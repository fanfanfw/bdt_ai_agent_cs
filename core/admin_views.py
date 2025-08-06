from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Q, Sum
from django.utils import timezone
from datetime import timedelta
import json

from .models import UserProfile, AIAssistant, ApiUsageLog, ChatSession, ChatMessage, KnowledgeBase
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
    
    context = {
        'user': user,
        'profile': profile,
        'assistant': assistant,
        'total_chat_sessions': total_chat_sessions,
        'total_messages': total_messages,
        'total_knowledge_items': total_knowledge_items,
        'recent_api_usage': recent_api_usage,
        'daily_usage_json': json.dumps(daily_usage),
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
        if new_plan in [choice[0] for choice in UserProfile.SUBSCRIPTION_CHOICES]:
            old_plan = profile.subscription_plan
            profile.subscription_plan = new_plan
            profile.set_subscription_limits()  # This will save the profile
            
            messages.success(request, f'User {user.username} subscription updated from {old_plan} to {new_plan}.')
        else:
            messages.error(request, 'Invalid subscription plan.')
    
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