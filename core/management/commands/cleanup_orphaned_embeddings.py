from django.core.management.base import BaseCommand
from core.models import KnowledgeBase
from core.services import EmbeddingService
import os
import re


class Command(BaseCommand):
    help = 'Clean up orphaned embedding files that no longer have corresponding KnowledgeBase entries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        embedding_service = EmbeddingService()
        base_dir = embedding_service.embeddings_base_dir
        
        if not os.path.exists(base_dir):
            self.stdout.write("No embeddings directory found.")
            return
        
        orphaned_files = []
        total_files = 0
        
        # Walk through all embedding files
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.endswith('_embeddings.json'):
                    total_files += 1
                    file_path = os.path.join(root, file)
                    
                    # Extract KB ID from filename
                    match = re.search(r'(\d+)_embeddings\.json$', file)
                    if match:
                        kb_id = int(match.group(1))
                        
                        # Check if KB exists
                        try:
                            kb = KnowledgeBase.objects.get(id=kb_id)
                            # Check if the embedding file path matches
                            if kb.embedding_file_path != file_path:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"⚠️  KB {kb_id} exists but path mismatch:\n"
                                        f"   File: {file_path}\n"
                                        f"   DB:   {kb.embedding_file_path}"
                                    )
                                )
                        except KnowledgeBase.DoesNotExist:
                            # This is an orphaned file
                            orphaned_files.append((file_path, kb_id))
        
        self.stdout.write(f"\nScan Results:")
        self.stdout.write(f"Total embedding files found: {total_files}")
        self.stdout.write(f"Orphaned files found: {len(orphaned_files)}")
        
        if orphaned_files:
            self.stdout.write(f"\n{self.style.WARNING('Orphaned Files:')}")
            for file_path, kb_id in orphaned_files:
                self.stdout.write(f"  - {file_path} (KB ID: {kb_id})")
            
            if dry_run:
                self.stdout.write(f"\n{self.style.NOTICE('DRY RUN: No files were deleted.')}")
                self.stdout.write("Run without --dry-run to actually delete these files.")
            else:
                # Delete orphaned files
                deleted_count = 0
                for file_path, kb_id in orphaned_files:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                        self.stdout.write(f"  ✓ Deleted: {file_path}")
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"  ✗ Error deleting {file_path}: {e}")
                        )
                
                self.stdout.write(f"\n{self.style.SUCCESS(f'Successfully deleted {deleted_count} orphaned files.')}")
                
                # Clean up empty directories
                self.cleanup_empty_dirs(base_dir)
        else:
            self.stdout.write(f"\n{self.style.SUCCESS('✓ No orphaned files found!')}")
    
    def cleanup_empty_dirs(self, base_dir):
        """Remove empty directories after file cleanup"""
        removed_dirs = []
        
        for root, dirs, files in os.walk(base_dir, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if not os.listdir(dir_path):  # Directory is empty
                        os.rmdir(dir_path)
                        removed_dirs.append(dir_path)
                except OSError:
                    pass  # Directory not empty or other error
        
        if removed_dirs:
            self.stdout.write(f"\nCleaned up {len(removed_dirs)} empty directories:")
            for dir_path in removed_dirs:
                self.stdout.write(f"  ✓ Removed: {dir_path}")