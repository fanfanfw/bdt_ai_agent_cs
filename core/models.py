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
    
    # Monthly limits (0 means unlimited)
    monthly_api_limit = models.IntegerField(default=1000)  # Free: 1000, Pro: 10000, Pro+: 0
    monthly_token_limit = models.IntegerField(default=50000)  # Free: 50k, Pro: 500k, Pro+: 0
    
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
        if self.monthly_api_limit == 0:  # Unlimited
            return True
        return self.current_month_api_requests < self.monthly_api_limit
    
    def can_use_tokens(self, token_count):
        if self.status != 'approved':
            return False
        if self.monthly_token_limit == 0:  # Unlimited
            return True
        return (self.current_month_tokens + token_count) <= self.monthly_token_limit
    
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
        if self.subscription_plan == 'free':
            self.monthly_api_limit = 1000
            self.monthly_token_limit = 50000
        elif self.subscription_plan == 'pro':
            self.monthly_api_limit = 10000
            self.monthly_token_limit = 500000
        elif self.subscription_plan == 'pro_plus':
            self.monthly_api_limit = 0  # Unlimited
            self.monthly_token_limit = 0  # Unlimited
        self.save(update_fields=['monthly_api_limit', 'monthly_token_limit'])


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
