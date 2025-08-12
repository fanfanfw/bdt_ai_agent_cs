import os
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.db import transaction

from .knowledge import KnowledgeBase
from .user import UserProfile
from .subscription import SubscriptionPlan


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


@receiver(post_save, sender=SubscriptionPlan)
def update_user_limits_on_plan_change(sender, instance, **kwargs):
    """Update user limits when subscription plan is modified"""
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
        # Import here to avoid circular imports
        from ..services import EmbeddingService
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