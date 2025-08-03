from django.core.management.base import BaseCommand
from core.models import AIAssistant
from core.services import ChatService


class Command(BaseCommand):
    help = 'Test chat functionality with an AI assistant'

    def add_arguments(self, parser):
        parser.add_argument('api_key', type=str, help='API key of the assistant to test')
        parser.add_argument('--message', type=str, default='Hello, how are you?', help='Message to send')

    def handle(self, *args, **options):
        api_key = options['api_key']
        message = options['message']

        try:
            assistant = AIAssistant.objects.get(api_key=api_key)
            self.stdout.write(f"Testing assistant for {assistant.user.username} ({assistant.business_type.name})")
            
            chat_service = ChatService(assistant)
            session_id, response = chat_service.process_message(message)
            
            self.stdout.write(f"User: {message}")
            self.stdout.write(f"Assistant: {response}")
            self.stdout.write(f"Session ID: {session_id}")
            
        except AIAssistant.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Assistant with API key {api_key} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))