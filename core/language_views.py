from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import AIAssistant


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def switch_language(request):
    """Switch language preference for the user's assistant"""
    try:
        data = json.loads(request.body)
        language = data.get('language', 'en')
        
        if language not in ['en', 'ms']:
            return JsonResponse({'error': 'Invalid language'}, status=400)
        
        # Get or create assistant for current user
        try:
            assistant = AIAssistant.objects.get(user=request.user)
            assistant.preferred_language = language
            assistant.save()
            
            language_names = {'en': 'English', 'ms': 'Bahasa Malaysia'}
            
            return JsonResponse({
                'success': True,
                'language': language,
                'language_name': language_names[language],
                'message': f'Language switched to {language_names[language]}'
            })
            
        except AIAssistant.DoesNotExist:
            return JsonResponse({'error': 'No assistant found for user'}, status=404)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_current_language(request):
    """Get current language preference"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        language_names = {'en': 'English', 'ms': 'Bahasa Malaysia'}
        
        return JsonResponse({
            'language': assistant.preferred_language,
            'language_name': language_names.get(assistant.preferred_language, 'English')
        })
        
    except AIAssistant.DoesNotExist:
        return JsonResponse({
            'language': 'en',
            'language_name': 'English'
        })
