import json
import websocket
import threading
import base64
import asyncio
import struct
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from urllib.parse import parse_qs

class VoiceConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.openai_websocket = None
        self.voice_service = None
        self.is_voice_active = False
        self.session_id = None
        self.websocket_thread = None
        self.message_queue = asyncio.Queue()
        self.is_disconnected = False
        
    async def connect(self):
        # Check authentication
        if not self.scope["user"].is_authenticated:
            await self.close()
            return
            
        # Get user's assistant
        try:
            from ..models import AIAssistant
            self.assistant = await database_sync_to_async(
                AIAssistant.objects.get
            )(user=self.scope["user"])
        except Exception:
            await self.close()
            return
            
        # Accept connection
        await self.accept()
        
        # Initialize voice service lazily
        self.voice_service = None
        
        # Send initial connection status
        await self.send(text_data=json.dumps({
            'type': 'connection_status',
            'status': 'connected',
            'message': 'Server-side WebSocket connected. Voice is INACTIVE.'
        }))

    async def disconnect(self, close_code):
        # Set flag to indicate disconnection
        self.is_disconnected = True
        
        # Close OpenAI WebSocket connection
        if self.openai_websocket:
            self.openai_websocket.close()
            
        # Stop voice service
        if self.voice_service:
            self.voice_service.django_consumer = None  # Clear reference to prevent further message sends

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                data = json.loads(text_data)
                message_type = data.get('type')
                
                if message_type == 'start_voice':
                    language = data.get('language', 'en')  # Default to English
                    await self.start_voice_session(language)
                elif message_type == 'stop_voice':
                    await self.stop_voice_session()
                elif message_type == 'audio_data':
                    await self.process_audio_data(data.get('audio'))
                    
            elif bytes_data:
                # Handle binary audio data
                await self.process_binary_audio(bytes_data)
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing message: {str(e)}'
            }))

    async def start_voice_session(self, language='en'):
        """Start voice session - connect to OpenAI WebSocket"""
        try:
            # Only start if not already active
            if self.is_voice_active:
                return
            
            # Check subscription limits before starting voice session
            user = self.scope["user"]
            profile = await database_sync_to_async(lambda: user.profile)()
            
            # Reset monthly usage if needed
            await database_sync_to_async(profile.reset_monthly_usage_if_needed)()
            
            # Check API request limit
            can_make_request = await database_sync_to_async(profile.can_make_api_request)()
            if not can_make_request:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'You have reached your monthly API request limit ({profile.monthly_api_limit}). Please upgrade your subscription to continue using this feature.',
                    'error_code': 'API_LIMIT_EXCEEDED'
                }))
                return
            
            # Check token limit
            token_limit_exceeded = await database_sync_to_async(profile.has_token_limit_exceeded)()
            if token_limit_exceeded:
                await self.send(text_data=json.dumps({
                    'type': 'error', 
                    'message': f'You have reached your monthly token limit ({profile.monthly_token_limit}). Please upgrade your subscription to continue using this feature.',
                    'error_code': 'TOKEN_LIMIT_EXCEEDED'
                }))
                return
                
            # Initialize voice service if not done yet
            if not self.voice_service:
                from ..services import RealtimeVoiceService
                self.voice_service = RealtimeVoiceService(self.assistant)
            
            # Set language preference in voice service
            self.voice_service.selected_language = language
            
            # Create WebSocket connection to OpenAI with consumer reference
            result = await database_sync_to_async(
                self.voice_service.create_server_websocket_connection
            )(django_consumer=self, language=language)
            
            if result.get('status') == 'success':
                self.is_voice_active = True
                self.session_id = result.get('session_id')
                
                # Setup message handling from OpenAI WebSocket
                await self.setup_openai_message_handler()
                
                await self.send(text_data=json.dumps({
                    'type': 'voice_started',
                    'session_id': self.session_id,
                    'message': 'Voice is now ACTIVE on server'
                }))
                
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Failed to start voice: {result.get("error")}'
                }))
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error starting voice: {str(e)}'
            }))

    async def stop_voice_session(self):
        """Stop voice session"""
        try:
            if self.is_voice_active:
                # Close OpenAI WebSocket
                if self.voice_service and self.voice_service.websocket:
                    self.voice_service.websocket.close()
                    
                self.is_voice_active = False
                self.session_id = None
                
                await self.send(text_data=json.dumps({
                    'type': 'voice_stopped',
                    'message': 'Voice is now INACTIVE on server'
                }))
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error', 
                'message': f'Error stopping voice: {str(e)}'
            }))

    async def process_audio_data(self, audio_data):
        """Process audio data from client and forward to OpenAI"""
        try:
            if not self.is_voice_active or not self.voice_service or not self.voice_service.websocket:
                return
                
            # Convert base64 audio to binary
            if isinstance(audio_data, str):
                audio_bytes = base64.b64decode(audio_data)
            else:
                audio_bytes = audio_data
                
            # Send audio to OpenAI WebSocket
            await self.send_to_openai({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_bytes).decode('utf-8')
            })
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing audio: {str(e)}'
            }))
    
    async def process_binary_audio(self, audio_bytes):
        """Process binary audio data from client"""
        try:
            if not self.is_voice_active or not self.voice_service or not self.voice_service.websocket:
                return
                
            # Send audio to OpenAI WebSocket
            await self.send_to_openai({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_bytes).decode('utf-8')
            })
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing binary audio: {str(e)}'
            }))
    
    async def setup_openai_message_handler(self):
        """Setup message handler to receive events from OpenAI WebSocket"""
        async def message_handler():
            while self.is_voice_active and self.voice_service and self.voice_service.websocket:
                try:
                    await asyncio.sleep(0.1)  # Check for messages periodically
                    # This would be implemented to handle messages from OpenAI WebSocket
                    # For now we'll rely on the WebSocket's on_message handler
                except Exception as e:
                    print(f"Error in message handler: {e}")
                    break
        
        asyncio.create_task(message_handler())
    
    async def send_to_openai(self, message):
        """Send message to OpenAI WebSocket"""
        try:
            if self.voice_service and self.voice_service.websocket:
                # Send message to OpenAI WebSocket in a thread-safe way
                def send_message():
                    if self.voice_service.websocket:
                        self.voice_service.websocket.send(json.dumps(message))
                
                # Execute in thread since WebSocket is synchronous
                await asyncio.get_event_loop().run_in_executor(None, send_message)
                
        except Exception as e:
            print(f"Error sending to OpenAI: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error sending to OpenAI: {str(e)}'
            }))


