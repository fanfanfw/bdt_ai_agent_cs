import os
from django.db import models
from .assistant import AIAssistant


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


# WidgetConfiguration model REMOVED - using simple CDN widget instead