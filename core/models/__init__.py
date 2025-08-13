# Models package - import all models to maintain compatibility
from .user import RegularUserManager, BusinessType, UserProfile
from .subscription import SubscriptionPlan, ApiUsageLog
from .assistant import AIAssistant, QnA
from .knowledge import KnowledgeBase
from .chat import ChatSession, ChatMessage

# Import signals to ensure they are registered
from . import signals

# Maintain backward compatibility
# WidgetConfiguration REMOVED - using simple CDN widget instead
__all__ = [
    'RegularUserManager',
    'BusinessType', 
    'UserProfile',
    'SubscriptionPlan',
    'ApiUsageLog',
    'AIAssistant',
    'QnA',
    'KnowledgeBase', 
    'ChatSession',
    'ChatMessage',
]