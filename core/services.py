import openai
import json
import numpy as np
from django.conf import settings
from sklearn.metrics.pairwise import cosine_similarity
from .models import KnowledgeBase, ChatSession, ChatMessage, AIAssistant
import PyPDF2
import docx
import io


class OpenAIService:
    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate_embeddings(self, text):
        """Generate embeddings for text using OpenAI"""
        try:
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            return None

    def create_assistant(self, name, instructions, tools=None):
        """Create OpenAI Assistant"""
        try:
            return self.client.beta.assistants.create(
                name=name,
                instructions=instructions,
                model="gpt-4o-mini",
                tools=tools or []
            )
        except Exception as e:
            print(f"Error creating assistant: {e}")
            return None

    def create_thread(self):
        """Create OpenAI Thread"""
        try:
            return self.client.beta.threads.create()
        except Exception as e:
            print(f"Error creating thread: {e}")
            return None

    def send_message(self, thread_id, message):
        """Send message to OpenAI thread"""
        try:
            self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message
            )
            
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=self.assistant_id
            )
            
            return run
        except Exception as e:
            print(f"Error sending message: {e}")
            return None

    def get_response(self, thread_id, run_id):
        """Get response from OpenAI"""
        try:
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id
            )
            
            if run.status == 'completed':
                messages = self.client.beta.threads.messages.list(
                    thread_id=thread_id
                )
                return messages.data[0].content[0].text.value
            
            return None
        except Exception as e:
            print(f"Error getting response: {e}")
            return None

    def text_to_speech(self, text):
        """Convert text to speech using OpenAI TTS"""
        try:
            response = self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text
            )
            return response.content
        except Exception as e:
            print(f"Error with TTS: {e}")
            return None

    def speech_to_text(self, audio_file):
        """Convert speech to text using OpenAI Whisper"""
        try:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
            return transcript.text
        except Exception as e:
            print(f"Error with STT: {e}")
            return None


