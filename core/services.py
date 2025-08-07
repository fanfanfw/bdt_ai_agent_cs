import openai
import json
import numpy as np
import os
import hashlib
import math
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
        # Update status using direct SQL to avoid signal triggers
        from .models import KnowledgeBase
        KnowledgeBase.objects.filter(pk=knowledge_item.pk).update(status='processing')
        
        # Extract text content
        text_content = self.extract_text_content(knowledge_item)
        
        if not text_content.strip():
            print(f"No content found for {knowledge_item.title}")
            KnowledgeBase.objects.filter(pk=knowledge_item.pk).update(status='error')
            return
        
        KnowledgeBase.objects.filter(pk=knowledge_item.pk).update(status='embedding')
        
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
            KnowledgeBase.objects.filter(pk=knowledge_item.pk).update(status='error')

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
                "knowledge_base_id": str(knowledge_item.id),
                "content_hash": self._generate_content_hash(knowledge_item)
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
        
        # Update knowledge base record using direct SQL to avoid signal triggers
        from .models import KnowledgeBase
        KnowledgeBase.objects.filter(pk=knowledge_item.pk).update(
            embedding_file_path=file_path,
            chunks_count=len(chunks_with_embeddings),
            status='completed'
        )
        
        print(f"Saved embeddings to: {file_path}")
        return file_path
    
    def _generate_content_hash(self, knowledge_item):
        """Generate hash of content for change detection"""
        import hashlib
        
        content = self.extract_text_content(knowledge_item)
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def load_embeddings_from_file(self, knowledge_item):
        """Load embeddings from JSON file with content validation"""
        import json
        import os
        
        if not knowledge_item.embedding_file_path or not os.path.exists(knowledge_item.embedding_file_path):
            return None
            
        try:
            with open(knowledge_item.embedding_file_path, 'r', encoding='utf-8') as f:
                embedding_data = json.load(f)
                
            # Validate if embeddings are still valid (content hasn't changed)
            if 'metadata' in embedding_data:
                stored_hash = embedding_data['metadata'].get('content_hash')
                current_hash = self._generate_content_hash(knowledge_item)
                
                if stored_hash and stored_hash != current_hash:
                    print(f"Content hash mismatch for {knowledge_item.title}, embeddings may be outdated")
                    # Could trigger refresh here if needed
                    
            return embedding_data
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
                try:
                    os.remove(knowledge_item.embedding_file_path)
                    print(f"Deleted old embedding file: {knowledge_item.embedding_file_path}")
                except Exception as e:
                    print(f"Error deleting old embedding file: {e}")
        
        # Clear database embeddings and file path
        knowledge_item.embeddings = {}
        knowledge_item.embedding_file_path = ""
        knowledge_item.chunks_count = 0
        knowledge_item.status = 'processing'
        knowledge_item.save()
        
        # Generate new embeddings
        self.generate_embeddings_for_item(knowledge_item)
    
    def delete_embeddings_for_item(self, knowledge_item):
        """Delete all embeddings for a knowledge base item"""
        print(f"Deleting embeddings for {knowledge_item.title}")
        
        # Delete embedding file
        if knowledge_item.embedding_file_path:
            import os
            if os.path.exists(knowledge_item.embedding_file_path):
                try:
                    os.remove(knowledge_item.embedding_file_path)
                    print(f"Deleted embedding file: {knowledge_item.embedding_file_path}")
                except Exception as e:
                    print(f"Error deleting embedding file: {e}")
        
        # Clear database embeddings
        knowledge_item.embeddings = {}
        knowledge_item.embedding_file_path = ""
        knowledge_item.chunks_count = 0
        knowledge_item.status = 'uploading'
        
        # Use update to avoid triggering signals
        from .models import KnowledgeBase
        KnowledgeBase.objects.filter(pk=knowledge_item.pk).update(
            embeddings=knowledge_item.embeddings,
            embedding_file_path=knowledge_item.embedding_file_path,
            chunks_count=knowledge_item.chunks_count,
            status=knowledge_item.status
        )

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
    
    def validate_embeddings_integrity(self, assistant):
        """Validate that all embeddings are up to date"""
        knowledge_items = assistant.knowledge_base.all()
        outdated_items = []
        
        for item in knowledge_items:
            if item.status == 'completed' and item.embedding_file_path:
                embedding_data = self.load_embeddings_from_file(item)
                if embedding_data and 'metadata' in embedding_data:
                    stored_hash = embedding_data['metadata'].get('content_hash')
                    current_hash = self._generate_content_hash(item)
                    
                    if stored_hash != current_hash:
                        outdated_items.append(item)
                        print(f"Found outdated embeddings for: {item.title}")
                        
        return outdated_items
    
    def refresh_outdated_embeddings(self, assistant):
        """Refresh all outdated embeddings for an assistant"""
        outdated_items = self.validate_embeddings_integrity(assistant)
        
        for item in outdated_items:
            print(f"Refreshing outdated embeddings for: {item.title}")
            self.refresh_embeddings_for_item(item)
            
        return len(outdated_items)

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
        # Validate embeddings integrity before returning results
        if not relevant_chunks:
            # Check if embeddings might be outdated
            outdated_count = self.refresh_outdated_embeddings(assistant)
            if outdated_count > 0:
                print(f"Refreshed {outdated_count} outdated embeddings, you may want to retry the search")
        
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
                response = self.generate_ai_response(message, relevant_knowledge, session)
                response_source = "kb+llm"
            else:
                # Step 4: Fallback to pure LLM response
                response = self.generate_ai_response(message, [], session)
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

    def get_chat_instructions(self, user_message=""):
        """Get adaptive system instructions for chat based on message language"""
        # Check if we have a preferred language set (from UI selection)
        preferred_lang = getattr(self, 'preferred_language', 'auto')
        
        # If auto-detect, use language detection
        if preferred_lang == 'auto':
            detected_lang = self.detect_language(user_message)
        else:
            detected_lang = preferred_lang
        
        # Debug logging (can be enabled for troubleshooting)
        # print(f"🌐 Chat Language Settings:")
        # print(f"   Preferred Language: {preferred_lang}")
        # print(f"   Final Language: {detected_lang}")
        
        # Get Q&As from database
        qnas = self.assistant.qnas.all()
        qna_text = ""
        if qnas:
            qna_text = "\n\nHere are the specific Q&As for this business:\n\n"
            for qna in qnas:
                qna_text += f"Q: {qna.question}\nA: {qna.answer}\n\n"
            qna_text += "Always prioritize these Q&As when answering similar questions."
        
        # Get knowledge base context
        knowledge_context = ""
        kb_items = self.assistant.knowledge_base.filter(status='completed')
        if kb_items:
            knowledge_context = "\n\nKnowledge Base Information:\n\n"
            for kb in kb_items:
                content = kb.content[:2000] if len(kb.content) > 2000 else kb.content
                knowledge_context += f"=== {kb.title} ===\n{content}\n\n"
            knowledge_context += "Use this knowledge base information when customers ask about business-specific details, services, policies, etc."

        # Return language-specific instructions like voice realtime
        if detected_lang == 'ms':
            return f"""Anda adalah pembantu perkhidmatan pelanggan {self.assistant.business_type.name} secara bertulis.

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
- Beri jawapan yang lengkap dan terperinci
- Rujuk perbualan terdahulu secara semula jadi
- Tanya soalan pengklarifikasian apabila diperlukan
- Gunakan nada yang mesra dan membantu{qna_text}{knowledge_context}

CONTOH RESPONS BAHASA MALAYSIA:
- "Terima kasih kerana bertanya!"
- "Maaf, saya tak faham. Boleh awak jelaskan lagi?"
- "Baiklah, saya akan bantu awak dengan perkara ini."
- "Adakah ada lagi yang saya boleh bantu?"

Ingat: Balas dalam BAHASA MALAYSIA sahaja, tidak kira bahasa soalan pelanggan."""
        else:
            return f"""You are a {self.assistant.business_type.name} customer service assistant with multi-language capabilities.

LANGUAGE GUIDELINES:
- AUTO-DETECT the language the customer is using
- If customer writes in English → Respond in ENGLISH
- If customer writes in Bahasa Malaysia/Malay → Respond in BAHASA MALAYSIA  
- If mixed languages are used, use the primary language of the conversation
- Adapt your cultural expressions to the detected language

RESPONSE STRATEGY:
1. FIRST: Detect the customer's language from their message
2. SECOND: Check if the question matches any of the Q&As below - these are high priority
3. THIRD: Search through the Knowledge Base information for relevant details
4. FOURTH: Use general knowledge but mention they should verify with the business
5. Always respond in the SAME language as the customer

CONVERSATION GUIDELINES:
- Keep responses complete and detailed
- Reference previous conversation naturally
- Ask clarifying questions when needed in the customer's language
- Use a warm, helpful tone with appropriate cultural context{qna_text}{knowledge_context}

EXAMPLE RESPONSES:
English: "Thank you for asking!", "How can I help you today?"
Bahasa Malaysia: "Terima kasih kerana bertanya!", "Apa yang boleh saya bantu hari ini?"

Remember: Always respond in the SAME language as the customer's message."""

    def detect_language(self, message):
        """Improved language detection for Malaysian and English"""
        if not message:
            return 'en'
            
        message_lower = message.lower().strip()
        
        # First check for strong English indicators
        english_indicators = {
            'what', 'how', 'when', 'where', 'why', 'who', 'which', 'whose',
            'the', 'and', 'or', 'but', 'with', 'for', 'from', 'to', 'at', 'by',
            'are', 'is', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might',
            'your', 'you', 'i', 'we', 'they', 'he', 'she', 'it', 'my', 'our', 'their',
            'business', 'service', 'services', 'hours', 'contact', 'many', 'much', 'some',
            'about', 'company', 'property', 'properties', 'agent', 'agents', 'luxury'
        }
        
        # Common Malaysian/Malay words (more specific and exclusive)
        malay_words = {
            'apa', 'yang', 'ini', 'itu', 'saya', 'awak', 'kamu', 'dengan', 'untuk', 'dari', 'dalam',
            'boleh', 'tidak', 'tak', 'ada', 'tiada', 'macam', 'mana', 'bagaimana', 'kenapa', 'bila',
            'kami', 'mereka', 'dia', 'terima', 'kasih', 'maaf', 'tolong', 'pun', 'lagi', 'juga',
            'sudah', 'belum', 'akan', 'sedang', 'buat', 'kerja', 'rumah', 'sekolah', 'universiti',
            'malaysia', 'melayu', 'ringgit', 'sen', 'berapa', 'banyak', 'sikit', 'ramai',
            'ejen', 'hartanah', 'mewah', 'perkhidmatan', 'waktu', 'operasi', 'perniagaan',
            'masa', 'hari', 'minggu', 'bulan', 'tahun', 'pagi', 'tengah', 'petang', 'malam'
        }
        
        # Remove punctuation for better word matching
        import re
        cleaned_message = re.sub(r'[^\w\s]', ' ', message_lower)
        words = cleaned_message.split()
        
        if not words:
            return 'en'
        
        malay_count = sum(1 for word in words if word in malay_words)
        english_count = sum(1 for word in words if word in english_indicators)
        
        # Debug logging (uncomment for troubleshooting)
        # print(f"🔍 Language Detection Debug:")
        # print(f"   Original message: '{message}'")
        # print(f"   Cleaned words: {words}")
        # print(f"   Malay words found: {[word for word in words if word in malay_words]}")
        # print(f"   English words found: {[word for word in words if word in english_indicators]}")
        # print(f"   Malay count: {malay_count}/{len(words)} = {(malay_count/len(words)*100):.1f}%")
        # print(f"   English count: {english_count}/{len(words)} = {(english_count/len(words)*100):.1f}%")
        
        # Strong Malay phrases always return Malay
        malay_phrases = [
            'terima kasih', 'boleh tak', 'macam mana', 'tak ada', 'ada tak',
            'apa khabar', 'berapa ramai', 'boleh tolong', 'saya nak', 'awak ada',
            'berapa harga', 'bagaimana nak', 'apa waktu', 'waktu operasi'
        ]
        for phrase in malay_phrases:
            if phrase in message_lower:
                return 'ms'
        
        # If we have strong English indicators and no/few Malay words, it's English
        if english_count > 0 and malay_count == 0:
            return 'en'
        
        # Compare ratios - if English ratio is higher, it's English
        if len(words) > 2:  # Only for longer messages
            malay_ratio = malay_count / len(words)
            english_ratio = english_count / len(words)
            
            if english_ratio > malay_ratio and english_ratio >= 0.3:
                return 'en'
            elif malay_ratio >= 0.2:  # Lower threshold for Malay
                return 'ms'
        
        # For short messages, be more conservative - default to English unless clear Malay
        if len(words) <= 2 and malay_count == 0:
            return 'en'
        elif malay_count > 0:
            return 'ms'        
        return 'en'

    def generate_ai_response(self, message, relevant_knowledge, session=None):
        """Generate AI response using OpenAI with improved RAG context handling"""
        # Get conversation history for context
        conversation_context = ""
        if session:
            recent_messages = ChatMessage.objects.filter(
                session=session
            ).order_by('-created_at')[:6]  # Last 6 messages (3 exchanges)
            
            if recent_messages:
                conversation_context = "\n\nRecent conversation history:\n"
                for msg in reversed(recent_messages):
                    role = "Customer" if msg.message_type == 'user' else "Assistant"
                    conversation_context += f"{role}: {msg.content}\n"
        
        if relevant_knowledge:
            # Sort chunks by similarity (highest first) to prioritize most relevant
            sorted_knowledge = sorted(relevant_knowledge, key=lambda x: x['similarity'], reverse=True)
            
            # Use knowledge base context from chunks
            context_parts = []
            for i, chunk in enumerate(sorted_knowledge):
                content = chunk['content']
                similarity = chunk['similarity']
                source = chunk['source']
                priority = "MOST RELEVANT" if i == 0 else f"Relevance: {similarity:.1%}"
                context_parts.append(f"[{priority} - Source: {source}]\n{content}")
            
            context = "\n\nRelevant information from knowledge base (sorted by relevance):\n" + "\n\n---\n\n".join(context_parts)
            
            prompt = f"""
            Answer the customer's question using the provided knowledge base information and conversation history for context.

            Customer Question: {message}
            {context}
            {conversation_context}

            CRITICAL INSTRUCTIONS:
            1. Consider the conversation history to understand the context and maintain continuity
            2. The customer is asking: "{message}"
            3. Look for the EXACT information that answers this specific question
            4. If they ask "how many" or "how much", look for NUMBERS and QUANTITIES
            5. If they ask about "agents", look for agent counts or specializations  
            6. If they ask about "luxury properties", look for luxury-specific information
            7. IGNORE unrelated information like commission rates, fees, or other services
            8. Use ONLY the information that directly answers their question
            9. Be specific and cite the exact numbers/details found
            10. Reference previous conversation if relevant to the current question

            What does the knowledge base say about their specific question?"""
        else:
            # No knowledge base context, use general response
            prompt = f"""
            Please answer the following customer question based on your general knowledge. Since no specific business information was found, provide a helpful general response and suggest the customer contact the business directly for specific details.

            Customer Question: {message}
            {conversation_context}

            Instructions:
            1. Consider the conversation history to maintain context and continuity
            2. Provide a helpful, general response
            3. Acknowledge that specific business details should be verified
            4. Maintain a professional customer service tone
            5. Suggest appropriate next steps for the customer
            """

        try:
            response = self.openai_service.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.get_chat_instructions(message)},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            # Track token usage
            tokens_used = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            if tokens_used > 0:
                # Update user profile with token usage
                profile = self.assistant.user.profile
                profile.record_api_usage(token_count=tokens_used)
                
                # Log detailed API usage
                from .models import ApiUsageLog
                ApiUsageLog.objects.create(
                    user=self.assistant.user,
                    endpoint='/api/chat/',
                    method='POST',
                    tokens_used=tokens_used,
                    status_code=200
                )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating AI response: {e}")
            return "I apologize, but I'm having trouble processing your request right now. Please try again later or contact our support team."




class RealtimeVoiceService:
    def __init__(self, assistant):
        self.assistant = assistant
        self.openai_service = OpenAIService()
        self.embedding_service = EmbeddingService()
        self.chat_service = ChatService(assistant)
        self.websocket = None
        self.session_id = None

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
        
        # Original function definition (keeping for reference):
        # return [
        #     {
        #         "type": "function",
        #         "name": "search_knowledge",
        #         "description": "Search the knowledge base for information relevant to the customer's question. Use this whenever customers ask about business-specific information like services, policies, hours, contact details, etc.",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "query": {
        #                     "type": "string",
        #                     "description": "The customer's question or key terms to search for in the knowledge base"
        #                 }
        #             },
        #             "required": ["query"]
        #         }
        #     }
        # ]

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