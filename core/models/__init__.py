# Models package - import all models to maintain compatibility
from .user import RegularUserManager, BusinessType, UserProfile
from .subscription import SubscriptionPlan, ApiUsageLog
from .assistant import AIAssistant, QnA
from .knowledge import KnowledgeBase, WidgetConfiguration
from .chat import ChatSession, ChatMessage

# Import signals to ensure they are registered
from . import signals

# Maintain backward compatibility
__all__ = [
    'RegularUserManager',
    'BusinessType', 
    'UserProfile',
    'SubscriptionPlan',
    'ApiUsageLog',
    'AIAssistant',
    'QnA',
    'KnowledgeBase', 
    'WidgetConfiguration',
    'ChatSession',
    'ChatMessage',
]