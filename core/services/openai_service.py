import openai
from django.conf import settings


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