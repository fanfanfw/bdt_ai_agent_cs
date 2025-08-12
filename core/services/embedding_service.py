import json
import os
import math
import hashlib
from datetime import datetime
import PyPDF2
import docx
import io

from .openai_service import OpenAIService
from ..models import KnowledgeBase


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
        user_id = knowledge_item.assistant.user.id
        kb_id = knowledge_item.id
        
        # Create directory structure: embeddings/users/{user_id}/knowledge_bases/
        user_dir = os.path.join(self.embeddings_base_dir, "users", str(user_id), "knowledge_bases")
        os.makedirs(user_dir, exist_ok=True)
        
        return os.path.join(user_dir, f"{kb_id}_embeddings.json")
    
    def save_embeddings_to_file(self, knowledge_item, chunks_with_embeddings):
        """Save embeddings to JSON file"""
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
        KnowledgeBase.objects.filter(pk=knowledge_item.pk).update(
            embedding_file_path=file_path,
            chunks_count=len(chunks_with_embeddings),
            status='completed'
        )
        
        print(f"Saved embeddings to: {file_path}")
        return file_path
    
    def _generate_content_hash(self, knowledge_item):
        """Generate hash of content for change detection"""
        content = self.extract_text_content(knowledge_item)
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def load_embeddings_from_file(self, knowledge_item):
        """Load embeddings from JSON file with content validation"""
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