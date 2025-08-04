from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
import json
import base64
from .models import AIAssistant
from .services import ChatService, VoiceService


def add_cors_headers(response):
    """Add CORS headers to response for widget API"""
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


class WidgetAPIView(View):
    """Base class for widget API views with authentication"""
    
    def authenticate_request(self, request_data):
        """Authenticate widget request using API key and assistant ID"""
        api_key = request_data.get('api_key')
        assistant_id = request_data.get('assistant_id')
        
        if not api_key or not assistant_id:
            return None, "Missing API key or assistant ID"
        
        try:
            assistant = AIAssistant.objects.get(
                api_key=api_key,
                id=assistant_id
            )
            return assistant, None
        except AIAssistant.DoesNotExist:
            return None, "Invalid API key or assistant ID"


@method_decorator(csrf_exempt, name='dispatch')
class WidgetChatAPIView(WidgetAPIView):
    """Public API endpoint for widget chat functionality"""
    
    def options(self, request):
        """Handle CORS preflight"""
        response = JsonResponse({})
        return add_cors_headers(response)
    
    def post(self, request):
        try:
            # Parse request data
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST.dict()
            
            print(f"Widget Chat API - Request data: {data}")
            
            # Authenticate request
            assistant, error = self.authenticate_request(data)
            if error:
                print(f"Widget Chat API - Auth error: {error}")
                response_data = JsonResponse({
                    'status': 'error',
                    'error': error
                }, status=401)
                return add_cors_headers(response_data)
            
            # Get message and session
            message = data.get('message', '').strip()
            session_id = data.get('session_id')
            
            print(f"Widget Chat API - Message: '{message}', Session ID: '{session_id}'")
            
            if not message:
                print("Widget Chat API - Error: Empty message")
                response_data = JsonResponse({
                    'status': 'error',
                    'error': 'Message is required'
                }, status=400)
                return add_cors_headers(response_data)
            
            # Process chat message
            print(f"Widget Chat API - Processing message with assistant: {assistant.business_type.name}")
            chat_service = ChatService(assistant)
            session_id, response = chat_service.process_message(
                message=message,
                session_id=session_id,
                is_voice=False
            )
            
            print(f"Widget Chat API - Response generated: '{response[:100]}...' Session: {session_id}")
            
            if not response:
                print("Widget Chat API - Error: No response generated")
                response_data = JsonResponse({
                    'status': 'error',
                    'error': 'Failed to generate response'
                }, status=500)
                return add_cors_headers(response_data)
            
            response_data = JsonResponse({
                'status': 'success',
                'response': response,
                'session_id': str(session_id),
                'message_id': None  # Could add message tracking if needed
            })
            return add_cors_headers(response_data)
            
        except json.JSONDecodeError as e:
            print(f"Widget Chat API - JSON decode error: {e}")
            response_data = JsonResponse({
                'status': 'error',
                'error': 'Invalid JSON in request body'
            }, status=400)
            return add_cors_headers(response_data)
        except Exception as e:
            print(f"Widget Chat API - Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            response_data = JsonResponse({
                'status': 'error',
                'error': 'Internal server error'
            }, status=500)
            return add_cors_headers(response_data)


@method_decorator(csrf_exempt, name='dispatch') 
class WidgetVoiceAPIView(WidgetAPIView):
    """Public API endpoint for widget voice functionality"""
    
    def options(self, request):
        """Handle CORS preflight"""
        response = JsonResponse({})
        return add_cors_headers(response)
    
    def post(self, request):
        try:
            # Authenticate request
            assistant, error = self.authenticate_request(request.POST)
            if error:
                return JsonResponse({
                    'status': 'error',
                    'error': error
                }, status=401)
            
            # Get audio file and session
            audio_file = request.FILES.get('audio')
            session_id = request.POST.get('session_id')
            
            if not audio_file:
                return JsonResponse({
                    'status': 'error',
                    'error': 'Audio file is required'
                }, status=400)
            
            # Process voice message
            voice_service = VoiceService(assistant)
            session_id, audio_response, response_text, transcribed_text = voice_service.process_voice_message(
                audio_file=audio_file,
                session_id=session_id
            )
            
            if not response_text:
                return JsonResponse({
                    'status': 'error',
                    'error': 'Failed to process voice message'
                }, status=500)
            
            # Encode audio response as base64 for transmission
            audio_base64 = None
            if audio_response:
                audio_base64 = base64.b64encode(audio_response).decode('utf-8')
            
            return JsonResponse({
                'status': 'success',
                'transcribed_text': transcribed_text,
                'response_text': response_text,
                'audio_response': audio_base64,
                'session_id': str(session_id)
            })
            
        except Exception as e:
            print(f"Widget voice API error: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Internal server error'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class WidgetStatusAPIView(WidgetAPIView):
    """API endpoint to check widget status and configuration"""
    
    def get(self, request):
        try:
            api_key = request.GET.get('api_key')
            assistant_id = request.GET.get('assistant_id')
            
            # Authenticate request
            assistant, error = self.authenticate_request({
                'api_key': api_key,
                'assistant_id': assistant_id
            })
            if error:
                return JsonResponse({
                    'status': 'error',
                    'error': error
                }, status=401)
            
            return JsonResponse({
                'status': 'success',
                'assistant': {
                    'id': str(assistant.id),
                    'business_type': assistant.business_type.name,
                    'title': f"{assistant.business_type.name} Assistant",
                    'has_knowledge_base': assistant.knowledge_base.exists(),
                    'has_qnas': assistant.qnas.exists(),
                    'knowledge_items_count': assistant.knowledge_base.count(),
                    'qna_count': assistant.qnas.count()
                }
            })
            
        except Exception as e:
            print(f"Widget status API error: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Internal server error'
            }, status=500)


# URL patterns for widget API
widget_chat_api = WidgetChatAPIView.as_view()
widget_voice_api = WidgetVoiceAPIView.as_view()
widget_status_api = WidgetStatusAPIView.as_view()