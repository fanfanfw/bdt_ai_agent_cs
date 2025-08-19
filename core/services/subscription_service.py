from django.db.models import Count, Sum
from django.utils import timezone
from datetime import datetime, timedelta

from ..models import UserProfile, SubscriptionPlan, ApiUsageLog


class SubscriptionService:
    """Service for handling subscription and usage tracking"""
    
    def __init__(self, user=None):
        self.user = user
        if user:
            self.profile = user.profile
    
    def get_user_usage_stats(self, user=None):
        """Get comprehensive usage statistics for user"""
        if user:
            profile = user.profile
        else:
            profile = self.profile
        
        profile.reset_monthly_usage_if_needed()
        
        # Get current limits
        current_limits = profile.get_current_limits()
        
        # Calculate usage percentages
        api_usage_percentage = 0
        token_usage_percentage = 0
        
        if current_limits['monthly_api_limit'] > 0:
            api_usage_percentage = (profile.current_month_api_requests / current_limits['monthly_api_limit']) * 100
        
        if current_limits['monthly_token_limit'] > 0:
            token_usage_percentage = (profile.current_month_tokens / current_limits['monthly_token_limit']) * 100
        
        return {
            'subscription_plan': profile.subscription_plan,
            'status': profile.status,
            
            # Current month usage
            'current_month_api_requests': profile.current_month_api_requests,
            'current_month_tokens': profile.current_month_tokens,
            
            # Limits
            'monthly_api_limit': current_limits['monthly_api_limit'],
            'monthly_token_limit': current_limits['monthly_token_limit'],
            'max_assistants': current_limits['max_assistants'],
            'max_knowledge_bases': current_limits['max_knowledge_bases'],
            
            # Usage percentages
            'api_usage_percentage': round(api_usage_percentage, 1),
            'token_usage_percentage': round(token_usage_percentage, 1),
            
            # Total usage (all time)
            'total_api_requests': profile.api_requests_count,
            'total_tokens': profile.tokens_used,
            
            # Status checks
            'can_make_api_request': profile.can_make_api_request(),
            'has_token_limit_exceeded': profile.has_token_limit_exceeded(),
            
            # Dates
            'last_reset_date': profile.last_reset_date,
            'last_activity': profile.last_activity,
        }
    
    def get_plan_details(self, plan_name=None):
        """Get subscription plan details"""
        if not plan_name:
            plan_name = self.profile.subscription_plan
        
        try:
            plan = SubscriptionPlan.objects.get(name=plan_name, is_active=True)
            return {
                'name': plan.name,
                'description': plan.description,
                'price': plan.price,
                'monthly_api_limit': plan.monthly_api_limit,
                'monthly_token_limit': plan.monthly_token_limit,
                'max_assistants': plan.max_assistants,
                'max_knowledge_bases': plan.max_knowledge_bases,
                'features': plan.features,
                'user_count': plan.user_count,
            }
        except SubscriptionPlan.DoesNotExist:
            return None
    
    def upgrade_subscription(self, new_plan_name, enable_auto_renewal=False):
        """Upgrade user's subscription plan with new subscription cycle logic"""
        try:
            new_plan = SubscriptionPlan.objects.get(name=new_plan_name, is_active=True)
            old_plan = self.profile.subscription_plan
            
            # Use the new upgrade method from UserProfile
            success = self.profile.upgrade_subscription(new_plan_name)
            
            if success:
                # Set auto renewal if requested
                if enable_auto_renewal:
                    self.profile.auto_renewal = True
                    self.profile.save(update_fields=['auto_renewal'])
                
                return True, f"Successfully upgraded from {old_plan} to {new_plan_name}. New 30-day cycle started."
            else:
                return False, "Failed to upgrade subscription"
                
        except SubscriptionPlan.DoesNotExist:
            return False, "Invalid subscription plan"
        except Exception as e:
            return False, f"Error upgrading subscription: {str(e)}"
    
    def downgrade_subscription(self, new_plan_name):
        """Downgrade user's subscription plan (immediate effect)"""
        try:
            new_plan = SubscriptionPlan.objects.get(name=new_plan_name, is_active=True)
            old_plan = self.profile.subscription_plan
            
            # Store previous plan
            self.profile.previous_plan = old_plan
            self.profile.plan_changed_at = timezone.now()
            
            # Update to new plan
            self.profile.subscription_plan = new_plan_name
            self.profile.monthly_api_limit = new_plan.monthly_api_limit
            self.profile.monthly_token_limit = new_plan.monthly_token_limit
            
            # Keep existing billing cycle (don't reset usage)
            # User will get new limits on next renewal
            
            self.profile.save()
            
            return True, f"Successfully downgraded from {old_plan} to {new_plan_name}. Changes take effect immediately."
            
        except SubscriptionPlan.DoesNotExist:
            return False, "Invalid subscription plan"
        except Exception as e:
            return False, f"Error downgrading subscription: {str(e)}"
    
    def enable_auto_renewal(self):
        """Enable auto-renewal for user's subscription"""
        self.profile.auto_renewal = True
        self.profile.save(update_fields=['auto_renewal'])
        return True, "Auto-renewal enabled"
    
    def disable_auto_renewal(self):
        """Disable auto-renewal for user's subscription"""
        self.profile.auto_renewal = False
        self.profile.save(update_fields=['auto_renewal'])
        return True, "Auto-renewal disabled"
    
    def record_usage(self, endpoint, method, tokens_used=0, ip_address=None, user_agent=None, response_time_ms=None, status_code=200):
        """Record API usage with detailed logging"""
        # Update profile usage
        self.profile.record_api_usage(token_count=tokens_used)
        
        # Log detailed usage
        ApiUsageLog.objects.create(
            user=self.user,
            endpoint=endpoint,
            method=method,
            tokens_used=tokens_used,
            response_time_ms=response_time_ms,
            status_code=status_code,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    def get_usage_history(self, days=30):
        """Get usage history for the last N days"""
        start_date = timezone.now() - timedelta(days=days)
        
        logs = ApiUsageLog.objects.filter(
            user=self.user,
            created_at__gte=start_date
        ).order_by('-created_at')
        
        # Group by day
        daily_usage = {}
        for log in logs:
            day = log.created_at.date()
            if day not in daily_usage:
                daily_usage[day] = {
                    'date': day,
                    'api_requests': 0,
                    'tokens_used': 0,
                    'endpoints': set(),
                }
            
            daily_usage[day]['api_requests'] += 1
            daily_usage[day]['tokens_used'] += log.tokens_used
            daily_usage[day]['endpoints'].add(log.endpoint)
        
        # Convert sets to lists and sort
        result = []
        for day_data in sorted(daily_usage.values(), key=lambda x: x['date'], reverse=True):
            day_data['endpoints'] = list(day_data['endpoints'])
            result.append(day_data)
        
        return result
    
    def get_top_endpoints(self, days=30, limit=10):
        """Get most used endpoints"""
        start_date = timezone.now() - timedelta(days=days)
        
        endpoints = ApiUsageLog.objects.filter(
            user=self.user,
            created_at__gte=start_date
        ).values('endpoint').annotate(
            request_count=Count('id'),
            total_tokens=Sum('tokens_used')
        ).order_by('-request_count')[:limit]
        
        return list(endpoints)
    
    def check_usage_alerts(self):
        """Check if user is approaching usage limits"""
        alerts = []
        stats = self.get_user_usage_stats()
        
        # API usage alerts
        if stats['monthly_api_limit'] > 0:
            if stats['api_usage_percentage'] >= 90:
                alerts.append({
                    'type': 'api_limit',
                    'level': 'critical',
                    'message': f"You've used {stats['api_usage_percentage']:.1f}% of your API requests",
                    'usage': stats['current_month_api_requests'],
                    'limit': stats['monthly_api_limit']
                })
            elif stats['api_usage_percentage'] >= 75:
                alerts.append({
                    'type': 'api_limit',
                    'level': 'warning',
                    'message': f"You've used {stats['api_usage_percentage']:.1f}% of your API requests",
                    'usage': stats['current_month_api_requests'],
                    'limit': stats['monthly_api_limit']
                })
        
        # Token usage alerts
        if stats['monthly_token_limit'] > 0:
            if stats['token_usage_percentage'] >= 90:
                alerts.append({
                    'type': 'token_limit',
                    'level': 'critical',
                    'message': f"You've used {stats['token_usage_percentage']:.1f}% of your token limit",
                    'usage': stats['current_month_tokens'],
                    'limit': stats['monthly_token_limit']
                })
            elif stats['token_usage_percentage'] >= 75:
                alerts.append({
                    'type': 'token_limit',
                    'level': 'warning',
                    'message': f"You've used {stats['token_usage_percentage']:.1f}% of your token limit",
                    'usage': stats['current_month_tokens'],
                    'limit': stats['monthly_token_limit']
                })
        
        return alerts
    
    def get_subscription_cycle_info(self):
        """Get detailed subscription cycle information"""
        if not self.profile.billing_cycle_end:
            return {
                'has_billing_cycle': False,
                'needs_initialization': True
            }
        
        today = timezone.now().date()
        days_remaining = self.profile.days_until_renewal()
        
        return {
            'has_billing_cycle': True,
            'subscription_start_date': self.profile.subscription_start_date,
            'billing_cycle_end': self.profile.billing_cycle_end,
            'days_remaining': days_remaining,
            'is_expired': self.profile.is_subscription_expired(),
            'auto_renewal': self.profile.auto_renewal,
            'previous_plan': self.profile.previous_plan,
            'plan_changed_at': self.profile.plan_changed_at,
            'cycle_progress_percentage': round(
                (30 - days_remaining) / 30 * 100 if days_remaining <= 30 else 100, 1
            ) if days_remaining > 0 else 100,
        }
    
    @staticmethod
    def get_all_active_plans():
        """Get all active subscription plans"""
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('order', 'price')
        
        result = []
        for plan in plans:
            result.append({
                'id': plan.id,
                'name': plan.name,
                'description': plan.description,
                'price': plan.price,
                'monthly_api_limit': plan.monthly_api_limit,
                'monthly_token_limit': plan.monthly_token_limit,
                'max_assistants': plan.max_assistants,
                'max_knowledge_bases': plan.max_knowledge_bases,
                'features': plan.features,
                'user_count': plan.user_count,
                'is_default': plan.is_default,
            })
        
        return result
    
    @staticmethod
    def get_system_usage_stats():
        """Get system-wide usage statistics (admin only)"""
        from django.db.models import Q
        
        # Total users by status
        user_stats = UserProfile.objects.values('status').annotate(count=Count('id'))
        
        # Total usage this month
        current_month = timezone.now().replace(day=1)
        monthly_usage = ApiUsageLog.objects.filter(
            created_at__gte=current_month
        ).aggregate(
            total_requests=Count('id'),
            total_tokens=Sum('tokens_used')
        )
        
        # Plan distribution
        plan_stats = UserProfile.objects.values('subscription_plan').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Active users (last 30 days)
        active_threshold = timezone.now() - timedelta(days=30)
        active_users = UserProfile.objects.filter(
            last_activity__gte=active_threshold,
            status='approved'
        ).count()
        
        return {
            'user_stats': list(user_stats),
            'monthly_usage': monthly_usage,
            'plan_stats': list(plan_stats),
            'active_users': active_users,
            'total_users': UserProfile.objects.count(),
        }
    
    def reset_monthly_usage(self):
        """Manually reset monthly usage (admin function)"""
        self.profile.current_month_api_requests = 0
        self.profile.current_month_tokens = 0
        self.profile.last_reset_date = timezone.now().date()
        self.profile.save(update_fields=[
            'current_month_api_requests', 
            'current_month_tokens', 
            'last_reset_date'
        ])
        
        return True, "Monthly usage reset successfully"