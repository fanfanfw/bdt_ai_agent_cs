from django.contrib.auth.models import User


def check_user_approved(user):
    """Check if user is approved for access"""
    if not user.is_authenticated:
        return False, "User not authenticated"
    
    # Admins are always approved
    if user.is_staff or user.is_superuser:
        return True, None
    
    # Regular users need profile approval
    if not hasattr(user, 'profile'):
        return False, "User profile not found"
    
    if not user.profile.is_approved():
        status = user.profile.status
        if status == 'pending':
            return False, "Account pending approval"
        elif status == 'suspended':
            return False, "Account suspended"
        elif status == 'rejected':
            return False, "Account rejected"
        else:
            return False, "Account not approved"
    
    return True, None


def check_admin_privileges(user):
    """Check if user has admin privileges"""
    if not user.is_authenticated:
        return False, "User not authenticated"
    
    if not (user.is_staff or user.is_superuser):
        return False, "Admin privileges required"
    
    return True, None


def check_subscription_limits(user, check_api=True, check_tokens=True, token_estimate=0):
    """Check user's subscription limits"""
    approved, msg = check_user_approved(user)
    if not approved:
        return False, msg
    
    profile = user.profile
    profile.reset_monthly_usage_if_needed()
    
    # Check API request limit
    if check_api and not profile.can_make_api_request():
        return False, {
            'error': 'API limit exceeded',
            'message': f'Monthly API limit ({profile.monthly_api_limit}) reached',
            'current_usage': profile.current_month_api_requests,
            'limit': profile.monthly_api_limit,
            'type': 'api_limit'
        }
    
    # Check token limit
    if check_tokens and not profile.can_use_tokens(token_estimate):
        return False, {
            'error': 'Token limit exceeded',
            'message': f'Monthly token limit ({profile.monthly_token_limit}) would be exceeded',
            'current_usage': profile.current_month_tokens,
            'limit': profile.monthly_token_limit,
            'estimate': token_estimate,
            'type': 'token_limit'
        }
    
    return True, None


def check_assistant_ownership(user, assistant):
    """Check if user owns the assistant"""
    if not user.is_authenticated:
        return False, "User not authenticated"
    
    # Admins can access any assistant
    if user.is_staff or user.is_superuser:
        return True, None
    
    # Regular users can only access their own assistant
    if assistant.user != user:
        return False, "Access denied: Not your assistant"
    
    return True, None


def check_session_ownership(user, session):
    """Check if user owns the chat session"""
    if not user.is_authenticated:
        return False, "User not authenticated"
    
    # Admins can access any session
    if user.is_staff or user.is_superuser:
        return True, None
    
    # Regular users can only access sessions from their assistant
    if session.assistant.user != user:
        return False, "Access denied: Not your session"
    
    return True, None


def can_create_assistant(user):
    """Check if user can create a new assistant"""
    approved, msg = check_user_approved(user)
    if not approved:
        return False, msg
    
    # Check subscription limits
    current_limits = user.profile.get_current_limits()
    max_assistants = current_limits.get('max_assistants', 1)
    
    from ..models import AIAssistant
    current_count = AIAssistant.objects.filter(user=user).count()
    
    if current_count >= max_assistants:
        return False, f"Maximum assistants ({max_assistants}) reached for your subscription plan"
    
    return True, None


def can_create_knowledge_base(user):
    """Check if user can create new knowledge base items"""
    approved, msg = check_user_approved(user)
    if not approved:
        return False, msg
    
    # Check subscription limits
    current_limits = user.profile.get_current_limits()
    max_kb = current_limits.get('max_knowledge_bases', 1)
    
    from ..models import AIAssistant, KnowledgeBase
    try:
        assistant = AIAssistant.objects.get(user=user)
        current_count = KnowledgeBase.objects.filter(assistant=assistant).count()
        
        if current_count >= max_kb:
            return False, f"Maximum knowledge base items ({max_kb}) reached for your subscription plan"
    except AIAssistant.DoesNotExist:
        pass  # No assistant yet, so no knowledge base items
    
    return True, None