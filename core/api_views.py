from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
import json
import uuid
from .models import AIAssistant
from .services import ChatService, VoiceService, EmbeddingService, RealtimeVoiceService


def get_assistant_from_api_key(api_key):
    """Get assistant from API key"""
    try:
        return AIAssistant.objects.get(api_key=api_key, is_active=True)
    except AIAssistant.DoesNotExist:
        return None


@csrf_exempt
@require_http_methods(["POST"])
def chat_api(request):
    """Chat API endpoint"""
    try:
        # Parse request
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        api_key = data.get('api_key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        
        if not api_key:
            return JsonResponse({'error': 'API key is required'}, status=401)
        
        # Get assistant
        assistant = get_assistant_from_api_key(api_key)
        if not assistant:
            return JsonResponse({'error': 'Invalid API key'}, status=401)
        
        # Process message
        chat_service = ChatService(assistant)
        session_id, response = chat_service.process_message(message, session_id)
        
        if not session_id:
            return JsonResponse({'error': 'Error processing message'}, status=500)
        
        return JsonResponse({
            'session_id': str(session_id),
            'response': response,
            'status': 'success'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def voice_chat_api(request):
    """Voice chat API endpoint"""
    try:
        api_key = request.POST.get('api_key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        session_id = request.POST.get('session_id')
        audio_file = request.FILES.get('audio')
        
        if not api_key:
            return JsonResponse({'error': 'API key is required'}, status=401)
        
        if not audio_file:
            return JsonResponse({'error': 'Audio file is required'}, status=400)
        
        # Get assistant
        assistant = get_assistant_from_api_key(api_key)
        if not assistant:
            return JsonResponse({'error': 'Invalid API key'}, status=401)
        
        # Process voice message
        voice_service = VoiceService(assistant)
        session_id, audio_response, text_response, transcribed_text = voice_service.process_voice_message(
            audio_file, session_id
        )
        
        if not session_id:
            return JsonResponse({'error': 'Error processing voice message'}, status=500)
        
        # Return audio response
        response = HttpResponse(audio_response, content_type='audio/mp3')
        response['X-Session-ID'] = str(session_id)
        response['X-Text-Response'] = text_response
        response['X-Transcribed-Text'] = transcribed_text
        return response
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def text_to_speech_api(request):
    """Text to Speech API endpoint"""
    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        api_key = data.get('api_key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not text:
            return JsonResponse({'error': 'Text is required'}, status=400)
        
        if not api_key:
            return JsonResponse({'error': 'API key is required'}, status=401)
        
        # Get assistant
        assistant = get_assistant_from_api_key(api_key)
        if not assistant:
            return JsonResponse({'error': 'Invalid API key'}, status=401)
        
        # Convert text to speech
        voice_service = VoiceService(assistant)
        audio_data = voice_service.openai_service.text_to_speech(text)
        
        if not audio_data:
            return JsonResponse({'error': 'Error generating speech'}, status=500)
        
        response = HttpResponse(audio_data, content_type='audio/mp3')
        response['Content-Disposition'] = 'attachment; filename="speech.mp3"'
        return response
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def speech_to_text_api(request):
    """Speech to Text API endpoint"""
    try:
        api_key = request.POST.get('api_key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        audio_file = request.FILES.get('audio')
        
        if not api_key:
            return JsonResponse({'error': 'API key is required'}, status=401)
        
        if not audio_file:
            return JsonResponse({'error': 'Audio file is required'}, status=400)
        
        # Get assistant
        assistant = get_assistant_from_api_key(api_key)
        if not assistant:
            return JsonResponse({'error': 'Invalid API key'}, status=401)
        
        # Convert speech to text
        voice_service = VoiceService(assistant)
        text = voice_service.openai_service.speech_to_text(audio_file)
        
        if not text:
            return JsonResponse({'error': 'Error processing audio'}, status=500)
        
        return JsonResponse({
            'text': text,
            'status': 'success'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def assistant_info_api(request):
    """Get assistant information"""
    try:
        api_key = request.GET.get('api_key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not api_key:
            return JsonResponse({'error': 'API key is required'}, status=401)
        
        # Get assistant
        assistant = get_assistant_from_api_key(api_key)
        if not assistant:
            return JsonResponse({'error': 'Invalid API key'}, status=401)
        
        return JsonResponse({
            'business_type': assistant.business_type.name,
            'qna_count': assistant.qnas.count(),
            'knowledge_base_count': assistant.knowledge_base.count(),
            'is_active': assistant.is_active,
            'created_at': assistant.created_at.isoformat(),
            'status': 'success'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


class ChatWidgetView(View):
    """Serve chat widget HTML/JS"""
    
    def get(self, request):
        api_key = request.GET.get('api_key', '')
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Chat Widget</title>
    <style>
        /* Chat Widget Styles */
        #ai-chat-widget {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 350px;
            height: 500px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            z-index: 10000;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: none;
            flex-direction: column;
        }}
        
        #ai-chat-toggle {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 60px;
            height: 60px;
            background: #30475E;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            z-index: 10001;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }}
        
        #ai-chat-toggle:hover {{
            background: #2a3d52;
            transform: scale(1.05);
        }}
        
        #ai-chat-toggle svg {{
            width: 24px;
            height: 24px;
            fill: white;
        }}
        
        .chat-header {{
            background: #30475E;
            color: white;
            padding: 16px;
            border-radius: 12px 12px 0 0;
            display: flex;
            justify-content: between;
            align-items: center;
        }}
        
        .chat-messages {{
            flex: 1;
            padding: 16px;
            overflow-y: auto;
            background: #DDDDDD;
        }}
        
        .message {{
            margin-bottom: 12px;
            display: flex;
            gap: 8px;
        }}
        
        .message.user {{
            justify-content: flex-end;
        }}
        
        .message-content {{
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            word-wrap: break-word;
        }}
        
        .message.user .message-content {{
            background: #30475E;
            color: white;
        }}
        
        .message.assistant .message-content {{
            background: white;
            color: #222831;
            border: 1px solid #ddd;
        }}
        
        .chat-input {{
            padding: 16px;
            border-top: 1px solid #ddd;
            background: white;
            border-radius: 0 0 12px 12px;
            display: flex;
            gap: 8px;
        }}
        
        .chat-input input {{
            flex: 1;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 20px;
            outline: none;
            font-size: 14px;
        }}
        
        .chat-input button {{
            padding: 12px 16px;
            background: #30475E;
            color: white;
            border: none;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .voice-button {{
            margin-left: 4px;
            background: #F05454 !important;
        }}
        
        .voice-button.recording {{
            background: #dc3545 !important;
            animation: pulse 1s infinite;
        }}
        
        @keyframes pulse {{
            0% {{ transform: scale(1); }}
            50% {{ transform: scale(1.05); }}
            100% {{ transform: scale(1); }}
        }}
        
        .typing-indicator {{
            display: flex;
            align-items: center;
            gap: 4px;
            font-style: italic;
            color: #666;
        }}
        
        .typing-dots {{
            display: flex;
            gap: 2px;
        }}
        
        .typing-dots span {{
            width: 4px;
            height: 4px;
            background: #666;
            border-radius: 50%;
            animation: typing 1.4s infinite;
        }}
        
        .typing-dots span:nth-child(2) {{ animation-delay: 0.2s; }}
        .typing-dots span:nth-child(3) {{ animation-delay: 0.4s; }}
        
        @keyframes typing {{
            0%, 60%, 100% {{ transform: translateY(0); }}
            30% {{ transform: translateY(-10px); }}
        }}
    </style>
</head>
<body>
    <!-- Chat Toggle Button -->
    <div id="ai-chat-toggle">
        <svg viewBox="0 0 24 24">
            <path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
        </svg>
    </div>
    
    <!-- Chat Widget -->
    <div id="ai-chat-widget">
        <div class="chat-header">
            <div>
                <h4 style="margin: 0; font-size: 16px;">AI Assistant</h4>
                <small style="opacity: 0.8;">How can I help you today?</small>
            </div>
            <button onclick="toggleChat()" style="background: none; border: none; color: white; cursor: pointer; font-size: 18px;">×</button>
        </div>
        
        <div class="chat-messages" id="chat-messages">
            <div class="message assistant">
                <div class="message-content">
                    Hello! I'm your AI assistant. How can I help you today?
                </div>
            </div>
        </div>
        
        <div class="chat-input">
            <input type="text" placeholder="Type your message..." id="message-input" onkeypress="handleKeyPress(event)">
            <button onclick="sendMessage()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
            </button>
            <button class="voice-button" onclick="toggleVoice()" id="voice-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2c1.1 0 2 .9 2 2v6c0 1.1-.9 2-2 2s-2-.9-2-2V4c0-1.1.9-2 2-2zm5.3 6c0 3-2.54 5.1-5.3 5.1S6.7 11 6.7 8H5c0 3.41 2.72 6.23 6 6.72V17h2v-2.28c3.28-.49 6-3.31 6-6.72h-1.7z"/>
                </svg>
            </button>
        </div>
    </div>

    <script>
        const API_KEY = '{api_key}';
        const API_BASE = '/api';
        let sessionId = null;
        let mediaRecorder = null;
        let isRecording = false;
        
        function toggleChat() {{
            const widget = document.getElementById('ai-chat-widget');
            const toggle = document.getElementById('ai-chat-toggle');
            
            if (widget.style.display === 'none' || widget.style.display === '') {{
                widget.style.display = 'flex';
                toggle.style.display = 'none';
            }} else {{
                widget.style.display = 'none';
                toggle.style.display = 'flex';
            }}
        }}
        
        function handleKeyPress(event) {{
            if (event.key === 'Enter') {{
                sendMessage();
            }}
        }}
        
        async function sendMessage() {{
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Add user message to chat
            addMessage(message, 'user');
            input.value = '';
            
            // Show typing indicator
            showTyping();
            
            try {{
                const response = await fetch(`${{API_BASE}}/chat/`, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${{API_KEY}}`
                    }},
                    body: JSON.stringify({{
                        message: message,
                        session_id: sessionId
                    }})
                }});
                
                const data = await response.json();
                
                if (data.status === 'success') {{
                    sessionId = data.session_id;
                    addMessage(data.response, 'assistant');
                }} else {{
                    addMessage('Sorry, I encountered an error. Please try again.', 'assistant');
                }}
            }} catch (error) {{
                addMessage('Sorry, I encountered an error. Please try again.', 'assistant');
            }}
            
            hideTyping();
        }}
        
        function addMessage(content, type) {{
            const messagesContainer = document.getElementById('chat-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${{type}}`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.textContent = content;
            
            messageDiv.appendChild(contentDiv);
            messagesContainer.appendChild(messageDiv);
            
            // Scroll to bottom
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }}
        
        function showTyping() {{
            const messagesContainer = document.getElementById('chat-messages');
            const typingDiv = document.createElement('div');
            typingDiv.className = 'message assistant typing-indicator';
            typingDiv.id = 'typing-indicator';
            
            typingDiv.innerHTML = `
                <div class="message-content">
                    <div class="typing-dots">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            `;
            
            messagesContainer.appendChild(typingDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }}
        
        function hideTyping() {{
            const typingIndicator = document.getElementById('typing-indicator');
            if (typingIndicator) {{
                typingIndicator.remove();
            }}
        }}
        
        async function toggleVoice() {{
            const voiceBtn = document.getElementById('voice-btn');
            
            if (!isRecording) {{
                try {{
                    const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
                    mediaRecorder = new MediaRecorder(stream);
                    const audioChunks = [];
                    
                    mediaRecorder.ondataavailable = event => {{
                        audioChunks.push(event.data);
                    }};
                    
                    mediaRecorder.onstop = async () => {{
                        const audioBlob = new Blob(audioChunks, {{ type: 'audio/wav' }});
                        await sendVoiceMessage(audioBlob);
                    }};
                    
                    mediaRecorder.start();
                    isRecording = true;
                    voiceBtn.classList.add('recording');
                    
                }} catch (error) {{
                    alert('Microphone access denied or not available');
                }}
            }} else {{
                mediaRecorder.stop();
                isRecording = false;
                voiceBtn.classList.remove('recording');
                
                // Stop all tracks
                const stream = mediaRecorder.stream;
                stream.getTracks().forEach(track => track.stop());
            }}
        }}
        
        async function sendVoiceMessage(audioBlob) {{
            showTyping();
            
            try {{
                const formData = new FormData();
                formData.append('audio', audioBlob, 'voice.wav');
                formData.append('api_key', API_KEY);
                if (sessionId) formData.append('session_id', sessionId);
                
                const response = await fetch(`${{API_BASE}}/voice-chat/`, {{
                    method: 'POST',
                    body: formData
                }});
                
                if (response.ok) {{
                    sessionId = response.headers.get('X-Session-ID');
                    const textResponse = response.headers.get('X-Text-Response');
                    
                    // Add text response to chat
                    addMessage(textResponse, 'assistant');
                    
                    // Play audio response
                    const audioData = await response.blob();
                    const audioUrl = URL.createObjectURL(audioData);
                    const audio = new Audio(audioUrl);
                    audio.play();
                    
                }} else {{
                    addMessage('Sorry, I encountered an error processing your voice message.', 'assistant');
                }}
            }} catch (error) {{
                addMessage('Sorry, I encountered an error processing your voice message.', 'assistant');
            }}
            
            hideTyping();
        }}
        
        // Initialize chat toggle
        document.getElementById('ai-chat-toggle').onclick = toggleChat;
    </script>
</body>
</html>
        """
        
        return HttpResponse(html_content, content_type='text/html')


@csrf_exempt
@require_http_methods(["POST"])
def voice_test_api(request):
    """Voice test API for internal testing (uses session-based auth)"""
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        session_id = request.POST.get('session_id')
        audio_file = request.FILES.get('audio')
        
        if not audio_file:
            return JsonResponse({'error': 'Audio file is required'}, status=400)
        
        # Get assistant for current user
        try:
            assistant = AIAssistant.objects.get(user=request.user)
        except AIAssistant.DoesNotExist:
            return JsonResponse({'error': 'No assistant found for user'}, status=404)
        
        # Process voice message
        voice_service = VoiceService(assistant)
        session_id, audio_response, text_response, transcribed_text = voice_service.process_voice_message(
            audio_file, session_id
        )
        
        if not session_id:
            return JsonResponse({'error': 'Error processing voice message'}, status=500)
        
        # Return JSON response with both audio and text
        import base64
        audio_b64 = base64.b64encode(audio_response).decode('utf-8') if audio_response else None
        
        return JsonResponse({
            'session_id': str(session_id),
            'text_response': text_response,
            'transcribed_text': transcribed_text,
            'audio_response': audio_b64,
            'status': 'success'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def voice_stt_test_api(request):
    """STT only test API for internal testing"""
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        audio_file = request.FILES.get('audio')
        
        if not audio_file:
            return JsonResponse({'error': 'Audio file is required'}, status=400)
        
        # Get assistant for current user
        try:
            assistant = AIAssistant.objects.get(user=request.user)
        except AIAssistant.DoesNotExist:
            return JsonResponse({'error': 'No assistant found for user'}, status=404)
        
        # Convert speech to text only
        voice_service = VoiceService(assistant)
        text = voice_service.openai_service.speech_to_text(audio_file)
        
        if not text:
            return JsonResponse({'error': 'Error processing audio'}, status=500)
        
        return JsonResponse({
            'transcribed_text': text,
            'status': 'success'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def realtime_session_api(request):
    """Create ephemeral token for realtime voice chat"""
    try:
        api_key = request.POST.get('api_key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        session_id = request.POST.get('session_id')
        
        if not api_key:
            return JsonResponse({'error': 'API key is required'}, status=401)
        
        # Get assistant
        assistant = get_assistant_from_api_key(api_key)
        if not assistant:
            return JsonResponse({'error': 'Invalid API key'}, status=401)
        
        # Create realtime service
        realtime_service = RealtimeVoiceService(assistant)
        
        # Create ephemeral token
        token_response = realtime_service.create_ephemeral_token()
        if not token_response:
            return JsonResponse({'error': 'Failed to create session token'}, status=500)
        
        # Get session config for additional setup
        session_config = realtime_service.create_session_config(session_id)
        
        return JsonResponse({
            'client_secret': token_response,
            'session_config': session_config,
            'status': 'success'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt  
@require_http_methods(["POST"])
def realtime_function_call_api(request):
    """Handle function calls from realtime API"""
    try:
        data = json.loads(request.body)
        function_name = data.get('function_name')
        arguments = data.get('arguments')
        session_id = data.get('session_id')
        
        # Use session authentication for internal calls
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
            
        if not function_name:
            return JsonResponse({'error': 'Function name is required'}, status=400)
        
        # Get assistant for current user
        try:
            assistant = AIAssistant.objects.get(user=request.user)
        except AIAssistant.DoesNotExist:
            return JsonResponse({'error': 'No assistant found for user'}, status=404)
        
        # Create realtime service and handle function call
        realtime_service = RealtimeVoiceService(assistant)
        result = realtime_service.handle_function_call(function_name, arguments, session_id)
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def realtime_test_api(request):
    """Realtime voice test API for internal testing"""
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        session_id = request.POST.get('session_id')
        
        # Get assistant for current user
        try:
            assistant = AIAssistant.objects.get(user=request.user)
        except AIAssistant.DoesNotExist:
            return JsonResponse({'error': 'No assistant found for user'}, status=404)
        
        # Create realtime service
        realtime_service = RealtimeVoiceService(assistant)
        
        # Create ephemeral token
        token_response = realtime_service.create_ephemeral_token()
        if not token_response:
            return JsonResponse({'error': 'Failed to create session token'}, status=500)
        
        # Check if there's an error in the token response
        if 'error' in token_response:
            return JsonResponse({
                'error': token_response.get('error', 'Failed to create session token'),
                'status': 'error'
            }, status=500)
        
        # Extract the necessary fields and ensure proper structure
        response_data = {
            'status': 'success'
        }
        
        # Add all the session data from OpenAI response
        if 'id' in token_response:
            response_data['session_id'] = token_response['id']
        if 'client_secret' in token_response:
            response_data['client_secret'] = token_response['client_secret']
        if 'model' in token_response:
            response_data['model'] = token_response['model']
        if 'voice' in token_response:
            response_data['voice'] = token_response['voice']
        if 'instructions' in token_response:
            response_data['instructions'] = token_response['instructions']
        if 'tools' in token_response:
            response_data['tools'] = token_response['tools']
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)