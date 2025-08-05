from django.urls import path
from . import api_views

urlpatterns = [
    path('chat/', api_views.chat_api, name='chat_api'),
    path('voice-chat/', api_views.voice_chat_api, name='voice_chat_api'),
    path('text-to-speech/', api_views.text_to_speech_api, name='text_to_speech_api'),
    path('speech-to-text/', api_views.speech_to_text_api, name='speech_to_text_api'),
    path('assistant-info/', api_views.assistant_info_api, name='assistant_info_api'),
    path('widget/', api_views.ChatWidgetView.as_view(), name='chat_widget'),
    path('voice-test/', api_views.voice_test_api, name='voice_test_api'),
    path('voice-stt-test/', api_views.voice_stt_test_api, name='voice_stt_test_api'),
    # Realtime Voice API endpoints
    path('realtime-session/', api_views.realtime_session_api, name='realtime_session_api'),
    path('realtime-function-call/', api_views.realtime_function_call_api, name='realtime_function_call_api'),
    path('realtime-test/', api_views.realtime_test_api, name='realtime_test_api'),
]