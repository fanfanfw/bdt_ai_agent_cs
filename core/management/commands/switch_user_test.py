from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import AIAssistant


class Command(BaseCommand):
    help = 'Switch test user for voice/chat testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username to switch to for testing',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all available users and their assistants',
        )

    def handle(self, *args, **options):
        if options['list']:
            self.list_users()
            return
            
        username = options.get('user')
        if not username:
            self.stdout.write("Please specify --user <username> or use --list to see available users")
            return
            
        try:
            user = User.objects.get(username=username)
            assistant = AIAssistant.objects.get(user=user)
            
            self.stdout.write(f"Switching to user: {username}")
            self.stdout.write(f"Business Type: {assistant.business_type.name}")
            self.stdout.write(f"Q&As: {assistant.qnas.count()}")
            self.stdout.write(f"Knowledge Base: {assistant.knowledge_base.count()}")
            
            # Show login instructions
            self.stdout.write("\nTo test with this user:")
            self.stdout.write("1. Logout from current session")
            self.stdout.write(f"2. Login with username: {username}")
            self.stdout.write("3. Go to Test Voice or Test Chat")
            
            if assistant.knowledge_base.exists():
                self.stdout.write("\nKnowledge Base Items:")
                for kb in assistant.knowledge_base.all():
                    self.stdout.write(f"  - {kb.title} ({kb.status})")
                    
            if assistant.qnas.exists():
                self.stdout.write("\nQ&A Items:")
                for qna in assistant.qnas.all()[:3]:
                    self.stdout.write(f"  - {qna.question}")
                    
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{username}' not found"))
        except AIAssistant.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{username}' has no assistant configured"))

    def list_users(self):
        self.stdout.write("Available users for testing:")
        self.stdout.write("="*50)
        
        for user in User.objects.all():
            try:
                assistant = AIAssistant.objects.get(user=user)
                self.stdout.write(f"Username: {user.username}")
                self.stdout.write(f"  Business: {assistant.business_type.name}")
                self.stdout.write(f"  Q&As: {assistant.qnas.count()}")
                self.stdout.write(f"  Knowledge Base: {assistant.knowledge_base.count()}")
                
                if assistant.knowledge_base.exists():
                    self.stdout.write("  KB Files:")
                    for kb in assistant.knowledge_base.all():
                        self.stdout.write(f"    - {kb.title}")
                        
                self.stdout.write("")
                
            except AIAssistant.DoesNotExist:
                self.stdout.write(f"Username: {user.username} (no assistant)")
                self.stdout.write("")