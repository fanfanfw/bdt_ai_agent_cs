from django.contrib import admin
from .models import BusinessType, AIAssistant, QnA, KnowledgeBase, ChatSession, ChatMessage


@admin.register(BusinessType)
class BusinessTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(AIAssistant)
class AIAssistantAdmin(admin.ModelAdmin):
    list_display = ['user', 'business_type', 'is_active', 'created_at']
    list_filter = ['business_type', 'is_active', 'created_at']
    search_fields = ['user__username', 'business_type__name']
    readonly_fields = ['api_key', 'openai_assistant_id']


@admin.register(QnA)
class QnAAdmin(admin.ModelAdmin):
    list_display = ['assistant', 'question_preview', 'order']
    list_filter = ['assistant__business_type']
    search_fields = ['question', 'answer']
    
    def question_preview(self, obj):
        return obj.question[:50] + "..." if len(obj.question) > 50 else obj.question
    question_preview.short_description = 'Question'


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ['title', 'assistant', 'created_at']
    list_filter = ['assistant__business_type', 'created_at']
    search_fields = ['title', 'content']


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'assistant', 'created_at']
    list_filter = ['created_at']
    readonly_fields = ['session_id', 'openai_thread_id']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['session', 'message_type', 'content_preview', 'is_voice', 'created_at']
    list_filter = ['message_type', 'is_voice', 'created_at']
    search_fields = ['content']
    
    def content_preview(self, obj):
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
