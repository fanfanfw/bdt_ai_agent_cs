# API package - import all API endpoints to maintain compatibility
from .widget import widget_chat_api, widget_voice_api, widget_status_api
from .chat import *
from .voice import *

# Maintain backward compatibility
__all__ = [
    'widget_chat_api',
    'widget_voice_api', 
    'widget_status_api',
]