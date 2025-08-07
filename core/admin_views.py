from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Q, Sum
from django.utils import timezone
from datetime import timedelta
import json

from .models import UserProfile, AIAssistant, ApiUsageLog, ChatSession, ChatMessage, KnowledgeBase, SubscriptionPlan
from .admin_auth import admin_required
from .user_utils import RegularUserQuerySet


@admin_required
def admin_dashboard(request):
    """Admin dashboard with analytics - Only regular users, exclude admins"""
    # Basic statistics (regular users only)
    total_users = RegularUserQuerySet.count_regular_users()
    pending_users = RegularUserQuerySet.count_pending_users()
    approved_users = RegularUserQuerySet.count_approved_users()
    suspended_users = RegularUserQuerySet.count_suspended_users()
    
    # Subscription statistics (regular users only)
    subscription_stats = RegularUserQuerySet.get_subscription_stats()
    
    # Activity statistics (last 30 days, regular users only)
    active_users_30d = RegularUserQuerySet.count_active_users_30d()
    
    # API usage statistics (from regular users only)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    total_api_requests = ApiUsageLog.objects.filter(user__profile__user_type='user').count()
    api_requests_30d = ApiUsageLog.objects.filter(
        user__profile__user_type='user',
        created_at__gte=thirty_days_ago
    ).count()
    
    # Monthly usage statistics (regular users only)
    monthly_tokens = UserProfile.objects.filter(user_type='user').aggregate(
        total=Sum('current_month_tokens')
    )['total'] or 0
    
    monthly_requests = UserProfile.objects.filter(user_type='user').aggregate(
        total=Sum('current_month_api_requests')
    )['total'] or 0
    
    # Recent users (last 10, regular users only)
    recent_users = RegularUserQuerySet.get_recent_users(10)
    
    # Top users by usage (regular users only)
    top_users_by_requests = RegularUserQuerySet.get_top_users_by_requests(10)
    
    context = {
        'total_users': total_users,
        'pending_users': pending_users,
        'pending_count': pending_users,  # For navbar
        'approved_users': approved_users,
        'suspended_users': suspended_users,
        'subscription_stats': subscription_stats,
        'active_users_30d': active_users_30d,
        'total_api_requests': total_api_requests,
        'api_requests_30d': api_requests_30d,
        'monthly_tokens': monthly_tokens,
        'monthly_requests': monthly_requests,
        'recent_users': recent_users,
        'top_users_by_requests': top_users_by_requests,
    }
    
    return render(request, 'admin/dashboard.html', context)


@admin_required
def user_management(request):
    """User management page - Only regular users, exclude admins"""
    status_filter = request.GET.get('status', 'all')
    subscription_filter = request.GET.get('subscription', 'all')
    search_query = request.GET.get('search', '')
    
    # Start with regular users only
    users = RegularUserQuerySet.get_regular_users().order_by('-date_joined')
    
    # Apply filters
    if status_filter != 'all':
        users = users.filter(profile__status=status_filter)
    
    if subscription_filter != 'all':
        users = users.filter(profile__subscription_plan=subscription_filter)
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    # Pagination could be added here
    users = users[:100]  # Limit to 100 for now
    
    context = {
        'users': users,
        'status_filter': status_filter,
        'subscription_filter': subscription_filter,
        'search_query': search_query,
        'status_choices': UserProfile.STATUS_CHOICES,
        'subscription_choices': UserProfile.SUBSCRIPTION_CHOICES,
    }
    
    return render(request, 'admin/user_management.html', context)


@admin_required
def user_detail(request, user_id):
    """User detail page with usage statistics - Only for regular users"""
    user = get_object_or_404(User, id=user_id, profile__user_type='user')
    profile = user.profile
    
    # Get AI Assistant if exists
    try:
        assistant = AIAssistant.objects.get(user=user)
    except AIAssistant.DoesNotExist:
        assistant = None
    
    # Usage statistics
    total_chat_sessions = ChatSession.objects.filter(assistant__user=user).count() if assistant else 0
    total_messages = ChatMessage.objects.filter(session__assistant__user=user).count() if assistant else 0
    total_knowledge_items = KnowledgeBase.objects.filter(assistant__user=user).count() if assistant else 0
    
    # Recent API usage (last 50)
    recent_api_usage = ApiUsageLog.objects.filter(user=user).order_by('-created_at')[:50]
    
    # Monthly usage data for chart
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_usage = []
    for i in range(30):
        day = timezone.now() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        usage_count = ApiUsageLog.objects.filter(
            user=user,
            created_at__gte=day_start,
            created_at__lt=day_end
        ).count()
        
        daily_usage.append({
            'date': day_start.strftime('%Y-%m-%d'),
            'count': usage_count
        })
    
    daily_usage.reverse()  # Show oldest to newest
    
    # Get available subscription plans for dropdown
    available_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('order')
    
    context = {
        'user': user,
        'profile': profile,
        'assistant': assistant,
        'total_chat_sessions': total_chat_sessions,
        'total_messages': total_messages,
        'total_knowledge_items': total_knowledge_items,
        'recent_api_usage': recent_api_usage,
        'daily_usage_json': json.dumps(daily_usage),
        'available_plans': available_plans,
    }
    
    return render(request, 'admin/user_detail.html', context)


