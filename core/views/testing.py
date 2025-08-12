import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse

from ..models import AIAssistant
from ..services import ChatService


@login_required
def test_chat_view(request):
    """Test chat functionality"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        
        # Check subscription limits
        profile = request.user.profile
        profile.reset_monthly_usage_if_needed()
        
        if not profile.can_make_api_request():
            messages.error(request, f'You have reached your monthly API request limit ({profile.monthly_api_limit}). Please upgrade your subscription to continue using this feature.')
            return redirect('dashboard')
        
        if profile.has_token_limit_exceeded():
            messages.error(request, f'You have reached your monthly token limit ({profile.monthly_token_limit}). Please upgrade your subscription to continue using this feature.')
            return redirect('dashboard')
        
        if request.method == 'POST':
            data = json.loads(request.body)
            message = data.get('message', '')
            session_id = data.get('session_id')
            language = data.get('language', 'auto')  # Get language preference
            
            # Double-check limits before processing
            if not profile.can_make_api_request():
                return JsonResponse({
                    'error': 'API limit exceeded',
                    'message': f'You have reached your monthly API request limit ({profile.monthly_api_limit}). Please upgrade your subscription.',
                    'status': 'error'
                }, status=429)
            
            chat_service = ChatService(assistant)
            # Set language preference on chat service
            chat_service.preferred_language = language
            session_id, response = chat_service.process_message(message, session_id)
            
            return JsonResponse({
                'session_id': str(session_id),
                'response': response,
                'status': 'success'
            })
        
        return render(request, 'core/test_chat.html', {'assistant': assistant})
        
    except AIAssistant.DoesNotExist:
        return redirect('business_type_selection')


@login_required
def test_realtime_voice_view(request):
    """Test realtime voice functionality with OpenAI Realtime API"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        
        # Check subscription limits
        profile = request.user.profile
        profile.reset_monthly_usage_if_needed()
        
        if not profile.can_make_api_request():
            messages.error(request, f'You have reached your monthly API request limit ({profile.monthly_api_limit}). Please upgrade your subscription to continue using this feature.')
            return redirect('dashboard')
        
        if profile.has_token_limit_exceeded():
            messages.error(request, f'You have reached your monthly token limit ({profile.monthly_token_limit}). Please upgrade your subscription to continue using this feature.')
            return redirect('dashboard')
        
        return render(request, 'core/test_realtime_voice.html', {'assistant': assistant})
        
    except AIAssistant.DoesNotExist:
        return redirect('business_type_selection')