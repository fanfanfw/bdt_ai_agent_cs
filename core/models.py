from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
import uuid
import json
import os


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
                # Try to get default plan from SubscriptionPlan model
                default_plan = SubscriptionPlan.objects.filter(is_default=True, is_active=True).first()
                if default_plan:
                    self.subscription_plan = default_plan.name
                else:
                    # Fallback to any active plan named 'free'
                    free_plan = SubscriptionPlan.objects.filter(name='free', is_active=True).first()
                    if free_plan:
                        self.subscription_plan = 'free'
            except:
                # If SubscriptionPlan table doesn't exist yet (during migration), use default
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
            # Try to get plan from SubscriptionPlan model
            plan = SubscriptionPlan.objects.get(name=self.subscription_plan, is_active=True)
            self.monthly_api_limit = plan.monthly_api_limit
            self.monthly_token_limit = plan.monthly_token_limit
        except SubscriptionPlan.DoesNotExist:
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
            plan = SubscriptionPlan.objects.get(name=self.subscription_plan, is_active=True)
            return {
                'monthly_api_limit': plan.monthly_api_limit,
                'monthly_token_limit': plan.monthly_token_limit,
                'max_assistants': plan.max_assistants,
                'max_knowledge_bases': plan.max_knowledge_bases,
                'features': plan.features
            }
        except SubscriptionPlan.DoesNotExist:
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
            # Check against SubscriptionPlan model
            plan = SubscriptionPlan.objects.get(name=self.subscription_plan, is_active=True)
            expected_api = plan.monthly_api_limit
            expected_token = plan.monthly_token_limit
        except SubscriptionPlan.DoesNotExist:
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
            return SubscriptionPlan.objects.get(name=self.subscription_plan, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return None
    
    def fix_subscription_consistency(self):
        """Fix subscription consistency if needed"""
        if not self.validate_subscription_consistency():
            print(f"[WARNING] Fixing inconsistent subscription for user {self.user.username}")
            self.set_subscription_limits()
            return True
        return False


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


class AIAssistant(models.Model):
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('ms', 'Bahasa Malaysia'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    business_type = models.ForeignKey(BusinessType, on_delete=models.CASCADE)
    openai_assistant_id = models.CharField(max_length=100, blank=True, null=True)
    api_key = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    system_instructions = models.TextField()
    preferred_language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default='en')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Assistant for {self.user.username}"


class QnA(models.Model):
    assistant = models.ForeignKey(AIAssistant, on_delete=models.CASCADE, related_name='qnas')
    question = models.TextField()
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Q: {self.question[:50]}..."


class KnowledgeBase(models.Model):
    STATUS_CHOICES = [
        ('uploading', 'Uploading'),
        ('processing', 'Processing'),
        ('embedding', 'Creating Embeddings'),
        ('completed', 'Completed'),
        ('error', 'Error'),
    ]
    
    assistant = models.ForeignKey(AIAssistant, on_delete=models.CASCADE, related_name='knowledge_base')
    title = models.CharField(max_length=200)
    content = models.TextField()
    file_path = models.FileField(upload_to='knowledge_base/', blank=True, null=True)
    
    # File-based embedding storage
    embedding_file_path = models.CharField(max_length=500, blank=True)
    chunks_count = models.IntegerField(default=0)
    embedding_model = models.CharField(max_length=50, default='text-embedding-3-small')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploading')
    
    # Legacy field - will be deprecated
    embeddings = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
    def clean_embedding_files(self):
        """
        Clean up embedding files for this knowledge base item
        """
        if self.embedding_file_path and os.path.exists(self.embedding_file_path):
            try:
                os.remove(self.embedding_file_path)
                self.embedding_file_path = ""
                self.chunks_count = 0
                self.embeddings = {}
                self.save(update_fields=['embedding_file_path', 'chunks_count', 'embeddings'])
                return True
            except Exception as e:
                print(f"Error cleaning embedding files: {e}")
                return False
        return True


class ChatSession(models.Model):
    assistant = models.ForeignKey(AIAssistant, on_delete=models.CASCADE)
    openai_thread_id = models.CharField(max_length=100)
    session_id = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Session {self.session_id}"


class ChatMessage(models.Model):
    MESSAGE_TYPES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES)
    content = models.TextField()
    is_voice = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.message_type}: {self.content[:50]}..."