@admin_required
def approve_user(request, user_id):
    """Approve a regular user - Admins cannot be approved"""
    user = get_object_or_404(User, id=user_id, profile__user_type='user')
    profile = user.profile
    
    if profile.status == 'pending':
        profile.approve()
        messages.success(request, f'User {user.username} has been approved.')
    else:
        messages.warning(request, f'User {user.username} is not pending approval.')
    
    return redirect('admin_user_detail', user_id=user_id)


@admin_required
def suspend_user(request, user_id):
    """Suspend a regular user - Admins cannot be suspended"""
    user = get_object_or_404(User, id=user_id, profile__user_type='user')
    profile = user.profile
    
    if profile.status == 'approved':
        profile.suspend()
        messages.success(request, f'User {user.username} has been suspended.')
    else:
        messages.warning(request, f'User {user.username} is not approved, cannot suspend.')
    
    return redirect('admin_user_detail', user_id=user_id)


@admin_required
def reject_user(request, user_id):
    """Reject a regular user - Admins cannot be rejected"""
    user = get_object_or_404(User, id=user_id, profile__user_type='user')
    profile = user.profile
    
    if profile.status == 'pending':
        profile.reject()
        messages.success(request, f'User {user.username} has been rejected.')
    else:
        messages.warning(request, f'User {user.username} is not pending, cannot reject.')
    
    return redirect('admin_user_detail', user_id=user_id)


@admin_required
def reactivate_user(request, user_id):
    """Reactivate a suspended regular user - Admins cannot be reactivated"""
    user = get_object_or_404(User, id=user_id, profile__user_type='user')
    profile = user.profile
    
    if profile.status == 'suspended':
        profile.approve()
        messages.success(request, f'User {user.username} has been reactivated.')
    else:
        messages.warning(request, f'User {user.username} is not suspended, cannot reactivate.')
    
    return redirect('admin_user_detail', user_id=user_id)


@admin_required
def update_subscription(request, user_id):
    """Update regular user subscription - Admins don't have subscriptions"""
    user = get_object_or_404(User, id=user_id, profile__user_type='user')
    profile = user.profile
    
    if request.method == 'POST':
        new_plan = request.POST.get('subscription_plan')
        
        # Validate plan exists in SubscriptionPlan model
        try:
            plan_obj = SubscriptionPlan.objects.get(name=new_plan, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            messages.error(request, f'Invalid or inactive subscription plan: {new_plan}')
            return redirect('admin_user_detail', user_id=user_id)
        
        old_plan = profile.subscription_plan
        
        # Update subscription plan
        profile.subscription_plan = new_plan
        
        # Apply subscription limits and save
        profile.set_subscription_limits()
        profile.save()  # Save changes to database
        
        # Force refresh from database to ensure we have the saved data
        profile.refresh_from_db()
        
        # Log the change for audit
        print(f"[ADMIN] User {user.username} subscription updated: {old_plan} -> {new_plan}")
        print(f"[ADMIN] Current plan in DB: {profile.subscription_plan}")
        print(f"[ADMIN] New limits - API: {profile.monthly_api_limit}, Tokens: {profile.monthly_token_limit}")
        
        messages.success(
            request, 
            f'User {user.username} subscription updated from {old_plan} to {new_plan}. '
            f'New limits: {profile.monthly_api_limit:,} API requests, {profile.monthly_token_limit:,} tokens per month.'
        )
    
    return redirect('admin_user_detail', user_id=user_id)


@admin_required
def analytics_api(request):
    """API endpoint for dashboard analytics data"""
    if request.method == 'GET':
        # Get data for charts
        chart_type = request.GET.get('type', 'daily_users')
        
        if chart_type == 'daily_users':
            # Daily user registrations for last 30 days
            thirty_days_ago = timezone.now() - timedelta(days=30)
            data = []
            
            for i in range(30):
                day = timezone.now() - timedelta(days=i)
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                
                user_count = User.objects.filter(
                    date_joined__gte=day_start,
                    date_joined__lt=day_end
                ).count()
                
                data.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'count': user_count
                })
            
            data.reverse()
            return JsonResponse({'data': data})
            
        elif chart_type == 'api_usage':
            # API usage for last 7 days
            seven_days_ago = timezone.now() - timedelta(days=7)
            data = []
            
            for i in range(7):
                day = timezone.now() - timedelta(days=i)
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                
                usage_count = ApiUsageLog.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end
                ).count()
                
                data.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'count': usage_count
                })
            
            data.reverse()
            return JsonResponse({'data': data})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@admin_required
