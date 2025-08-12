import json
import openai
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse

from ..models import BusinessType, AIAssistant, QnA, KnowledgeBase
from ..forms import BusinessTypeForm
from ..services import EmbeddingService


@login_required
def dashboard(request):
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        
        # Get user profile for usage statistics
        profile = request.user.profile
        profile.reset_monthly_usage_if_needed()  # Ensure current month data is accurate
        
        # Get current limits from subscription plan (real-time)
        current_limits = profile.get_current_limits()
        monthly_api_limit = current_limits['monthly_api_limit']
        monthly_token_limit = current_limits['monthly_token_limit']
        
        # Calculate usage percentages using real-time limits
        api_usage_percentage = 0
        token_usage_percentage = 0
        
        if monthly_api_limit > 0:  # Not unlimited
            api_usage_percentage = (profile.current_month_api_requests / monthly_api_limit) * 100
        
        if monthly_token_limit > 0:  # Not unlimited
            token_usage_percentage = (profile.current_month_tokens / monthly_token_limit) * 100
        
        context = {
            'assistant': assistant,
            'profile': profile,
            'current_limits': current_limits,  # Add current limits to context
            'api_usage_percentage': api_usage_percentage,
            'token_usage_percentage': token_usage_percentage,
        }
        
        return render(request, 'core/dashboard.html', context)
    except AIAssistant.DoesNotExist:
        return redirect('business_type_selection')


@login_required
def business_type_selection(request):
    if request.method == 'POST':
        form = BusinessTypeForm(request.POST)
        if form.is_valid():
            business_type = form.cleaned_data['business_type']
            
            # Generate default Q&As for the business type
            qnas = generate_default_qnas(business_type.name)
            
            # Store in session for next step
            request.session['selected_business_type'] = business_type.id
            request.session['generated_qnas'] = qnas
            
            return redirect('qna_customization')
    else:
        form = BusinessTypeForm()
    
    return render(request, 'core/business_type_selection.html', {'form': form})


@login_required
def qna_customization(request):
    business_type_id = request.session.get('selected_business_type')
    if not business_type_id:
        return redirect('business_type_selection')
    
    business_type = BusinessType.objects.get(id=business_type_id)
    generated_qnas = request.session.get('generated_qnas', [])
    
    if request.method == 'POST':
        # Process Q&A customizations
        qnas_data = []
        for i in range(len(generated_qnas)):
            question = request.POST.get(f'question_{i}')
            answer = request.POST.get(f'answer_{i}')
            if question and answer:
                qnas_data.append({'question': question, 'answer': answer})
        
        request.session['customized_qnas'] = qnas_data
        return redirect('knowledge_base_setup')
    
    return render(request, 'core/qna_customization.html', {
        'business_type': business_type,
        'qnas': generated_qnas
    })


@login_required
def knowledge_base_setup(request):
    if request.method == 'POST':
        # Create AI Assistant
        business_type_id = request.session.get('selected_business_type')
        qnas_data = request.session.get('customized_qnas', [])
        
        business_type = BusinessType.objects.get(id=business_type_id)
        
        # Create system instructions from Q&As
        system_instructions = create_system_instructions(business_type.name, qnas_data)
        
        # Create AI Assistant
        assistant = AIAssistant.objects.create(
            user=request.user,
            business_type=business_type,
            system_instructions=system_instructions
        )
        
        # Save Q&As
        for i, qna in enumerate(qnas_data):
            QnA.objects.create(
                assistant=assistant,
                question=qna['question'],
                answer=qna['answer'],
                order=i
            )
        
        # Process knowledge base files/content
        manual_content = request.POST.get('manual_content', '')
        if manual_content:
            KnowledgeBase.objects.create(
                assistant=assistant,
                title="Manual Content",
                content=manual_content
            )
        
        # Handle file uploads
        if 'knowledge_files' in request.FILES:
            for file in request.FILES.getlist('knowledge_files'):
                # Process file and extract content
                content = process_uploaded_file(file)
                kb_item = KnowledgeBase.objects.create(
                    assistant=assistant,
                    title=file.name,
                    content=content,
                    file_path=file
                )
                
                # Generate embeddings using new RAG system
                embedding_service = EmbeddingService()
                embedding_service.generate_embeddings_for_item(kb_item)
        
        # Process embeddings for knowledge base (for manual content)
        try:
            embedding_service = EmbeddingService()
            embedding_service.process_knowledge_base(assistant)
        except Exception as e:
            print(f"Error processing embeddings: {e}")
        
        # Create OpenAI Assistant
        try:
            openai_assistant = create_openai_assistant(assistant)
            assistant.openai_assistant_id = openai_assistant.id
            assistant.save()
        except Exception as e:
            messages.error(request, f"Error creating AI assistant: {e}")
        
        # Clear session
        for key in ['selected_business_type', 'generated_qnas', 'customized_qnas']:
            request.session.pop(key, None)
        
        messages.success(request, "AI Assistant created successfully!")
        return redirect('dashboard')
    
    return render(request, 'core/knowledge_base_setup.html')


