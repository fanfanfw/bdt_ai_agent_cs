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


class WidgetConfiguration(models.Model):
    """Model untuk menyimpan konfigurasi widget yang sudah dibuat user"""
    assistant = models.ForeignKey(AIAssistant, on_delete=models.CASCADE, related_name='widget_configs')
    name = models.CharField(max_length=100, help_text="Nama konfigurasi widget")
    description = models.TextField(blank=True, help_text="Deskripsi konfigurasi")
    
    # Widget appearance settings
    widget_title = models.CharField(max_length=100, default="AI Assistant")
    widget_position = models.CharField(max_length=20, default="bottom-right")
    primary_color = models.CharField(max_length=7, default="#007bff")
    secondary_color = models.CharField(max_length=7, default="#6c757d")
    
    # Chat settings
    welcome_message = models.TextField(default="Hello! How can I help you today?")
    chat_placeholder = models.CharField(max_length=100, default="Type your message...")
    
    # Voice settings
    voice_enabled = models.BooleanField(default=False)
    voice_language = models.CharField(max_length=5, default="auto")
    voice_show_transcript = models.BooleanField(default=True)
    
    # Privacy settings
    consent_required = models.BooleanField(default=False)
    consent_title = models.CharField(max_length=100, default="Terms and Conditions")
    consent_content = models.TextField(default="By using this chat, you agree to our terms of service.")
    
    # Generated code
    generated_code = models.TextField(blank=True, help_text="Generated widget HTML/JS code")
    
    # Usage tracking
    times_copied = models.IntegerField(default=0)
    last_copied_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Widget Configuration"
        verbose_name_plural = "Widget Configurations"
    
    def __str__(self):
        return f"{self.name} - {self.assistant.user.username}"
    
    def mark_copied(self):
        """Mark widget as copied and increment counter"""
        from django.utils import timezone
        self.times_copied += 1
        self.last_copied_at = timezone.now()
        self.save(update_fields=['times_copied', 'last_copied_at'])
    
    def get_configuration_dict(self):
        """Get configuration as dictionary for JavaScript"""
        return {
            'widget_title': self.widget_title,
            'widget_position': self.widget_position,
            'primary_color': self.primary_color,
            'secondary_color': self.secondary_color,
            'welcome_message': self.welcome_message,
            'chat_placeholder': self.chat_placeholder,
            'voice_enabled': self.voice_enabled,
            'voice_language': self.voice_language,
            'voice_show_transcript': self.voice_show_transcript,
            'consent_required': self.consent_required,
            'consent_title': self.consent_title,
            'consent_content': self.consent_content,
        }