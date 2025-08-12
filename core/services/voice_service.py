import json
import uuid
import threading
import time

from .openai_service import OpenAIService
from .embedding_service import EmbeddingService
from .chat_service import ChatService
from ..models import ChatSession, ChatMessage, ApiUsageLog


class VoiceTranscriptService:
    """Service untuk menyimpan transcript dari realtime voice sessions"""
    
    def __init__(self, assistant):
        self.assistant = assistant
    
    def create_voice_session(self, source='test_voice_realtime'):
        """Create new voice session for transcript storage"""
        return ChatSession.objects.create(
            assistant=self.assistant,
            openai_thread_id=None,  # Voice sessions don't use OpenAI threads
            source=source
        )
    
    def save_transcript(self, session, user_transcript=None, assistant_response=None):
        """Save voice transcript to database"""
        try:
            # Save user transcript if available
            if user_transcript and user_transcript.strip():
                ChatMessage.objects.create(
                    session=session,
                    message_type='user',
                    content=user_transcript,
                    is_voice=True
                )
            
            # Save assistant response if available
            if assistant_response and assistant_response.strip():
                ChatMessage.objects.create(
                    session=session,
                    message_type='assistant', 
                    content=assistant_response,
                    is_voice=True
                )
                
            return True
        except Exception as e:
            print(f"Error saving voice transcript: {e}")
            return False
    
    def get_session_history(self, session_id):
        """Get voice session history"""
        try:
            session = ChatSession.objects.get(
                session_id=session_id,
                assistant=self.assistant
            )
            messages = ChatMessage.objects.filter(
                session=session
            ).order_by('created_at')
            
            return {
                'session': session,
                'messages': [
                    {
                        'type': msg.message_type,
                        'content': msg.content,
                        'timestamp': msg.created_at,
                        'is_voice': msg.is_voice
                    }
                    for msg in messages
                ]
            }
        except ChatSession.DoesNotExist:
            return None