@receiver(pre_save, sender=KnowledgeBase)
def knowledge_base_pre_save(sender, instance, **kwargs):
    """
    Handle KnowledgeBase before save - detect content changes
    """
    if instance.pk:  # Only for existing instances
        try:
            old_instance = KnowledgeBase.objects.get(pk=instance.pk)
            
            # Check if content has changed (for manual content)
            content_changed = old_instance.content != instance.content
            
            # Check if file has changed (for file uploads)
            file_changed = old_instance.file_path != instance.file_path
            
            if content_changed or file_changed:
                # Store flag to refresh embeddings after save
                instance._embedding_refresh_needed = True
                
                # Delete old embedding file if exists
                if old_instance.embedding_file_path and os.path.exists(old_instance.embedding_file_path):
                    try:
                        os.remove(old_instance.embedding_file_path)
                        print(f"Deleted old embedding file: {old_instance.embedding_file_path}")
                    except Exception as e:
                        print(f"Error deleting old embedding file: {e}")
                        
        except KnowledgeBase.DoesNotExist:
            # New instance
            instance._embedding_refresh_needed = True


@receiver(post_save, sender=KnowledgeBase)
def knowledge_base_post_save(sender, instance, created, **kwargs):
    """
    Handle KnowledgeBase after save - regenerate embeddings if needed
    """
    # Check if this is a new instance or content changed
    should_refresh = created or getattr(instance, '_embedding_refresh_needed', False)
    
    if should_refresh:
        # Clear embedding data
        instance.embeddings = {}
        instance.embedding_file_path = ""
        instance.chunks_count = 0
        instance.status = 'processing'
        
        # Save without triggering signals again
        KnowledgeBase.objects.filter(pk=instance.pk).update(
            embeddings=instance.embeddings,
            embedding_file_path=instance.embedding_file_path,
            chunks_count=instance.chunks_count,
            status=instance.status
        )
        
        # Generate new embeddings asynchronously
        from django.db import transaction
        transaction.on_commit(lambda: _generate_embeddings_async(instance.pk))


@receiver(post_delete, sender=KnowledgeBase)
def knowledge_base_post_delete(sender, instance, **kwargs):
    """
    Handle KnowledgeBase deletion - clean up embedding files
    """
    # Delete embedding file if exists
    if instance.embedding_file_path and os.path.exists(instance.embedding_file_path):
        try:
            os.remove(instance.embedding_file_path)
            print(f"Deleted embedding file on knowledge base deletion: {instance.embedding_file_path}")
        except Exception as e:
            print(f"Error deleting embedding file on deletion: {e}")
    
    # Delete uploaded file if exists
    if instance.file_path:
        try:
            if os.path.exists(instance.file_path.path):
                os.remove(instance.file_path.path)
                print(f"Deleted uploaded file: {instance.file_path.path}")
        except Exception as e:
            print(f"Error deleting uploaded file: {e}")


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when User is created"""
    if created:
        # Determine user type based on staff/superuser status
        user_type = 'admin' if (instance.is_staff or instance.is_superuser) else 'user'
        status = 'approved' if user_type == 'admin' else 'pending'
        
        UserProfile.objects.create(
            user=instance,
            user_type=user_type,
            status=status
        )


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)
    instance.profile.save()


@receiver(post_save, sender='core.SubscriptionPlan')
def update_user_limits_on_plan_change(sender, instance, **kwargs):
    """Update user limits when subscription plan is modified"""
    from django.db import transaction
    
    # Update all users who have this subscription plan
    users_to_update = UserProfile.objects.filter(subscription_plan=instance.name)
    
    if users_to_update.exists():
        with transaction.atomic():
            for user_profile in users_to_update:
                user_profile.monthly_api_limit = instance.monthly_api_limit
                user_profile.monthly_token_limit = instance.monthly_token_limit
                user_profile.save(update_fields=['monthly_api_limit', 'monthly_token_limit'])
        
        print(f"Updated limits for {users_to_update.count()} users on plan '{instance.name}'")


def _generate_embeddings_async(knowledge_base_id):
    """
    Generate embeddings for a knowledge base item asynchronously
    """
    try:
        from .services import EmbeddingService
        instance = KnowledgeBase.objects.get(pk=knowledge_base_id)
        embedding_service = EmbeddingService()
        embedding_service.generate_embeddings_for_item(instance)
        print(f"Embeddings regenerated for: {instance.title}")
    except Exception as e:
        print(f"Error generating embeddings asynchronously: {e}")
        # Update status to error
        try:
            KnowledgeBase.objects.filter(pk=knowledge_base_id).update(status='error')
        except:
            pass