class WidgetVoiceConsumer(AsyncWebsocketConsumer):
    """WebSocket Consumer for widget realtime voice functionality"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.voice_service = None
        self.is_voice_active = False
        self.session_id = None
        self.assistant = None
    
    async def connect(self):
        # Get API key and assistant ID from query parameters
        query_params = parse_qs(self.scope["query_string"].decode())
        api_key = query_params.get('api_key', [None])[0]
        assistant_id = query_params.get('assistant_id', [None])[0]
        
        if not api_key or not assistant_id:
            await self.close()
            return
        
        # Authenticate using API key and assistant ID
        try:
            from ..models import AIAssistant
            self.assistant = await database_sync_to_async(
                AIAssistant.objects.get
            )(api_key=api_key, id=assistant_id)
        except Exception:
            await self.close()
            return
        
        # Check user quota before allowing connection
        profile = await database_sync_to_async(lambda: self.assistant.user.profile)()
        await database_sync_to_async(profile.reset_monthly_usage_if_needed)()
        
        can_make_request = await database_sync_to_async(profile.can_make_api_request)()
        token_limit_exceeded = await database_sync_to_async(profile.has_token_limit_exceeded)()
        
        if not can_make_request or token_limit_exceeded:
            await self.send(text_data=json.dumps({
                'type': 'quota_exceeded',
                'error': 'API or token limit exceeded',
                'message': 'Your monthly quota has been reached. Please upgrade your subscription.'
            }))
            await self.close()
            return
        
        # Accept connection
        await self.accept()
        
        # Send connection status
        await self.send(text_data=json.dumps({
            'type': 'connection_status',
            'status': 'connected',
            'message': 'Widget voice connection established'
        }))
    
    async def disconnect(self, close_code):
        # Cleanup voice service
        if self.voice_service:
            self.voice_service.django_consumer = None
        
        self.is_voice_active = False
    
    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                data = json.loads(text_data)
                message_type = data.get('type')
                
                if message_type == 'start_voice':
                    language = data.get('language', 'auto')
                    await self.start_voice_session(language)
                elif message_type == 'stop_voice':
                    await self.stop_voice_session()
                elif message_type == 'audio_data':
                    await self.process_audio_data(data.get('audio'))
                    
            elif bytes_data:
                await self.process_binary_audio(bytes_data)
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing message: {str(e)}'
            }))
    
    async def start_voice_session(self, language='auto'):
        """Start voice session for widget"""
        try:
            if self.is_voice_active:
                return
            
            # Double check quota before starting
            profile = await database_sync_to_async(lambda: self.assistant.user.profile)()
            can_make_request = await database_sync_to_async(profile.can_make_api_request)()
            token_limit_exceeded = await database_sync_to_async(profile.has_token_limit_exceeded)()
            
            if not can_make_request or token_limit_exceeded:
                await self.send(text_data=json.dumps({
                    'type': 'quota_exceeded',
                    'error': 'Quota exceeded during session start',
                    'message': 'Your quota has been reached. Please upgrade your subscription.'
                }))
                return
            
            # Initialize voice service
            if not self.voice_service:
                from ..services import RealtimeVoiceService
                self.voice_service = RealtimeVoiceService(self.assistant)
            
            # Set language preference
            self.voice_service.selected_language = language
            
            # Create WebSocket connection to OpenAI
            result = await database_sync_to_async(
                self.voice_service.create_server_websocket_connection
            )(django_consumer=self, language=language)
            
            if result.get('status') == 'success':
                self.is_voice_active = True
                self.session_id = result.get('session_id')
                
                await self.send(text_data=json.dumps({
                    'type': 'voice_started',
                    'session_id': self.session_id,
                    'message': 'Widget voice session started'
                }))
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Failed to start voice: {result.get("error")}'
                }))
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error starting voice session: {str(e)}'
            }))
    
    async def stop_voice_session(self):
        """Stop voice session for widget"""
        try:
            if self.is_voice_active and self.voice_service:
                if self.voice_service.websocket:
                    self.voice_service.websocket.close()
                
                self.is_voice_active = False
                self.session_id = None
                
                await self.send(text_data=json.dumps({
                    'type': 'voice_stopped',
                    'message': 'Widget voice session stopped'
                }))
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error stopping voice session: {str(e)}'
            }))
    
    async def process_audio_data(self, audio_data):
        """Process audio data from widget client"""
        try:
            if not self.is_voice_active or not self.voice_service:
                return
            
            # Convert base64 audio to binary
            if isinstance(audio_data, str):
                audio_bytes = base64.b64decode(audio_data)
            else:
                audio_bytes = audio_data
            
            # Send audio to OpenAI WebSocket
            await self.send_to_openai({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_bytes).decode('utf-8')
            })
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing audio: {str(e)}'
            }))
    
    async def process_binary_audio(self, audio_bytes):
        """Process binary audio data from widget client"""
        try:
            if not self.is_voice_active or not self.voice_service:
                return
            
            # Send audio to OpenAI WebSocket
            await self.send_to_openai({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_bytes).decode('utf-8')
            })
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing binary audio: {str(e)}'
            }))
    
    async def send_to_openai(self, message):
        """Send message to OpenAI WebSocket"""
        try:
            if self.voice_service and self.voice_service.websocket:
                def send_message():
                    if self.voice_service.websocket:
                        self.voice_service.websocket.send(json.dumps(message))
                
                await asyncio.get_event_loop().run_in_executor(None, send_message)
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error sending to OpenAI: {str(e)}'
            }))