class RealtimeVoiceService:
    def __init__(self, assistant):
        self.assistant = assistant
        self.openai_service = OpenAIService()
        self.embedding_service = EmbeddingService()
        self.chat_service = ChatService(assistant)
        self.transcript_service = VoiceTranscriptService(assistant)
        self.websocket = None
        self.session_id = None
        self.voice_session = None  # Database session for transcript storage
        self.current_user_transcript = ""
        self.current_assistant_response = ""

    def safe_send_to_consumer(self, message):
        """Safely send message to Django consumer with error handling"""
        if not self.django_consumer:
            return
            
        # Check if consumer is disconnected
        if hasattr(self.django_consumer, 'is_disconnected') and self.django_consumer.is_disconnected:
            print("Django consumer is disconnected, skipping message")
            return
            
        try:
            import asyncio
            import threading
            
            def send_message():
                try:
                    # Double check consumer status before sending
                    if hasattr(self.django_consumer, 'is_disconnected') and self.django_consumer.is_disconnected:
                        print("Django consumer disconnected during send, aborting")
                        return
                        
                    # Check if consumer is still connected
                    if not hasattr(self.django_consumer, 'channel_layer') or not self.django_consumer.channel_layer:
                        print("Django consumer channel layer is missing, skipping message")
                        return
                        
                    # Check if the consumer's scope is still active
                    if hasattr(self.django_consumer, 'scope') and self.django_consumer.scope.get('client') is None:
                        print("Django consumer scope is closed, skipping message")
                        return
                    
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        new_loop.run_until_complete(
                            self.django_consumer.send(text_data=json.dumps(message))
                        )
                    finally:
                        new_loop.close()
                        
                except Exception as e:
                    print(f"Failed to send message through consumer: {e}")
                    # Don't re-raise the exception to avoid crashing the thread
            
            thread = threading.Thread(target=send_message)
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            print(f"Error in safe_send_to_consumer: {e}")

    def get_voice_for_language(self, language_hint="auto"):
        """Get appropriate voice based on language preference"""
        # Use selected language first
        preferred_lang = getattr(self, 'selected_language', 'auto')
        
        # Override with hint if provided and not auto
        if language_hint != "auto":
            preferred_lang = language_hint
        
        # Supported voices: 'alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse'
        voice_mapping = {
            'ms': 'shimmer',  # Better for Malaysian/Malay pronunciation 
            'en': 'alloy',    # Good for English
            'auto': 'alloy',  # Default to alloy for auto-detect
        }
        
        return voice_mapping.get(preferred_lang, 'alloy')
    
    def create_server_websocket_connection(self, django_consumer=None, language='en'):
        """Create server-side WebSocket connection to OpenAI Realtime API"""
        try:
            import websocket
            import json as json_lib
            import threading
            import time
            import uuid
            
            self.session_id = f"ws_session_{uuid.uuid4().hex[:8]}"
            self.connection_ready = False
            self.connection_error = None
            self.selected_language = language  # Store language preference
            
            # Create database session for transcript storage
            source = 'widget_voice' if hasattr(django_consumer, '__class__') and 'Widget' in django_consumer.__class__.__name__ else 'test_voice_realtime'
            self.voice_session = self.transcript_service.create_voice_session(source)
            print(f"✅ Created voice session for transcript: {self.voice_session.session_id}")
            
            # Reset transcript accumulators
            self.current_user_transcript = ""
            self.current_assistant_response = ""
            
            # Validate and set django_consumer
            if django_consumer:
                # Check if consumer is already disconnected
                if hasattr(django_consumer, 'is_disconnected') and django_consumer.is_disconnected:
                    return {
                        "status": "error",
                        "error": "Django consumer is already disconnected"
                    }
                self.django_consumer = django_consumer
            else:
                self.django_consumer = None
            
            # WebSocket URL for server-to-server connection  
            url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
            
            # Headers for authentication
            headers = [
                f"Authorization: Bearer {self.openai_service.client.api_key}",
                "OpenAI-Beta: realtime=v1"
            ]
            
            def on_open(ws):
                print("✅ Connected to OpenAI Realtime API via WebSocket")
                
                # Get transcription language - use null for auto-detect
                transcription_lang = None  # Let Whisper auto-detect
                if getattr(self, 'selected_language', 'auto') == 'en':
                    transcription_lang = "en"
                elif getattr(self, 'selected_language', 'auto') == 'ms':
                    transcription_lang = "ms"
                # For 'auto' or any other value, we leave it as None for auto-detection
                
                voice_for_response = self.get_voice_for_language(getattr(self, 'selected_language', 'auto'))
                
                print(f"🌐 Session Language: {getattr(self, 'selected_language', 'auto')}")
                print(f"🎤 Transcription Language: {transcription_lang or 'auto-detect'}")
                print(f"🗣️ Voice Model: {voice_for_response}")
                
                # Build transcription config using OpenAI Realtime API transcription model
                transcription_config = {
                    "model": "gpt-4o-transcribe"  # Use Realtime API's transcription model, not external Whisper
                }
                if transcription_lang:
                    transcription_config["language"] = transcription_lang
                
                # Send session configuration
                session_update = {
                    "type": "session.update", 
                    "session": {
                        "instructions": self.get_realtime_instructions(),
                        "voice": voice_for_response,
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16", 
                        "input_audio_transcription": transcription_config,
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500
                        },
                        "tools": self.get_knowledge_base_tools(),
                        "tool_choice": "auto",
                        "modalities": ["text", "audio"],
                        "temperature": 0.7
                    }
                }
                ws.send(json_lib.dumps(session_update))
                print("📝 Session configuration sent")
            
            def on_message(ws, message):
                try:
                    event = json_lib.loads(message)
                    event_type = event.get('type', 'unknown')
                    print(f"📨 Received: {event_type}")
                    
                    if event_type == 'session.updated':
                        print("⚙️ Session updated successfully")
                        self.connection_ready = True
                    elif event_type == 'input_audio_buffer.speech_started':
                        print("🎤 Speech detection started")
                    elif event_type == 'input_audio_buffer.speech_stopped':
                        print("🔄 Speech ended, triggering response...")
                        # Trigger response creation when user stops speaking
                        response_trigger = {
                            "type": "response.create"
                        }
                        ws.send(json_lib.dumps(response_trigger))
                    elif event_type == 'input_audio_buffer.committed':
                        print("✅ Audio buffer committed for processing")
                    elif event_type == 'response.function_call_arguments.done':
                        # Handle function calls for knowledge base search
                        print(f"🔍 Function call: {event.get('name', 'unknown')}")
                        
                        function_name = event.get('name')
                        arguments = event.get('arguments', '{}')
                        call_id = event.get('call_id')
                        
                        if function_name == 'search_knowledge':
                            try:
                                # Call the function handler
                                result = self.handle_function_call(function_name, arguments)
                                
                                # Send function result back to OpenAI
                                function_result = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json_lib.dumps(result)
                                    }
                                }
                                ws.send(json_lib.dumps(function_result))
                                
                                # Trigger response creation
                                response_trigger = {
                                    "type": "response.create"
                                }
                                ws.send(json_lib.dumps(response_trigger))
                                
                                print(f"✅ Function call completed: {result.get('success', False)}")
                                
                            except Exception as e:
                                print(f"❌ Function call error: {e}")
                                # Send error back to OpenAI
                                error_result = {
                                    "type": "conversation.item.create", 
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json_lib.dumps({
                                            "success": False,
                                            "error": str(e),
                                            "message": "I encountered an error searching the knowledge base. Let me try to help with general information."
                                        })
                                    }
                                }
                                ws.send(json_lib.dumps(error_result))
                    elif event_type == 'response.created':
                        print("🤖 Response creation started")
                    elif event_type == 'response.output_item.added':
                        print("📝 Response output item added")
                    elif event_type == 'output_audio_buffer.started':
                        print("🔊 Output audio buffer started")
                        # Signal to start collecting audio chunks
                        if self.django_consumer:
                            message = {
                                'type': 'audio_buffer_start',
                                'response_id': event.get('response_id', ''),
                                'event_type': event_type
                            }
                            self.safe_send_to_consumer(message)
                    elif event_type == 'response.audio.done':
                        print("🔇 Response audio completed")
                        # Signal to stop collecting and start playing
                        if self.django_consumer:
                            message = {
                                'type': 'audio_buffer_complete',
                                'response_id': event.get('response_id', ''),
                                'event_type': event_type
                            }
                            self.safe_send_to_consumer(message)
                    elif event_type == 'response.audio.delta':
                        print("🔊 Audio delta received")
                        # Forward audio response to Django consumer
                        if self.django_consumer:
                            audio_data = event.get('delta', '')
                            message = {
                                'type': 'ai_audio_delta',
                                'audio': audio_data,
                                'event_type': event_type
                            }
                            self.safe_send_to_consumer(message)
                    elif event_type == 'response.audio_transcript.delta':
                        print(f"📝 Transcript delta: {event.get('delta', '')}")
                    elif event_type == 'response.audio_transcript.done':
                        transcript = event.get('transcript', '')
                        print(f"✅ Complete transcript: {transcript}")
                        
                        # Save assistant response to database
                        if transcript and self.voice_session:
                            self.current_assistant_response = transcript
                            print(f"💾 Saving assistant response to session {self.voice_session.session_id}")
                        
                        # Forward complete transcript to Django consumer
                        if self.django_consumer and transcript:
                            message = {
                                'type': 'ai_response_text',
                                'text': transcript,
                                'event_type': event_type
                            }
                            self.safe_send_to_consumer(message)
                    elif event_type == 'response.done':
                        print("✅ Response completed")
                        
                        # Save both user and assistant transcripts to database
                        if self.voice_session and (self.current_user_transcript or self.current_assistant_response):
                            success = self.transcript_service.save_transcript(
                                session=self.voice_session,
                                user_transcript=self.current_user_transcript,
                                assistant_response=self.current_assistant_response
                            )
                            if success:
                                print(f"✅ Transcripts saved to database session {self.voice_session.session_id}")
                                # Reset for next conversation turn
                                self.current_user_transcript = ""
                                self.current_assistant_response = ""
                            else:
                                print("❌ Failed to save transcripts to database")
                        
                        # Track API usage for realtime voice
                        try:
                            usage_data = event.get('response', {}).get('usage', {})
                            input_tokens = usage_data.get('input_tokens', 0)
                            output_tokens = usage_data.get('output_tokens', 0)
                            total_tokens = usage_data.get('total_tokens', 0) or (input_tokens + output_tokens)
                            
                            if total_tokens > 0:
                                # Record API usage with token count
                                profile = self.assistant.user.profile
                                profile.record_api_usage(token_count=total_tokens)
                                
                                # Log detailed API usage
                                ApiUsageLog.objects.create(
                                    user=self.assistant.user,
                                    endpoint='/ws/voice/realtime/',
                                    method='WS',
                                    tokens_used=total_tokens,
                                    status_code=200,
                                    response_time_ms=0  # WebSocket doesn't have traditional response time
                                )
                                print(f"📊 Recorded API usage: {total_tokens} tokens for user {self.assistant.user.username}")
                            else:
                                # Record API request even without token info
                                profile = self.assistant.user.profile  
                                profile.record_api_usage(token_count=0)
                                print(f"📊 Recorded API request for user {self.assistant.user.username}")
                                
                        except Exception as e:
                            print(f"❌ Error recording API usage: {e}")
                    elif event_type == 'conversation.item.input_audio_transcription.delta':
                        # Handle user input transcription delta (partial)
                        delta = event.get('delta', '')
                        print(f"👤 User transcription delta: {delta}")
                        
                        if self.django_consumer and delta:
                            message = {
                                'type': 'user_transcript_delta',
                                'delta': delta,
                                'item_id': event.get('item_id', ''),
                                'event_type': event_type
                            }
                            self.safe_send_to_consumer(message)
                    elif event_type == 'conversation.item.input_audio_transcription.completed':
                        # Handle user input transcription completion
                        transcript = event.get('transcript', '')
                        print(f"👤 User input transcribed (complete): {transcript}")
                        
                        # Save user transcript to database
                        if transcript and self.voice_session:
                            self.current_user_transcript = transcript
                            print(f"💾 Saving user transcript to session {self.voice_session.session_id}")
                        
                        if self.django_consumer and transcript:
                            message = {
                                'type': 'user_transcript',
                                'transcript': transcript,
                                'item_id': event.get('item_id', ''),
                                'event_type': event_type
                            }
                            self.safe_send_to_consumer(message)
                    elif event_type == 'conversation.item.input_audio_transcription.failed':
                        # Handle user input transcription failure
                        error = event.get('error', {})
                        print(f"❌ User transcription failed: {error}")
                        
                        if self.django_consumer:
                            message = {
                                'type': 'user_transcript_error',
                                'error': error,
                                'item_id': event.get('item_id', ''),
                                'event_type': event_type
                            }
                            self.safe_send_to_consumer(message)
                    elif event_type == 'conversation.item.created':
                        # Forward conversation events to Django consumer
                        if self.django_consumer and event.get('item'):
                            item = event['item']
                            if item.get('role') == 'assistant' and item.get('content'):
                                content_text = ""
                                for content in item['content']:
                                    if content.get('transcript'):
                                        content_text = content['transcript']
                                        break
                                
                                if content_text:
                                    message = {
                                        'type': 'ai_response_text',
                                        'text': content_text,
                                        'event_type': event_type
                                    }
                                    self.safe_send_to_consumer(message)
                    elif event_type == 'error':
                        print(f"❌ Error from OpenAI: {event}")
                        self.connection_error = event.get('message', 'Unknown error')
                        # Forward error to Django consumer
                        if self.django_consumer:
                            message = {
                                'type': 'openai_error',
                                'error': self.connection_error,
                                'event_type': event_type
                            }
                            self.safe_send_to_consumer(message)
                        
                except Exception as e:
                    print(f"Error handling message: {e}")
            
            def on_error(ws, error):
                print(f"❌ WebSocket error: {error}")
                self.connection_error = str(error)
            
            def on_close(ws, close_status_code, close_msg):
                print("🔌 WebSocket connection closed")
                self.websocket = None
                self.session_id = None
                self.connection_ready = False
                
                # Clear django_consumer reference to prevent further message sends
                if hasattr(self, 'django_consumer'):
                    self.django_consumer = None
            
            # Create WebSocket connection
            self.websocket = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Start WebSocket in separate thread
            def run_websocket():
                self.websocket.run_forever()
            
            websocket_thread = threading.Thread(target=run_websocket, daemon=True)
            websocket_thread.start()
            
            # Wait for connection to be ready (max 5 seconds)
            max_wait = 5
            wait_time = 0
            while not self.connection_ready and not self.connection_error and wait_time < max_wait:
                time.sleep(0.1)
                wait_time += 0.1
                
            if self.connection_error:
                return {
                    "status": "error",
                    "error": self.connection_error
                }
            elif self.connection_ready:
                return {
                    "status": "success",
                    "session_id": self.session_id,
                    "connection_type": "server_websocket",
                    "message": "Server-side WebSocket connection established"
                }
            else:
                return {
                    "status": "timeout",
                    "error": "Connection timeout after 5 seconds"
                }
            
        except Exception as e:
            print(f"Exception in create_server_websocket_connection: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error", 
                "error": "Failed to create WebSocket connection",
                "details": str(e)
            }

    # Due to length constraints, I'll continue with the remaining methods in the next file...
    
    def create_ephemeral_token(self):
        """Create ephemeral token for client-side WebRTC"""
        try:
            import requests
            import json as json_lib
            
            # Prepare session configuration
            session_config = {
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": self.get_voice_for_language(),  # Dynamic voice selection
                "instructions": self.get_realtime_instructions(),
                "tools": self.get_knowledge_base_tools(),
                "tool_choice": "auto",
                "modalities": ["text", "audio"],
                "temperature": 0.7
            }
            
            print(f"Creating session with config: {json_lib.dumps(session_config, indent=2)}")
            
            response = requests.post(
                "https://api.openai.com/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {self.openai_service.client.api_key}",
                    "Content-Type": "application/json"
                },
                json=session_config
            )
            
            print(f"OpenAI API Response: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            print(f"Response body: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                print(f"Parsed response data: {response_data}")
                return response_data
            else:
                print(f"Error creating ephemeral token: {response.status_code} - {response.text}")
                return {
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "status_code": response.status_code
                }
                
        except Exception as e:
            print(f"Exception creating ephemeral token: {e}")
            import traceback
            traceback.print_exc()
            return {
                "error": str(e),
                "exception": True
            }

    def get_realtime_instructions(self):
        """Get system instructions for realtime voice agent with embedded Q&A and Knowledge Base"""
        # Get language preference from selected language or assistant preference
        preferred_lang = getattr(self, 'selected_language', getattr(self.assistant, 'preferred_language', 'auto'))
        
        # Get Q&As from database (same as test_chat)
        qnas = self.assistant.qnas.all()
        qna_text = ""
        if qnas:
            qna_text = "\n\nHere are the specific Q&As for this business:\n\n"
            for qna in qnas:
                qna_text += f"Q: {qna.question}\nA: {qna.answer}\n\n"
            qna_text += "Always prioritize these Q&As when answering similar questions."
        
        # Get ALL knowledge base content (not just summary)
        knowledge_context = ""
        kb_items = self.assistant.knowledge_base.filter(status='completed')
        if kb_items:
            knowledge_context = "\n\nKnowledge Base Information:\n\n"
            for kb in kb_items:
                # Include full content (truncated if too long)
                content = kb.content[:2000] if len(kb.content) > 2000 else kb.content
                knowledge_context += f"=== {kb.title} ===\n{content}\n\n"
            knowledge_context += "Use this knowledge base information when customers ask about business-specific details, services, policies, etc."

        # Language-specific instructions
        if preferred_lang == 'ms':
            return f"""Anda adalah pembantu perkhidmatan pelanggan {self.assistant.business_type.name} yang bercakap dengan suara yang semulajadi dan berkomunikasi.

PERSONALITI & SUARA:
- Bercakap secara semula jadi dan berkomunikasi dalam BAHASA MALAYSIA sahaja
- Gunakan ungkapan Malaysia yang semula jadi, intonasi, dan frasa
- Gunakan nada yang mesra dan membantu dengan konteks budaya yang sesuai
- Beri jeda secara semula jadi dengan jeda ringkas
- Akui emosi pelanggan dan balas dengan empati
- Gunakan "awak", "saya", "boleh", "macam mana", "bagaimana" secara semula jadi

PANDUAN BAHASA:
- SENTIASA balas dalam BAHASA MALAYSIA sahaja
- Gunakan ungkapan Malaysia yang sesuai seperti "Terima kasih", "Maaf", "Baiklah", "Bagaimana"
- Bercakap seperti orang Malaysia yang membantu pelanggan

STRATEGI JAWAPAN:
1. PERTAMA: Periksa sama ada soalan sepadan dengan Q&A di bawah - ini adalah keutamaan tinggi
2. KEDUA: Cari melalui maklumat Knowledge Base untuk butiran yang berkaitan  
3. KETIGA: Gunakan pengetahuan umum tetapi sebut mereka harus sahkan dengan perniagaan
4. Sentiasa membantu dan berusaha untuk memajukan perbualan

PANDUAN PERBUALAN:
- Beri jawapan yang ringkas tetapi lengkap (perbualan suara)
- Rujuk perbualan terdahulu secara semula jadi
- Tanya soalan pengklarifikasian apabila diperlukan
- Akui emosi dan balas dengan empati{qna_text}{knowledge_context}

CONTOH RESPONS BAHASA MALAYSIA:
- "Terima kasih kerana bertanya!"
- "Maaf, saya tak faham. Boleh awak ulang semula?"
- "Baiklah, saya akan bantu awak dengan perkara ini."
- "Adakah ada lagi yang saya boleh bantu?"

Ingat: Anda sedang bercakap secara semula jadi, jadi bercakap seperti anda bercakap dengan seseorang yang berdiri di sebelah anda, dalam BAHASA MALAYSIA sahaja.
"""
        elif preferred_lang == 'auto':
            return f"""You are a {self.assistant.business_type.name} customer service assistant with multi-language capabilities.

PERSONALITY & VOICE:
- Speak naturally and conversationally  
- Detect the customer's language and respond in the SAME language they use
- Use a warm, helpful tone with appropriate cultural context
- Pace your speech naturally with brief pauses
- Acknowledge customer emotions and respond empathetically
- Be professional yet friendly in your communication style

LANGUAGE GUIDELINES:
- AUTO-DETECT the language the customer is speaking
- If customer speaks English → Respond in ENGLISH
- If customer speaks Bahasa Malaysia/Malay → Respond in BAHASA MALAYSIA
- If mixed languages are used, use the primary language of the conversation
- Adapt your cultural expressions to the detected language

RESPONSE STRATEGY:
1. FIRST: Detect the customer's language from their speech
2. SECOND: Check if the question matches any of the Q&As below - these are high priority
3. THIRD: Search through the Knowledge Base information for relevant details
4. FOURTH: Use general knowledge but mention they should verify with the business
5. Always respond in the SAME language as the customer

CONVERSATION GUIDELINES:
- Keep responses concise but complete (voice conversation)
- Reference previous conversation naturally
- Ask clarifying questions when needed in the customer's language
- Acknowledge emotions and respond empathetically{qna_text}{knowledge_context}

EXAMPLE RESPONSES:
English: "Thank you for asking!", "How can I help you today?"
Bahasa Malaysia: "Terima kasih kerana bertanya!", "Apa yang boleh saya bantu hari ini?"

Remember: You're having a natural voice conversation, so speak as you would to a person standing next to you, matching their language preference.
"""
        else:  # English
            return f"""You are a {self.assistant.business_type.name} customer service assistant speaking in a conversational, natural voice.

PERSONALITY & VOICE:
- Speak naturally and conversationally in ENGLISH ONLY
- Use a warm, helpful tone with appropriate cultural context
- Pace your speech naturally with brief pauses
- Acknowledge customer emotions and respond empathetically
- Use clear, professional English expressions

LANGUAGE GUIDELINES:
- ALWAYS respond in ENGLISH ONLY
- Use standard conversational English
- Be professional yet friendly in your communication style

RESPONSE STRATEGY:
1. FIRST: Check if the question matches any of the Q&As below - these are high priority
2. SECOND: Search through the Knowledge Base information for relevant details
3. THIRD: Use general knowledge but mention they should verify with the business
4. Always be helpful and aim to move the conversation forward

CONVERSATION GUIDELINES:
- Keep responses concise but complete (voice conversation)
- Reference previous conversation naturally
- Ask clarifying questions when needed
- Acknowledge emotions and respond empathetically{qna_text}{knowledge_context}

EXAMPLE ENGLISH RESPONSES:
- "Thank you for asking!"
- "I'm sorry, I didn't understand. Could you please repeat that?"
- "Alright, I'll help you with this matter."
- "Is there anything else I can help you with?"

Remember: You're having a natural voice conversation in ENGLISH ONLY, so speak as you would to a person standing next to you.
"""

    def get_knowledge_base_tools(self):
        """Define knowledge base search as a function tool"""
        return [
            {
                "type": "function",
                "name": "search_knowledge",
                "description": "Search the knowledge base for information relevant to the customer's question. Use this whenever customers ask about business-specific information like services, policies, hours, contact details, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The customer's question or key terms to search for in the knowledge base"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]

    def handle_function_call(self, function_name, arguments, session_id=None):
        """Handle function calls from the realtime model - Using same logic as chat service"""
        if function_name == "search_knowledge":
            try:
                args = json.loads(arguments) if isinstance(arguments, str) else arguments
                query = args.get("query", "")
                
                print(f"🔍 RAG Search called with query: '{query}'")
                
                # Step 1: Check Q&As first (same as chat service)
                qna_response = self.chat_service.check_qna_match(query)
                if qna_response:
                    print(f"✅ Found QnA match")
                    return {
                        "success": True,
                        "source": "qna",
                        "result": qna_response,
                        "query": query
                    }
                
                # Step 2: Search knowledge base with embeddings (same as chat service)
                relevant_knowledge = self.embedding_service.find_relevant_knowledge(
                    self.assistant, query, similarity_threshold=0.4
                )
                
                print(f"📊 Found {len(relevant_knowledge)} relevant chunks")
                
                if relevant_knowledge:
                    # Format knowledge for the model (same as chat service)
                    knowledge_text = self.format_knowledge_for_realtime(relevant_knowledge)
                    print(f"✅ Found knowledge base match")
                    
                    return {
                        "success": True,
                        "source": "knowledge_base",
                        "result": knowledge_text,
                        "sources": [chunk['source'] for chunk in relevant_knowledge[:3]],
                        "query": query
                    }
                else:
                    print(f"❌ No relevant information found")
                    return {
                        "success": False,
                        "source": "none",
                        "result": "I don't have specific information about that in our knowledge base. Let me help you with general information or you can contact us directly for more details.",
                        "query": query
                    }
                    
            except Exception as e:
                print(f"Error in search_knowledge function: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }
        
        return {"success": False, "error": "Unknown function"}

    def format_knowledge_for_realtime(self, relevant_knowledge):
        """Format knowledge chunks for realtime model consumption"""
        if not relevant_knowledge:
            return "No relevant information found."
        
        formatted_parts = []
        for i, chunk in enumerate(relevant_knowledge[:3]):  # Top 3 most relevant
            similarity = chunk['similarity']
            source = chunk['source']
            content = chunk['content']
            
            priority = "MOST RELEVANT" if i == 0 else f"Relevance: {similarity:.1%}"
            formatted_parts.append(f"[{priority} - {source}]\n{content}")
        
        return "\n\n---\n\n".join(formatted_parts)

    def create_session_config(self, session_id=None):
        """Create session configuration for realtime API"""
        # Get or create chat session for continuity
        chat_session = self.chat_service.get_or_create_session(session_id)
        
        # Get recent conversation for context
        conversation_context = ""
        if chat_session:
            recent_messages = ChatMessage.objects.filter(
                session=chat_session
            ).order_by('-created_at')[:6]
            
            if recent_messages:
                context_parts = []
                for msg in reversed(recent_messages):
                    role = "customer" if msg.message_type == 'user' else "assistant"
                    context_parts.append(f"{role}: {msg.content}")
                conversation_context = "\n".join(context_parts)

        instructions = self.get_realtime_instructions()
        if conversation_context:
            instructions += f"\n\nRECENT CONVERSATION CONTEXT:\n{conversation_context}\n\nUse this context to maintain conversation continuity."

        return {
            "model": "gpt-4o-realtime-preview-2024-12-17",
            "voice": self.get_voice_for_language(),  # Dynamic voice selection
            "instructions": instructions,
            "tools": self.get_knowledge_base_tools(),
            "tool_choice": "auto",
            "modalities": ["text", "audio"],
            "temperature": 0.7,
            "max_response_output_tokens": 4096,
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 200
            }
        }