def pending_approvals(request):
    """Show pending user approvals - Only regular users, exclude admins"""
    pending_users = RegularUserQuerySet.get_regular_users().filter(
        profile__status='pending'
    ).order_by('-date_joined')
    
    return render(request, 'admin/pending_approvals.html', {
        'pending_users': pending_users
    })


@admin_required
def bulk_approve_users(request):
    """Bulk approve users - Only regular users, exclude admins"""
    if request.method == 'POST':
        user_ids = request.POST.getlist('user_ids')
        if user_ids:
            profiles = UserProfile.objects.filter(
                user__id__in=user_ids,
                user_type='user',  # Only regular users
                status='pending'
            )
            
            count = profiles.count()
            for profile in profiles:
                profile.approve()
            
            messages.success(request, f'{count} users have been approved.')
        else:
            messages.warning(request, 'No users selected.')
    
    return redirect('admin_pending_approvals')


@admin_required
def bulk_reject_users(request):
    """Bulk reject users - Only regular users, exclude admins"""
    if request.method == 'POST':
        user_ids = request.POST.getlist('user_ids')
        if user_ids:
            profiles = UserProfile.objects.filter(
                user__id__in=user_ids,
                user_type='user',  # Only regular users
                status='pending'
            )
            
            count = profiles.count()
            for profile in profiles:
                profile.reject()
            
            messages.success(request, f'{count} users have been rejected.')
        else:
            messages.warning(request, 'No users selected.')
    
    return redirect('admin_pending_approvals')


# Subscription Plan Management Views

@admin_required
def subscription_plans(request):
    """List all subscription plans"""
    plans = SubscriptionPlan.objects.all().order_by('order')
    return render(request, 'admin/subscription_plans.html', {
        'plans': plans
    })


