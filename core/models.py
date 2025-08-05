from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
import uuid
import json
import os


class BusinessType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


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
