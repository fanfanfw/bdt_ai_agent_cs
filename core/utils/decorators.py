from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse


def login_required_with_approval(function):
    """Decorator that requires login AND approved status"""
    @wraps(function)
    def wrapper(request, *args, **kwargs):
        # First check if user is logged in
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Then check if user is approved (unless admin)
        if not request.user.is_staff and not request.user.is_superuser:
            if not hasattr(request.user, 'profile') or not request.user.profile.is_approved():
                messages.error(request, 'Your account is pending approval. Please wait for admin approval.')
                return redirect('home')
        
        return function(request, *args, **kwargs)
    return wrapper


def admin_required(function):
    """Decorator that requires admin privileges"""
    @wraps(function)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'Admin privileges required.')
            return redirect('home')
        
        return function(request, *args, **kwargs)
    return wrapper


def quota_required(function):
    """Decorator that checks user quota before allowing API access"""
    @wraps(function)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has profile and is approved
        if not hasattr(request.user, 'profile') or not request.user.profile.is_approved():
            if request.content_type == 'application/json':
                return JsonResponse({'error': 'Account not approved'}, status=403)
            messages.error(request, 'Your account is not approved.')
            return redirect('home')
        
        # Check API quota
        profile = request.user.profile
        profile.reset_monthly_usage_if_needed()
        
        if not profile.can_make_api_request():
            if request.content_type == 'application/json':
                return JsonResponse({
                    'error': 'API limit exceeded',
                    'message': f'Monthly API limit ({profile.monthly_api_limit}) reached'
                }, status=429)
            messages.error(request, f'Monthly API limit ({profile.monthly_api_limit}) reached. Please upgrade your subscription.')
            return redirect('dashboard')
        
        if profile.has_token_limit_exceeded():
            if request.content_type == 'application/json':
                return JsonResponse({
                    'error': 'Token limit exceeded',
                    'message': f'Monthly token limit ({profile.monthly_token_limit}) reached'
                }, status=429)
            messages.error(request, f'Monthly token limit ({profile.monthly_token_limit}) reached. Please upgrade your subscription.')
            return redirect('dashboard')
        
        return function(request, *args, **kwargs)
    return wrapper


def api_key_required(function):
    """Decorator for API endpoints that require API key authentication"""
    @wraps(function)
    def wrapper(request, *args, **kwargs):
        from ..models import AIAssistant
        
        # Get API key and assistant ID from request
        if request.method == 'GET':
            api_key = request.GET.get('api_key')
            assistant_id = request.GET.get('assistant_id')
        else:
            if request.content_type == 'application/json':
                import json
                try:
                    data = json.loads(request.body)
                    api_key = data.get('api_key')
                    assistant_id = data.get('assistant_id')
                except:
                    api_key = None
                    assistant_id = None
            else:
                api_key = request.POST.get('api_key')
                assistant_id = request.POST.get('assistant_id')
        
        if not api_key or not assistant_id:
            return JsonResponse({
                'status': 'error',
                'error': 'API key and assistant ID required'
            }, status=401)
        
        # Validate API key and assistant ID
        try:
            assistant = AIAssistant.objects.get(api_key=api_key, id=assistant_id)
            request.assistant = assistant  # Add assistant to request
            request.api_user = assistant.user  # Add user to request
        except AIAssistant.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid API key or assistant ID'
            }, status=401)
        
        return function(request, *args, **kwargs)
    return wrapper