@admin_required
def create_plan(request):
    """Create a new subscription plan"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            price = float(request.POST.get('price', 0))
            monthly_api_limit = int(request.POST.get('monthly_api_limit', 0))
            monthly_token_limit = int(request.POST.get('monthly_token_limit', 0))
            max_assistants = int(request.POST.get('max_assistants', 1))
            max_knowledge_bases = int(request.POST.get('max_knowledge_bases', 1))
            order = int(request.POST.get('order', 0))
            is_active = request.POST.get('is_active') == 'on'
            
            # Parse features from JSON or text
            features_text = request.POST.get('features', '[]')
            try:
                if features_text.startswith('['):
                    features = json.loads(features_text)
                else:
                    # Convert text lines to JSON array
                    features = [line.strip() for line in features_text.split('\n') if line.strip()]
            except json.JSONDecodeError:
                features = []
            
            # Validate required fields
            if not name:
                messages.error(request, 'Plan name is required.')
                return render(request, 'admin/create_plan.html')
            
            # Create plan
            plan = SubscriptionPlan.objects.create(
                name=name,
                description=description,
                price=price,
                monthly_api_limit=monthly_api_limit,
                monthly_token_limit=monthly_token_limit,
                max_assistants=max_assistants,
                max_knowledge_bases=max_knowledge_bases,
                features=features,
                order=order,
                is_active=is_active
            )
            
            messages.success(request, f'Subscription plan "{plan.name}" created successfully.')
            return redirect('subscription_plans')
            
        except ValueError as e:
            messages.error(request, f'Invalid input: {str(e)}')
        except Exception as e:
            messages.error(request, f'Error creating plan: {str(e)}')
    
    return render(request, 'admin/create_plan.html')


@admin_required
def edit_plan(request, plan_id):
    """Edit an existing subscription plan"""
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    
    if request.method == 'POST':
        try:
            plan.name = request.POST.get('name', '').strip()
            plan.description = request.POST.get('description', '').strip()
            plan.price = float(request.POST.get('price', 0))
            plan.monthly_api_limit = int(request.POST.get('monthly_api_limit', 0))
            plan.monthly_token_limit = int(request.POST.get('monthly_token_limit', 0))
            plan.max_assistants = int(request.POST.get('max_assistants', 1))
            plan.max_knowledge_bases = int(request.POST.get('max_knowledge_bases', 1))
            plan.order = int(request.POST.get('order', 0))
            plan.is_active = request.POST.get('is_active') == 'on'
            
            # Parse features
            features_text = request.POST.get('features', '[]')
            try:
                if features_text.startswith('['):
                    plan.features = json.loads(features_text)
                else:
                    plan.features = [line.strip() for line in features_text.split('\n') if line.strip()]
            except json.JSONDecodeError:
                plan.features = []
            
            # Validate required fields
            if not plan.name:
                messages.error(request, 'Plan name is required.')
                return render(request, 'admin/edit_plan.html', {'plan': plan})
            
            plan.save()
            messages.success(request, f'Subscription plan "{plan.name}" updated successfully.')
            return redirect('subscription_plans')
            
        except ValueError as e:
            messages.error(request, f'Invalid input: {str(e)}')
        except Exception as e:
            messages.error(request, f'Error updating plan: {str(e)}')
    
    # Convert features list to text for editing
    features_text = '\n'.join(plan.features) if plan.features else ''
    
    return render(request, 'admin/edit_plan.html', {
        'plan': plan,
        'features_text': features_text
    })


@admin_required
def delete_plan(request, plan_id):
    """Delete a subscription plan"""
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    
    if request.method == 'POST':
        # Check if any regular users are using this plan (exclude admins)
        users_count = UserProfile.objects.filter(
            subscription_plan=plan.name,
            user_type='user'  # Only count regular users
        ).count()
        
        if users_count > 0:
            messages.error(request, f'Cannot delete plan "{plan.name}". It is currently used by {users_count} user(s).')
        else:
            plan_name = plan.name
            plan.delete()
            messages.success(request, f'Subscription plan "{plan_name}" deleted successfully.')
        
        return redirect('subscription_plans')
    
    # Count regular users using this plan (exclude admins)
    users_count = UserProfile.objects.filter(
        subscription_plan=plan.name,
        user_type='user'  # Only count regular users
    ).count()
    
    return render(request, 'admin/confirm_delete_plan.html', {
        'plan': plan,
        'users_count': users_count
    })


@admin_required
def toggle_plan_status(request, plan_id):
    """Toggle plan active status via AJAX"""
    if request.method == 'POST':
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        plan.is_active = not plan.is_active
        plan.save()
        
        return JsonResponse({
            'success': True,
            'is_active': plan.is_active,
            'message': f'Plan "{plan.name}" {"activated" if plan.is_active else "deactivated"}.'
        })
    
    return JsonResponse({'success': False, 'message': 'Invalid request.'})


@admin_required
def plan_usage_stats(request, plan_id):
    """Show usage statistics for a specific plan"""
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    
    # Get regular users on this plan (exclude admins)
    users_on_plan = UserProfile.objects.filter(
        subscription_plan=plan.name,
        user_type='user'  # Only regular users
    )
    total_users = users_on_plan.count()
    
    # Usage statistics
    total_api_requests = sum(user.current_month_api_requests for user in users_on_plan)
    total_tokens = sum(user.current_month_tokens for user in users_on_plan)
    
    # Average usage per user
    avg_api_requests = total_api_requests / total_users if total_users > 0 else 0
    avg_tokens = total_tokens / total_users if total_users > 0 else 0
    
    # Usage percentages
    api_usage_percent = (total_api_requests / (plan.monthly_api_limit * total_users) * 100) if total_users > 0 and plan.monthly_api_limit > 0 else 0
    token_usage_percent = (total_tokens / (plan.monthly_token_limit * total_users) * 100) if total_users > 0 and plan.monthly_token_limit > 0 else 0
    
    return render(request, 'admin/plan_usage_stats.html', {
        'plan': plan,
        'total_users': total_users,
        'total_api_requests': total_api_requests,
        'total_tokens': total_tokens,
        'avg_api_requests': avg_api_requests,
        'avg_tokens': avg_tokens,
        'api_usage_percent': api_usage_percent,
        'token_usage_percent': token_usage_percent,
        'users_on_plan': users_on_plan[:10]  # Show first 10 users
    })