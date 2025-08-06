from django.contrib.auth.models import User
from .models import UserProfile


class RegularUserQuerySet:
    """Utility class to provide regular user queries (excluding admins)"""
    
    @staticmethod
    def get_regular_users():
        """Get all regular users (exclude admins)"""
        return User.objects.filter(profile__user_type='user').select_related('profile')
    
    @staticmethod
    def get_regular_user_profiles():
        """Get all regular user profiles (exclude admins)"""
        return UserProfile.objects.filter(user_type='user').select_related('user')
    
    @staticmethod
    def count_regular_users():
        """Count regular users only"""
        return User.objects.filter(profile__user_type='user').count()
    
    @staticmethod
    def count_pending_users():
        """Count pending regular users only"""
        return UserProfile.objects.filter(user_type='user', status='pending').count()
    
    @staticmethod
    def count_approved_users():
        """Count approved regular users only"""
        return UserProfile.objects.filter(user_type='user', status='approved').count()
    
    @staticmethod
    def count_suspended_users():
        """Count suspended regular users only"""
        return UserProfile.objects.filter(user_type='user', status='suspended').count()
    
    @staticmethod
    def count_active_users_30d():
        """Count active regular users in last 30 days"""
        from django.utils import timezone
        from datetime import timedelta
        
        thirty_days_ago = timezone.now() - timedelta(days=30)
        return UserProfile.objects.filter(
            user_type='user',
            last_activity__gte=thirty_days_ago
        ).count()
    
    @staticmethod
    def get_subscription_stats():
        """Get subscription distribution for regular users only"""
        from django.db.models import Count
        
        return UserProfile.objects.filter(user_type='user').values('subscription_plan').annotate(
            count=Count('id')
        ).order_by('subscription_plan')
    
    @staticmethod
    def get_recent_users(limit=10):
        """Get recent regular user registrations"""
        return User.objects.filter(profile__user_type='user').select_related('profile').order_by('-date_joined')[:limit]
    
    @staticmethod
    def get_top_users_by_requests(limit=10):
        """Get top regular users by API requests"""
        return UserProfile.objects.filter(user_type='user').select_related('user').order_by('-api_requests_count')[:limit]