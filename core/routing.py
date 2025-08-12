from django.urls import re_path
from .websocket import consumers

websocket_urlpatterns = [
    re_path(r'ws/voice/(?P<room_name>\w+)/$', consumers.VoiceConsumer.as_asgi()),
    re_path(r'ws/widget/voice/$', consumers.WidgetVoiceConsumer.as_asgi()),
]