@login_required
def usage_stats_api(request):
    """API endpoint to get real-time usage statistics"""
    try:
        profile = request.user.profile
        profile.reset_monthly_usage_if_needed()
        
        # Get current limits from subscription plan (real-time)
        current_limits = profile.get_current_limits()
        monthly_api_limit = current_limits['monthly_api_limit']
        monthly_token_limit = current_limits['monthly_token_limit']
        
        # Calculate usage percentages using real-time limits
        api_usage_percentage = 0
        token_usage_percentage = 0
        
        if monthly_api_limit > 0:  # Not unlimited
            api_usage_percentage = (profile.current_month_api_requests / monthly_api_limit) * 100
        
        if monthly_token_limit > 0:  # Not unlimited
            token_usage_percentage = (profile.current_month_tokens / monthly_token_limit) * 100
        
        return JsonResponse({
            'subscription_plan': profile.subscription_plan,
            'current_month_api_requests': profile.current_month_api_requests,
            'monthly_api_limit': monthly_api_limit,  # Use real-time limit
            'current_month_tokens': profile.current_month_tokens,
            'monthly_token_limit': monthly_token_limit,  # Use real-time limit
            'api_usage_percentage': round(api_usage_percentage, 1),
            'token_usage_percentage': round(token_usage_percentage, 1),
            'total_api_requests': profile.api_requests_count,
            'total_tokens': profile.tokens_used,
            'can_make_api_request': profile.can_make_api_request(),
            'last_reset_date': profile.last_reset_date.strftime('%Y-%m-%d'),
            'status': 'success'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)


def generate_default_qnas(business_type):
    """Generate default Q&As using OpenAI based on business type"""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    prompt = f"""Generate 10 common customer service questions and answers for a {business_type} business. 
    Format as JSON array with 'question' and 'answer' keys. 
    Make answers helpful but concise (2-3 sentences max).
    Focus on typical customer inquiries like hours, location, services, pricing, policies etc."""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates customer service Q&As."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        # Extract JSON from response
        start = content.find('[')
        end = content.rfind(']') + 1
        if start != -1 and end != 0:
            qnas = json.loads(content[start:end])
            return qnas
    except Exception as e:
        print(f"Error generating Q&As: {e}")
    
    # Fallback default Q&As
    return [
        {"question": "What are your business hours?", "answer": "We are open Monday to Friday from 9 AM to 6 PM."},
        {"question": "Where are you located?", "answer": "Please contact us for our current location information."},
        {"question": "What services do you offer?", "answer": f"We offer various {business_type.lower()} services. Please contact us for detailed information."},
        {"question": "How can I contact you?", "answer": "You can reach us through this chat system or check our website for contact details."},
        {"question": "Do you offer delivery?", "answer": "Please inquire about our delivery options as they may vary by location."},
    ]


def create_system_instructions(business_type, qnas):
    """Create system instructions for the AI assistant"""
    qna_text = "\n".join([f"Q: {qa['question']}\nA: {qa['answer']}\n" for qa in qnas])
    
    instructions = f"""You are a helpful customer service assistant for a {business_type} business.

Your primary job is to:
1. Answer customer questions accurately and professionally
2. Use the provided Q&A knowledge base first
3. If you don't know something, admit it and offer to help find the answer
4. Be friendly, concise, and helpful
5. Stay in character as a customer service representative

Here are the specific Q&As for this business:

{qna_text}

Always prioritize these Q&As when answering similar questions. If asked about something not covered in the Q&As, use your general knowledge but mention that the customer should verify with the business directly for the most current information."""
    
    return instructions


def create_openai_assistant(assistant):
    """Create OpenAI assistant"""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    return client.beta.assistants.create(
        name=f"{assistant.business_type.name} Customer Service",
        instructions=assistant.system_instructions,
        model="gpt-4o-mini",
        tools=[{"type": "file_search"}] if assistant.knowledge_base.exists() else []
    )


def process_uploaded_file(file):
    """Extract text content from uploaded file"""
    embedding_service = EmbeddingService()
    return embedding_service.extract_file_content(file)