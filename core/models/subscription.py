from django.db import models
from django.contrib.auth.models import User


class SubscriptionPlan(models.Model):
    """Model to manage subscription plans dynamically"""
    name = models.CharField(max_length=50, unique=True, help_text="Plan name (e.g., 'free', 'pro', 'enterprise')")
    description = models.TextField(blank=True, help_text="Plan description")
    
    # Limits
    monthly_api_limit = models.IntegerField(
        default=1000, 
        help_text="Monthly API request limit (0 = unlimited)"
    )
    monthly_token_limit = models.IntegerField(
        default=50000,
        help_text="Monthly token limit (0 = unlimited)"
    )
    max_assistants = models.IntegerField(default=1, help_text="Maximum AI assistants allowed")
    max_knowledge_bases = models.IntegerField(default=1, help_text="Maximum knowledge bases allowed")
    
    # Pricing
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        help_text="Monthly price in USD"
    )
    
    # Features
    features = models.JSONField(
        default=list,
        blank=True,
        help_text="List of plan features"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text="Default plan for new users")
    
    # Order for display
    order = models.IntegerField(default=0, help_text="Order for displaying plans")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'name']
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"
    
    def __str__(self):
        return f"{self.name} (${self.price}/month)"
    
    @property
    def user_count(self):
        """Return number of regular users currently on this plan (exclude admins)"""
        # Import here to avoid circular imports
        from .user import UserProfile
        return UserProfile.objects.filter(
            subscription_plan=self.name,
            user_type='user'  # Only count regular users, not admins
        ).count()
    
    def get_limits(self):
        """Return plan limits as dictionary"""
        return {
            'monthly_api_limit': self.monthly_api_limit,
            'monthly_token_limit': self.monthly_token_limit,
            'max_assistants': self.max_assistants,
            'max_knowledge_bases': self.max_knowledge_bases,
        }
    
    @classmethod
    def get_plan_limits(cls, plan_name):
        """Get limits for a specific plan"""
        try:
            plan = cls.objects.get(name=plan_name, is_active=True)
            return plan.get_limits()
        except cls.DoesNotExist:
            # Fallback to default limits if plan not found
            return {
                'monthly_api_limit': 1000,
                'monthly_token_limit': 50000,
                'max_assistants': 1,
                'max_knowledge_bases': 1,
            }
    
    def save(self, *args, **kwargs):
        # Ensure only one default plan
        if self.is_default:
            SubscriptionPlan.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_default_plan(cls):
        """Get the default plan for new users"""
        return cls.objects.filter(is_default=True, is_active=True).first()
    
    @classmethod
    def get_active_plans(cls):
        """Get all active plans"""
        return cls.objects.filter(is_active=True).order_by('sort_order', 'price')
    
    def get_limits_display(self):
        """Get human-readable limits"""
        api_limit = "Unlimited" if self.monthly_api_limit == 0 else f"{self.monthly_api_limit:,}"
        token_limit = "Unlimited" if self.monthly_token_limit == 0 else f"{self.monthly_token_limit:,}"
        return f"{api_limit} API calls, {token_limit} tokens"


class ApiUsageLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_usage_logs')
    endpoint = models.CharField(max_length=100)
    method = models.CharField(max_length=10)
    tokens_used = models.IntegerField(default=0)
    response_time_ms = models.IntegerField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.endpoint} ({self.created_at})"