import re
import uuid
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def validate_api_key(api_key):
    """Validate API key format"""
    if not api_key:
        raise ValidationError("API key is required")
    
    # Check if it's a valid UUID format
    try:
        uuid.UUID(api_key)
    except ValueError:
        raise ValidationError("API key must be a valid UUID format")
    
    return api_key


def validate_assistant_access(user, assistant_id):
    """Validate that user can access the assistant"""
    from ..models import AIAssistant
    
    try:
        assistant = AIAssistant.objects.get(id=assistant_id)
    except AIAssistant.DoesNotExist:
        raise ValidationError("Assistant not found")
    
    # Check ownership
    if assistant.user != user and not (user.is_staff or user.is_superuser):
        raise ValidationError("Access denied: Not your assistant")
    
    return assistant


def validate_file_upload(uploaded_file):
    """Validate uploaded file for knowledge base"""
    if not uploaded_file:
        return True  # Optional file
    
    # Check file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB in bytes
    if uploaded_file.size > max_size:
        raise ValidationError(f"File size too large. Maximum size is {max_size // (1024*1024)}MB")
    
    # Check file extension
    allowed_extensions = ['.txt', '.pdf', '.docx', '.doc']
    file_name = uploaded_file.name.lower()
    
    if not any(file_name.endswith(ext) for ext in allowed_extensions):
        raise ValidationError(f"File type not supported. Allowed types: {', '.join(allowed_extensions)}")
    
    return True


def validate_widget_config(config_data):
    """Validate widget configuration data"""
    errors = {}
    
    # Required fields
    required_fields = ['widget_title', 'welcome_message']
    for field in required_fields:
        if not config_data.get(field, '').strip():
            errors[field] = f"{field.replace('_', ' ').title()} is required"
    
    # Validate colors (hex format)
    color_fields = ['primary_color', 'secondary_color']
    hex_pattern = re.compile(r'^#[0-9A-Fa-f]{6}$')
    
    for field in color_fields:
        color = config_data.get(field, '')
        if color and not hex_pattern.match(color):
            errors[field] = f"{field.replace('_', ' ').title()} must be a valid hex color (e.g., #007bff)"
    
    # Validate position
    valid_positions = ['bottom-right', 'bottom-left', 'top-right', 'top-left']
    position = config_data.get('widget_position', '')
    if position and position not in valid_positions:
        errors['widget_position'] = f"Position must be one of: {', '.join(valid_positions)}"
    
    # Validate language
    valid_languages = ['auto', 'en', 'ms']
    language = config_data.get('voice_language', '')
    if language and language not in valid_languages:
        errors['voice_language'] = f"Language must be one of: {', '.join(valid_languages)}"
    
    if errors:
        raise ValidationError(errors)
    
    return True


def validate_session_id(session_id):
    """Validate session ID format"""
    if not session_id:
        return True  # Optional
    
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise ValidationError("Session ID must be a valid UUID format")
    
    return True


def validate_message_content(content):
    """Validate chat message content"""
    if not content or not content.strip():
        raise ValidationError("Message content cannot be empty")
    
    # Check message length
    max_length = 4000  # characters
    if len(content) > max_length:
        raise ValidationError(f"Message too long. Maximum length is {max_length} characters")
    
    # Basic content validation (no harmful scripts)
    dangerous_patterns = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'on\w+\s*=',
    ]
    
    content_lower = content.lower()
    for pattern in dangerous_patterns:
        if re.search(pattern, content_lower, re.IGNORECASE | re.DOTALL):
            raise ValidationError("Message contains potentially harmful content")
    
    return True


def validate_subscription_plan(plan_name):
    """Validate subscription plan name"""
    from ..models import SubscriptionPlan
    
    if not plan_name:
        raise ValidationError("Subscription plan is required")
    
    try:
        plan = SubscriptionPlan.objects.get(name=plan_name, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        raise ValidationError("Invalid or inactive subscription plan")
    
    return plan


def validate_business_type(business_type_id):
    """Validate business type ID"""
    from ..models import BusinessType
    
    if not business_type_id:
        raise ValidationError("Business type is required")
    
    try:
        business_type = BusinessType.objects.get(id=business_type_id)
    except BusinessType.DoesNotExist:
        raise ValidationError("Invalid business type")
    
    return business_type


def validate_qna_data(qnas_data):
    """Validate Q&A data structure"""
    if not qnas_data:
        return True  # Optional
    
    if not isinstance(qnas_data, list):
        raise ValidationError("Q&A data must be a list")
    
    for i, qna in enumerate(qnas_data):
        if not isinstance(qna, dict):
            raise ValidationError(f"Q&A item {i+1} must be a dictionary")
        
        if not qna.get('question', '').strip():
            raise ValidationError(f"Q&A item {i+1}: Question is required")
        
        if not qna.get('answer', '').strip():
            raise ValidationError(f"Q&A item {i+1}: Answer is required")
        
        # Check length limits
        if len(qna['question']) > 500:
            raise ValidationError(f"Q&A item {i+1}: Question too long (max 500 characters)")
        
        if len(qna['answer']) > 2000:
            raise ValidationError(f"Q&A item {i+1}: Answer too long (max 2000 characters)")
    
    return True