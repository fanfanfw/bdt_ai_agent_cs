import uuid
from django.db import models
from .assistant import AIAssistant


class ChatSession(models.Model):
    SOURCE_CHOICES = [
        ('test_chat', 'Test Chat'),
        ('test_voice_realtime', 'Test Voice Realtime'),
        ('widget_chat', 'Widget Chat'),
        ('widget_voice', 'Widget Voice'),
    ]
    
    assistant = models.ForeignKey(AIAssistant, on_delete=models.CASCADE)
    openai_thread_id = models.CharField(max_length=100, blank=True, null=True)
    session_id = models.UUIDField(default=uuid.uuid4, unique=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='test_chat')
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