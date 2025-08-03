from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import AIAssistant, KnowledgeBase, BusinessType
from core.services import EmbeddingService
import os
import time


class Command(BaseCommand):
    help = 'Test embedding synchronization with knowledge base changes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            default=1,
            help='User ID to test with (default: 1)',
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        
        try:
            user = User.objects.get(id=user_id)
            self.stdout.write(f"Testing with user: {user.username}")
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"User with ID {user_id} does not exist")
            )
            return

        # Get or create assistant
        try:
            assistant = AIAssistant.objects.get(user=user)
        except AIAssistant.DoesNotExist:
            # Create test business type if needed
            business_type, created = BusinessType.objects.get_or_create(
                name="Test Business",
                defaults={"description": "Test business for embedding sync"}
            )
            
            # Create test assistant
            assistant = AIAssistant.objects.create(
                user=user,
                business_type=business_type,
                system_instructions="Test assistant for embedding synchronization"
            )
            self.stdout.write("Created test assistant")

        embedding_service = EmbeddingService()

        # Test 1: Create new knowledge base item
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 1: Creating new knowledge base item")
        self.stdout.write("="*50)
        
        kb_item = KnowledgeBase.objects.create(
            assistant=assistant,
            title="Test Knowledge Item",
            content="This is test content for embedding synchronization. It contains multiple sentences to test chunking. The embedding system should automatically process this content."
        )
        
        self.stdout.write(f"Created KB item: {kb_item.title}")
        self.stdout.write(f"Initial status: {kb_item.status}")
        
        # Wait for background processing
        self.stdout.write("Waiting for embedding generation...")
        time.sleep(3)
        
        # Refresh from database
        kb_item.refresh_from_db()
        self.stdout.write(f"Status after creation: {kb_item.status}")
        self.stdout.write(f"Embedding file path: {kb_item.embedding_file_path}")
        self.stdout.write(f"Chunks count: {kb_item.chunks_count}")
        
        if kb_item.embedding_file_path and os.path.exists(kb_item.embedding_file_path):
            self.stdout.write(self.style.SUCCESS("✓ Embedding file created successfully"))
        else:
            self.stdout.write(self.style.ERROR("✗ Embedding file not found"))

        # Test 2: Update content and check embedding refresh
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 2: Updating knowledge base content")
        self.stdout.write("="*50)
        
        old_embedding_path = kb_item.embedding_file_path
        self.stdout.write(f"Old embedding path: {old_embedding_path}")
        
        # Update content
        new_content = "This is UPDATED test content for embedding synchronization. The content has been significantly changed. This should trigger automatic embedding regeneration with new chunks and vectors."
        kb_item.content = new_content
        kb_item.save()
        
        self.stdout.write("Updated KB content")
        self.stdout.write("Waiting for embedding regeneration...")
        time.sleep(3)
        
        # Refresh from database
        kb_item.refresh_from_db()
        self.stdout.write(f"Status after update: {kb_item.status}")
        self.stdout.write(f"New embedding file path: {kb_item.embedding_file_path}")
        self.stdout.write(f"New chunks count: {kb_item.chunks_count}")
        
        # Check if old embedding file was deleted
        if old_embedding_path and not os.path.exists(old_embedding_path):
            self.stdout.write(self.style.SUCCESS("✓ Old embedding file deleted"))
        else:
            self.stdout.write(self.style.WARNING("? Old embedding file still exists"))
        
        # Check if new embedding file was created
        if kb_item.embedding_file_path and os.path.exists(kb_item.embedding_file_path):
            self.stdout.write(self.style.SUCCESS("✓ New embedding file created"))
        else:
            self.stdout.write(self.style.ERROR("✗ New embedding file not found"))

        # Test 3: Test embedding validation
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 3: Testing embedding validation")
        self.stdout.write("="*50)
        
        outdated_items = embedding_service.validate_embeddings_integrity(assistant)
        self.stdout.write(f"Found {len(outdated_items)} outdated embeddings")
        
        if len(outdated_items) == 0:
            self.stdout.write(self.style.SUCCESS("✓ All embeddings are up to date"))
        else:
            self.stdout.write(self.style.WARNING(f"Found {len(outdated_items)} outdated embeddings"))
            for item in outdated_items:
                self.stdout.write(f"  - {item.title}")

        # Test 4: Test knowledge search
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 4: Testing knowledge search")
        self.stdout.write("="*50)
        
        search_query = "test content embedding"
        relevant_chunks = embedding_service.find_relevant_knowledge(
            assistant, search_query, similarity_threshold=0.3
        )
        
        self.stdout.write(f"Search query: '{search_query}'")
        self.stdout.write(f"Found {len(relevant_chunks)} relevant chunks")
        
        for i, chunk in enumerate(relevant_chunks):
            self.stdout.write(f"  {i+1}. Similarity: {chunk['similarity']:.3f}")
            self.stdout.write(f"     Source: {chunk['source']}")
            self.stdout.write(f"     Content: {chunk['content'][:100]}...")

        # Test 5: Delete knowledge base item
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 5: Deleting knowledge base item")
        self.stdout.write("="*50)
        
        embedding_path_to_check = kb_item.embedding_file_path
        self.stdout.write(f"Embedding path to check: {embedding_path_to_check}")
        
        # Delete the item
        kb_item.delete()
        self.stdout.write("Deleted KB item")
        
        # Check if embedding file was cleaned up
        if embedding_path_to_check and not os.path.exists(embedding_path_to_check):
            self.stdout.write(self.style.SUCCESS("✓ Embedding file deleted on KB deletion"))
        else:
            self.stdout.write(self.style.ERROR("✗ Embedding file not deleted"))

        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write("Embedding synchronization tests completed!")
        self.stdout.write("Check the results above to verify that:")
        self.stdout.write("1. Embeddings are created automatically for new KB items")
        self.stdout.write("2. Embeddings are refreshed when content changes")
        self.stdout.write("3. Old embedding files are cleaned up")
        self.stdout.write("4. Embedding files are deleted when KB items are deleted")
        self.stdout.write("5. Knowledge search works with the updated embeddings")