class EmbeddingService:
    def __init__(self):
        self.openai_service = OpenAIService()
        self.chunk_size = 1000  # Characters per chunk
        self.chunk_overlap = 200  # Overlap between chunks
        self.embeddings_base_dir = "media/embeddings"
    
    def chunk_text(self, text, chunk_size=None, overlap=None):
        """Split text into overlapping chunks for better embeddings"""
        if chunk_size is None:
            chunk_size = self.chunk_size
        if overlap is None:
            overlap = self.chunk_overlap
            
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence endings near the chunk boundary
                for i in range(min(100, chunk_size // 4)):  # Look back up to 100 chars
                    if end - i > start and text[end - i - 1] in '.!?':
                        end = end - i
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position with overlap
            start = end - overlap
            if start >= len(text):
                break
                
        return chunks

    def process_knowledge_base(self, assistant):
        """Process all knowledge base items for an assistant and generate embeddings"""
        knowledge_items = assistant.knowledge_base.all()
        
        for item in knowledge_items:
            if not item.embeddings:
                self.generate_embeddings_for_item(item)

    def generate_embeddings_for_item(self, knowledge_item):
        """Generate embeddings for a specific knowledge base item"""
        knowledge_item.status = 'processing'
        knowledge_item.save()
        
        # Extract text content
        text_content = self.extract_text_content(knowledge_item)
        
        if not text_content.strip():
            print(f"No content found for {knowledge_item.title}")
            knowledge_item.status = 'error'
            knowledge_item.save()
            return
        
        knowledge_item.status = 'embedding'
        knowledge_item.save()
        
        # Split into chunks
        chunks = self.chunk_text(text_content)
        print(f"Processing {len(chunks)} chunks for {knowledge_item.title}")
        
        # Generate embeddings for each chunk
        chunk_embeddings = []
        for i, chunk in enumerate(chunks):
            embedding_vector = self.openai_service.generate_embeddings(chunk)
            
            if embedding_vector:
                chunk_embeddings.append({
                    'chunk_id': i,
                    'text': chunk,
                    'vector': embedding_vector,
                    'length': len(chunk)
                })
            else:
                print(f"Failed to generate embedding for chunk {i} of {knowledge_item.title}")
        
        # Save embeddings to file
        if chunk_embeddings:
            file_path = self.save_embeddings_to_file(knowledge_item, chunk_embeddings)
            print(f"Saved {len(chunk_embeddings)} embeddings for {knowledge_item.title}")
        else:
            print(f"No embeddings generated for {knowledge_item.title}")
            knowledge_item.status = 'error'
            knowledge_item.save()

    def get_embedding_file_path(self, knowledge_item):
        """Get the file path for storing embeddings"""
        import os
        user_id = knowledge_item.assistant.user.id
        kb_id = knowledge_item.id
        
        # Create directory structure: embeddings/users/{user_id}/knowledge_bases/
        user_dir = os.path.join(self.embeddings_base_dir, "users", str(user_id), "knowledge_bases")
        os.makedirs(user_dir, exist_ok=True)
        
        return os.path.join(user_dir, f"{kb_id}_embeddings.json")
    
    def save_embeddings_to_file(self, knowledge_item, chunks_with_embeddings):
        """Save embeddings to JSON file"""
        import json
        import os
        from datetime import datetime
        
        file_path = self.get_embedding_file_path(knowledge_item)
        
        # Create embedding data structure matching the old system
        embedding_data = {
            "metadata": {
                "file_name": knowledge_item.title,
                "file_type": "manual" if not knowledge_item.file_path else knowledge_item.file_path.name.split('.')[-1],
                "total_chunks": len(chunks_with_embeddings),
                "embedding_model": knowledge_item.embedding_model,
                "processed_at": datetime.now().isoformat(),
                "user_id": knowledge_item.assistant.user.id,
                "knowledge_base_id": str(knowledge_item.id)
            },
            "chunks": []
        }
        
        for chunk_data in chunks_with_embeddings:
            embedding_data["chunks"].append({
                "chunk_index": chunk_data['chunk_id'],
                "text": chunk_data['text'],
                "char_count": chunk_data['length'],
                "embedding": chunk_data['vector'],
                "sentences_count": len(chunk_data['text'].split('.'))
            })
        
        # Save to file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(embedding_data, f, ensure_ascii=False, indent=2)
        
        # Update knowledge base record
        knowledge_item.embedding_file_path = file_path
        knowledge_item.chunks_count = len(chunks_with_embeddings)
        knowledge_item.status = 'completed'
        knowledge_item.save()
        
        print(f"Saved embeddings to: {file_path}")
        return file_path
    
    def load_embeddings_from_file(self, knowledge_item):
        """Load embeddings from JSON file"""
        import json
        import os
        
        if not knowledge_item.embedding_file_path or not os.path.exists(knowledge_item.embedding_file_path):
            return None
            
        try:
            with open(knowledge_item.embedding_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading embeddings from {knowledge_item.embedding_file_path}: {e}")
            return None
    
    def refresh_embeddings_for_item(self, knowledge_item):
        """Refresh embeddings when content changes"""
        print(f"Refreshing embeddings for {knowledge_item.title}")
        
        # Delete old embedding file
        if knowledge_item.embedding_file_path:
            import os
            if os.path.exists(knowledge_item.embedding_file_path):
                os.remove(knowledge_item.embedding_file_path)
        
        # Clear database embeddings and file path
        knowledge_item.embeddings = {}
        knowledge_item.embedding_file_path = ""
        knowledge_item.chunks_count = 0
        knowledge_item.status = 'processing'
        knowledge_item.save()
        
        # Generate new embeddings
        self.generate_embeddings_for_item(knowledge_item)

    def extract_text_content(self, knowledge_item):
        """Extract text content from knowledge base item"""
        if knowledge_item.content:
            return knowledge_item.content
        
        if knowledge_item.file_path:
            return self.extract_file_content(knowledge_item.file_path)
        
        return ""

    def extract_file_content(self, file_path):
        """Extract content from uploaded files"""
        try:
            file_extension = file_path.name.split('.')[-1].lower()
            
            if file_extension == 'txt':
                return file_path.read().decode('utf-8')
            
            elif file_extension == 'pdf':
                return self.extract_pdf_content(file_path)
            
            elif file_extension in ['docx', 'doc']:
                return self.extract_docx_content(file_path)
            
            else:
                return f"Unsupported file type: {file_extension}"
                
        except Exception as e:
            print(f"Error extracting file content: {e}")
            return f"Error processing file: {file_path.name}"

    def extract_pdf_content(self, file_path):
        """Extract text from PDF file"""
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_path.read()))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            print(f"Error extracting PDF content: {e}")
            return "Error processing PDF file"

    def extract_docx_content(self, file_path):
        """Extract text from DOCX file"""
        try:
            doc = docx.Document(io.BytesIO(file_path.read()))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            print(f"Error extracting DOCX content: {e}")
            return "Error processing DOCX file"

    def cosine_similarity(self, vec1, vec2):
        """Calculate cosine similarity between two vectors"""
        import math
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(a * a for a in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0
        
        return dot_product / (magnitude1 * magnitude2)

    def find_relevant_knowledge(self, assistant, query, similarity_threshold=0.4):
        """Find relevant knowledge base chunks using file-based search"""
        query_embedding = self.openai_service.generate_embeddings(query)
        if not query_embedding:
            return []

        relevant_chunks = []
        knowledge_items = assistant.knowledge_base.filter(status='completed')

        for item in knowledge_items:
            # Try file-based embeddings first
            embeddings_data = self.load_embeddings_from_file(item)
            
            if embeddings_data and 'chunks' in embeddings_data:
                # File-based format
                for chunk in embeddings_data['chunks']:
                    if 'embedding' in chunk:
                        similarity = self.cosine_similarity(query_embedding, chunk['embedding'])
                        
                        if similarity >= similarity_threshold:
                            relevant_chunks.append({
                                'item': item,
                                'chunk_id': chunk['chunk_index'],
                                'similarity': similarity,
                                'content': chunk['text'],
                                'source': f"{item.title} (chunk {chunk['chunk_index'] + 1})"
                            })
            else:
                # Fallback to database embeddings (legacy)
                embeddings_data = item.embeddings
                
                if 'data' in embeddings_data and embeddings_data.get('object') == 'list':
                    # Database chunked format
                    for chunk_data in embeddings_data['data']:
                        if 'vector' in chunk_data:
                            similarity = self.cosine_similarity(query_embedding, chunk_data['vector'])
                            
                            if similarity >= similarity_threshold:
                                relevant_chunks.append({
                                    'item': item,
                                    'chunk_id': chunk_data['chunk_id'],
                                    'similarity': similarity,
                                    'content': chunk_data['text'],
                                    'source': f"{item.title} (chunk {chunk_data['chunk_id'] + 1})"
                                })

        # Sort by similarity and return top chunks
        relevant_chunks.sort(key=lambda x: x['similarity'], reverse=True)
        return relevant_chunks[:5]  # Return top 5 most relevant chunks


class ChatService:
    def __init__(self, assistant):
        self.assistant = assistant
        self.openai_service = OpenAIService()
        self.embedding_service = EmbeddingService()

    def get_or_create_session(self, session_id=None):
        """Get or create chat session"""
        if session_id:
            try:
                return ChatSession.objects.get(session_id=session_id, assistant=self.assistant)
            except ChatSession.DoesNotExist:
                pass

        # Create new session
        thread = self.openai_service.create_thread()
        if thread:
            return ChatSession.objects.create(
                assistant=self.assistant,
                openai_thread_id=thread.id
            )
        return None

    def process_message(self, message, session_id=None, is_voice=False):
        """Process user message and generate response with improved flow"""
        session = self.get_or_create_session(session_id)
        if not session:
            return None, "Error creating chat session"

        # Save user message
        user_msg = ChatMessage.objects.create(
            session=session,
            message_type='user',
            content=message,
            is_voice=is_voice
        )

        response_source = "llm"  # Track response source for debugging
        
        # Step 1: Check Q&As first (exact matches and high similarity)
        qna_response = self.check_qna_match(message)
        if qna_response:
            response = qna_response
            response_source = "qna"
        else:
            # Step 2: Search knowledge base with embeddings
            relevant_knowledge = self.embedding_service.find_relevant_knowledge(
                self.assistant, message, similarity_threshold=0.4  # Lower threshold for better recall
            )
            
            if relevant_knowledge:
                # Step 3: Generate response using LLM with knowledge base context
                response = self.generate_ai_response(message, relevant_knowledge)
                response_source = "kb+llm"
            else:
                # Step 4: Fallback to pure LLM response
                response = self.generate_ai_response(message, [])
                response_source = "llm"

        # Save assistant response
        assistant_msg = ChatMessage.objects.create(
            session=session,
            message_type='assistant',
            content=response,
            is_voice=False
        )

        return session.session_id, response

    def check_qna_match(self, message):
        """Check if message matches any Q&A with improved matching logic"""
        qnas = self.assistant.qnas.all()
        message_lower = message.lower().strip()
        
        # First pass: Check for exact question matches
        for qna in qnas:
            question_lower = qna.question.lower().strip()
            if message_lower == question_lower:
                return qna.answer
        
        # Second pass: Check for high similarity (>70% keyword overlap)
        best_match = None
        best_score = 0
        
        for qna in qnas:
            question_lower = qna.question.lower()
            
            # Get meaningful words (>3 chars, exclude common words)
            stop_words = {'what', 'how', 'when', 'where', 'why', 'who', 'the', 'and', 'or', 'but', 'you', 'your', 'are', 'is', 'do', 'does', 'can', 'will', 'would', 'should', 'about', 'with', 'for', 'from', 'to', 'in', 'on', 'at', 'by'}
            
            message_words = set(word for word in message_lower.split() 
                               if len(word) > 3 and word not in stop_words)
            question_words = set(word for word in question_lower.split() 
                                if len(word) > 3 and word not in stop_words)
            
            if not message_words or not question_words:
                continue
                
            # Calculate similarity score (intersection over union)
            intersection = len(message_words & question_words)
            union = len(message_words | question_words)
            similarity = intersection / union if union > 0 else 0
            
            # Require high similarity (70%) and at least 2 matching keywords
            if similarity >= 0.7 and intersection >= 2 and similarity > best_score:
                best_score = similarity
                best_match = qna.answer
        
        return best_match

    def generate_ai_response(self, message, relevant_knowledge):
        """Generate AI response using OpenAI with improved RAG context handling"""
        if relevant_knowledge:
            # Use knowledge base context from chunks
            context_parts = []
            for chunk in relevant_knowledge:
                content = chunk['content']
                similarity = chunk['similarity']
                source = chunk['source']
                context_parts.append(f"[Source: {source}, Relevance: {similarity:.1%}]\n{content}")
            
            context = "\n\nRelevant information from knowledge base:\n" + "\n\n---\n\n".join(context_parts)
            
            prompt = f"""
            Based on the system instructions and the relevant knowledge chunks provided below, please answer the customer's question accurately and professionally.

            Customer Question: {message}
            {context}

            Instructions:
            1. Use the provided knowledge base information as your primary source
            2. Synthesize information from multiple chunks if relevant
            3. If the knowledge base doesn't fully answer the question, combine it with general knowledge
            4. Be specific and helpful, citing the most relevant information
            5. Maintain a professional customer service tone
            6. If you're not certain about something, mention that the customer should verify with the business
            """
        else:
            # No knowledge base context, use general response
            prompt = f"""
            Please answer the following customer question based on your general knowledge and the system instructions. Since no specific business information was found, provide a helpful general response and suggest the customer contact the business directly for specific details.

            Customer Question: {message}

            Instructions:
            1. Provide a helpful, general response
            2. Acknowledge that specific business details should be verified
            3. Maintain a professional customer service tone
            4. Suggest appropriate next steps for the customer
            """

        try:
            response = self.openai_service.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.assistant.system_instructions},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating AI response: {e}")
            return "I apologize, but I'm having trouble processing your request right now. Please try again later or contact our support team."


class VoiceService:
    def __init__(self, assistant):
        self.assistant = assistant
        self.openai_service = OpenAIService()
        self.chat_service = ChatService(assistant)

    def process_voice_message(self, audio_file, session_id=None):
        """Process voice message: STT -> Chat -> TTS"""
        # Speech to Text
        text = self.openai_service.speech_to_text(audio_file)
        if not text:
            return None, None, "Error processing audio"

        # Process text message
        session_id, response_text = self.chat_service.process_message(
            text, session_id, is_voice=True
        )

        # Text to Speech
        audio_response = self.openai_service.text_to_speech(response_text)

        return session_id, audio_response, response_text