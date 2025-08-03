from django.db import models
from django.contrib.auth.models import User
import uuid
import json


class BusinessType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class AIAssistant(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    business_type = models.ForeignKey(BusinessType, on_delete=models.CASCADE)
    openai_assistant_id = models.CharField(max_length=100, blank=True, null=True)
    api_key = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    system_instructions = models.TextField()
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

    def __str__(self):
        return self.title


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
