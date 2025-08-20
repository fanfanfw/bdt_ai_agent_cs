from django.urls import path
from . import api_views

urlpatterns = [
    path('chat/', api_views.chat_api, name='chat_api'),
    # Legacy voice APIs removed - use realtime voice via WebSocket instead
    path('assistant-info/', api_views.assistant_info_api, name='assistant_info_api'),
    path('widget/', api_views.ChatWidgetView.as_view(), name='chat_widget'),
    # Realtime Voice API endpoints
    path('realtime-session/', api_views.realtime_session_api, name='realtime_session_api'),
    path('realtime-function-call/', api_views.realtime_function_call_api, name='realtime_function_call_api'),
    path('realtime-websocket/', api_views.realtime_websocket_api, name='realtime_websocket_api'),
    path('realtime-test/', api_views.realtime_test_api, name='realtime_test_api'),
]