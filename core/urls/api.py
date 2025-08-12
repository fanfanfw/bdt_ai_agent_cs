from django.urls import path
from ..api.widget import widget_chat_api, widget_voice_api, widget_status_api

urlpatterns = [
    # Widget API endpoints
    path('api/widget/chat/', widget_chat_api, name='widget_chat_api'),
    path('api/widget/voice/', widget_voice_api, name='widget_voice_api'), 
    path('api/widget/status/', widget_status_api, name='widget_status_api'),
    
    # Future API endpoints can be added here
]