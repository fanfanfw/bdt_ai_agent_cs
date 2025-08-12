from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class RegularUserManager(models.Manager):
    """Manager to get only regular users (exclude admins)"""
    def get_queryset(self):
        return super().get_queryset().filter(profile__user_type='user')


class BusinessType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    USER_TYPE_CHOICES = [
        ('admin', 'Admin'),
        ('user', 'Regular User'),
    ]
    
    SUBSCRIPTION_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('pro_plus', 'Pro+'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('suspended', 'Suspended'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='user')
    subscription_plan = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES, default='free')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Usage tracking
    api_requests_count = models.IntegerField(default=0)
    tokens_used = models.IntegerField(default=0)
    chat_messages_count = models.IntegerField(default=0)
    voice_messages_count = models.IntegerField(default=0)
    
    # Monthly limits (0 means unlimited) - will be set from SubscriptionPlan
    monthly_api_limit = models.IntegerField(default=1000)
    monthly_token_limit = models.IntegerField(default=50000)
    
    # Monthly usage reset
    current_month_api_requests = models.IntegerField(default=0)
    current_month_tokens = models.IntegerField(default=0)
    last_reset_date = models.DateField(auto_now_add=True)
    
    # Timestamps
    approved_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Set default subscription plan for new regular users only (not admins)
        if not self.pk and self.subscription_plan == 'free' and self.user_type == 'user':
            try:
                # Import here to avoid circular imports
                from .subscription import SubscriptionPlan
                # Try to get default plan from SubscriptionPlan model
                default_plan = SubscriptionPlan.objects.filter(is_default=True, is_active=True).first()
                if default_plan:
                    self.subscription_plan = default_plan.name
                    # Set limits from database plan immediately
                    self.monthly_api_limit = default_plan.monthly_api_limit
                    self.monthly_token_limit = default_plan.monthly_token_limit
                else:
                    # Fallback to any active plan named 'free'
                    free_plan = SubscriptionPlan.objects.filter(name='free', is_active=True).first()
                    if free_plan:
                        self.subscription_plan = 'free'
                        self.monthly_api_limit = free_plan.monthly_api_limit
                        self.monthly_token_limit = free_plan.monthly_token_limit
            except:
                # If SubscriptionPlan table doesn't exist yet (during migration), use default
                pass
        
        # For any user, ensure limits match their subscription plan from database
        if self.pk:  # Only for existing users to avoid infinite recursion
            try:
                from .subscription import SubscriptionPlan
                plan = SubscriptionPlan.objects.filter(name=self.subscription_plan, is_active=True).first()
                if plan:
                    # Only update if different to avoid unnecessary saves
                    if (self.monthly_api_limit != plan.monthly_api_limit or 
                        self.monthly_token_limit != plan.monthly_token_limit):
                        self.monthly_api_limit = plan.monthly_api_limit
                        self.monthly_token_limit = plan.monthly_token_limit
            except:
                pass
        
        super().save(*args, **kwargs)
        
        # Update limits after saving if needed
        if hasattr(self, '_update_limits_after_save'):
            self.sync_limits_with_plan(save=False)
            super().save(update_fields=['monthly_api_limit', 'monthly_token_limit'])

    def __str__(self):
        return f"{self.user.username} - {self.user_type} - {self.subscription_plan} ({self.status})"
    
    def is_regular_user(self):
        return self.user_type == 'user'
    
    def is_admin_user(self):
        return self.user_type == 'admin'
    
    def is_approved(self):
        return self.status == 'approved'
    
    def is_suspended(self):
        return self.status == 'suspended'
    
    def can_make_api_request(self):
        if self.status != 'approved':
            return False
        
        # Get current limits from subscription plan
        current_limits = self.get_current_limits()
        monthly_api_limit = current_limits['monthly_api_limit']
        
        if monthly_api_limit == 0:  # Unlimited
            return True
        return self.current_month_api_requests < monthly_api_limit
    
    def can_use_tokens(self, token_count):
        if self.status != 'approved':
            return False
        
        # Get current limits from subscription plan
        current_limits = self.get_current_limits()
        monthly_token_limit = current_limits['monthly_token_limit']
        
        if monthly_token_limit == 0:  # Unlimited
            return True
        return (self.current_month_tokens + token_count) <= monthly_token_limit
    
    def has_token_limit_exceeded(self):
        """Check if user has exceeded token limit"""
        if self.status != 'approved':
            return True
        
        # Get current limits from subscription plan
        current_limits = self.get_current_limits()
        monthly_token_limit = current_limits['monthly_token_limit']
        
        if monthly_token_limit == 0:  # Unlimited
            return False
        return self.current_month_tokens >= monthly_token_limit
    
    def update_activity(self):
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])
    
    def reset_monthly_usage_if_needed(self):
        today = timezone.now().date()
        if today.month != self.last_reset_date.month or today.year != self.last_reset_date.year:
            self.current_month_api_requests = 0
            self.current_month_tokens = 0
            self.last_reset_date = today
            self.save(update_fields=['current_month_api_requests', 'current_month_tokens', 'last_reset_date'])
    
    def record_api_usage(self, token_count=0):
        self.reset_monthly_usage_if_needed()
        self.api_requests_count += 1
        self.current_month_api_requests += 1
        self.tokens_used += token_count
        self.current_month_tokens += token_count
        self.update_activity()
        self.save(update_fields=['api_requests_count', 'current_month_api_requests', 
                               'tokens_used', 'current_month_tokens', 'last_activity'])
    
    def approve(self):
        self.status = 'approved'
        self.approved_at = timezone.now()
        self.save()
    
    def suspend(self):
        self.status = 'suspended'
        self.suspended_at = timezone.now()
        self.save()
    
    def reject(self):
        self.status = 'rejected'
        self.save()
    
    def set_subscription_limits(self):
        """Set monthly limits based on subscription plan using SubscriptionPlan model"""
        try:
            # Import here to avoid circular imports
            from .subscription import SubscriptionPlan
            # Try to get plan from SubscriptionPlan model
            plan = SubscriptionPlan.objects.get(name=self.subscription_plan, is_active=True)
            self.monthly_api_limit = plan.monthly_api_limit
            self.monthly_token_limit = plan.monthly_token_limit
        except:
            # Fallback to hardcoded values for backward compatibility
            if self.subscription_plan == 'free':
                self.monthly_api_limit = 1000
                self.monthly_token_limit = 50000
            elif self.subscription_plan == 'pro':
                self.monthly_api_limit = 10000
                self.monthly_token_limit = 500000
            elif self.subscription_plan == 'pro_plus':
                self.monthly_api_limit = 0  # Unlimited
                self.monthly_token_limit = 0  # Unlimited
            else:
                # Default to free plan if unknown subscription
                self.subscription_plan = 'free'
                self.monthly_api_limit = 1000
                self.monthly_token_limit = 50000
    
    def get_current_limits(self):
        """Get current limits from SubscriptionPlan model (real-time)"""
        try:
            from .subscription import SubscriptionPlan
            plan = SubscriptionPlan.objects.get(name=self.subscription_plan, is_active=True)
            return {
                'monthly_api_limit': plan.monthly_api_limit,
                'monthly_token_limit': plan.monthly_token_limit,
                'max_assistants': plan.max_assistants,
                'max_knowledge_bases': plan.max_knowledge_bases,
                'features': plan.features
            }
        except:
            # Fallback to current saved limits
            return {
                'monthly_api_limit': self.monthly_api_limit,
                'monthly_token_limit': self.monthly_token_limit,
                'max_assistants': 1,
                'max_knowledge_bases': 1,
                'features': []
            }
    
    def sync_with_subscription_plan(self):
        """Synchronize user limits with current subscription plan settings"""
        current_limits = self.get_current_limits()
        self.monthly_api_limit = current_limits['monthly_api_limit']
        self.monthly_token_limit = current_limits['monthly_token_limit']
        self.save(update_fields=['monthly_api_limit', 'monthly_token_limit'])
        
        self.save(update_fields=['subscription_plan', 'monthly_api_limit', 'monthly_token_limit'])
    
    def validate_subscription_consistency(self):
        """Validate that subscription plan matches the limits"""
        try:
            from .subscription import SubscriptionPlan
            # Check against SubscriptionPlan model
            plan = SubscriptionPlan.objects.get(name=self.subscription_plan, is_active=True)
            expected_api = plan.monthly_api_limit
            expected_token = plan.monthly_token_limit
        except:
            # Fallback to hardcoded values
            expected_limits = {
                'free': (1000, 50000),
                'pro': (10000, 500000),
                'pro_plus': (0, 0)
            }
            
            if self.subscription_plan in expected_limits:
                expected_api, expected_token = expected_limits[self.subscription_plan]
            else:
                return False
        
        return (self.monthly_api_limit == expected_api and 
                self.monthly_token_limit == expected_token)
    
    def get_subscription_plan_object(self):
        """Get the SubscriptionPlan object for this user"""
        try:
            from .subscription import SubscriptionPlan
            return SubscriptionPlan.objects.get(name=self.subscription_plan, is_active=True)
        except:
            return None
    
    def fix_subscription_consistency(self):
        """Fix subscription consistency if needed"""
        if not self.validate_subscription_consistency():
            print(f"[WARNING] Fixing inconsistent subscription for user {self.user.username}")
            self.set_subscription_limits()
            return True
        return False