from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import AIAssistant, KnowledgeBase, BusinessType
from core.services import EmbeddingService
import os
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile


class Command(BaseCommand):
    help = 'Test deletion cleanup for embeddings and files'

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
                defaults={"description": "Test business for deletion testing"}
            )
            
            # Create test assistant
            assistant = AIAssistant.objects.create(
                user=user,
                business_type=business_type,
                system_instructions="Test assistant for deletion testing"
            )
            self.stdout.write("Created test assistant")

        # Test 1: Manual content deletion
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 1: Manual Content Deletion")
        self.stdout.write("="*50)
        
        # Create KB with manual content
        kb_manual = KnowledgeBase.objects.create(
            assistant=assistant,
            title="Test Manual Content",
            content="This is test manual content for deletion testing."
        )
        
        # Wait for embedding generation
        import time
        time.sleep(2)
        
        # Refresh and check
        kb_manual.refresh_from_db()
        embedding_file_path = kb_manual.embedding_file_path
        
        self.stdout.write(f"Created KB with manual content: {kb_manual.title}")
        self.stdout.write(f"Embedding file: {embedding_file_path}")
        self.stdout.write(f"File exists: {os.path.exists(embedding_file_path) if embedding_file_path else 'No file'}")
        
        # Delete the KB item
        kb_manual.delete()
        
        # Check if embedding file was deleted
        if embedding_file_path:
            embedding_exists = os.path.exists(embedding_file_path)
            if not embedding_exists:
                self.stdout.write(self.style.SUCCESS("✓ Manual content: Embedding file deleted"))
            else:
                self.stdout.write(self.style.ERROR("✗ Manual content: Embedding file still exists"))
        
        # Test 2: File upload deletion
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 2: File Upload Deletion")
        self.stdout.write("="*50)
        
        # Create a test file
        test_content = b"This is test file content for deletion testing.\nIt has multiple lines.\nFor better testing."
        test_file = SimpleUploadedFile(
            "test_document.txt",
            test_content,
            content_type="text/plain"
        )
        
        # Create KB with file upload
        kb_file = KnowledgeBase.objects.create(
            assistant=assistant,
            title="Test File Upload",
            content="This content comes from uploaded file.",
            file_path=test_file
        )
        
        # Wait for embedding generation
        time.sleep(2)
        
        # Refresh and check
        kb_file.refresh_from_db()
        embedding_file_path = kb_file.embedding_file_path
        upload_file_path = kb_file.file_path.path if kb_file.file_path else None
        
        self.stdout.write(f"Created KB with file upload: {kb_file.title}")
        self.stdout.write(f"Upload file: {upload_file_path}")
        self.stdout.write(f"Embedding file: {embedding_file_path}")
        self.stdout.write(f"Upload exists: {os.path.exists(upload_file_path) if upload_file_path else 'No file'}")
        self.stdout.write(f"Embedding exists: {os.path.exists(embedding_file_path) if embedding_file_path else 'No file'}")
        
        # Delete the KB item
        kb_file.delete()
        
        # Check if both files were deleted
        upload_deleted = not os.path.exists(upload_file_path) if upload_file_path else True
        embedding_deleted = not os.path.exists(embedding_file_path) if embedding_file_path else True
        
        if upload_deleted:
            self.stdout.write(self.style.SUCCESS("✓ File upload: Upload file deleted"))
        else:
            self.stdout.write(self.style.ERROR("✗ File upload: Upload file still exists"))
            
        if embedding_deleted:
            self.stdout.write(self.style.SUCCESS("✓ File upload: Embedding file deleted"))
        else:
            self.stdout.write(self.style.ERROR("✗ File upload: Embedding file still exists"))

        # Test 3: Check for orphaned files
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 3: Check for Orphaned Files")
        self.stdout.write("="*50)
        
        embedding_service = EmbeddingService()
        user_embedding_dir = os.path.join(
            embedding_service.embeddings_base_dir, 
            "users", 
            str(user.id), 
            "knowledge_bases"
        )
        
        if os.path.exists(user_embedding_dir):
            embedding_files = os.listdir(user_embedding_dir)
            self.stdout.write(f"Remaining embedding files: {len(embedding_files)}")
            for file in embedding_files:
                self.stdout.write(f"  - {file}")
                
            if len(embedding_files) == 0:
                self.stdout.write(self.style.SUCCESS("✓ No orphaned embedding files"))
            else:
                self.stdout.write(self.style.WARNING(f"! Found {len(embedding_files)} remaining files"))
        else:
            self.stdout.write("No embedding directory found (this is normal if no KBs exist)")

        # Test 4: Check media directory
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST 4: Check Media Directory")
        self.stdout.write("="*50)
        
        media_kb_dir = "media/knowledge_base"
        if os.path.exists(media_kb_dir):
            upload_files = os.listdir(media_kb_dir)
            self.stdout.write(f"Remaining upload files: {len(upload_files)}")
            for file in upload_files:
                self.stdout.write(f"  - {file}")
                
            if len(upload_files) == 0:
                self.stdout.write(self.style.SUCCESS("✓ No orphaned upload files"))
            else:
                self.stdout.write(self.style.WARNING(f"! Found {len(upload_files)} remaining files"))
        else:
            self.stdout.write("No upload directory found (this is normal if no files uploaded)")
            
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write("DELETION TEST SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write("Deletion cleanup tests completed!")
        self.stdout.write("If you see any ✗ errors above, there might be an issue with the cleanup signals.")
        self.stdout.write("Expected behavior:")
        self.stdout.write("1. ✓ Manual content embeddings should be deleted")
        self.stdout.write("2. ✓ File upload files should be deleted") 
        self.stdout.write("3. ✓ File upload embeddings should be deleted")
        self.stdout.write("4. ✓ No orphaned files should remain")