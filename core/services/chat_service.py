import re
from .openai_service import OpenAIService
from .embedding_service import EmbeddingService
from ..models import ChatSession, ChatMessage, ApiUsageLog


class ChatService:
    def __init__(self, assistant):
        self.assistant = assistant
        self.openai_service = OpenAIService()
        self.embedding_service = EmbeddingService()

    def get_or_create_session(self, session_id=None, source='test_chat'):
        """Get or create chat session"""
        if session_id:
            try:
                return ChatSession.objects.get(session_id=session_id, assistant=self.assistant)
            except ChatSession.DoesNotExist:
                pass

        # Create new session
        thread = None
        openai_thread_id = None
        
        # Only create OpenAI thread for non-voice sources
        if source not in ['test_voice_realtime', 'widget_voice']:
            thread = self.openai_service.create_thread()
            if thread:
                openai_thread_id = thread.id
        
        return ChatSession.objects.create(
            assistant=self.assistant,
            openai_thread_id=openai_thread_id,
            source=source
        )

    def process_message(self, message, session_id=None, is_voice=False, source='test_chat'):
        """Process user message and generate response with improved flow"""
        
        session = self.get_or_create_session(session_id, source)
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

        # Return language-specific instructions
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
        cleaned_message = re.sub(r'[^\w\s]', ' ', message_lower)
        words = cleaned_message.split()
        
        if not words:
            return 'en'
        
        malay_count = sum(1 for word in words if word in malay_words)
        english_count = sum(1 for word in words if word in english_indicators)
        
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