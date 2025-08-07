from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.models import User
import json
import openai
from django.db import transaction

from .models import BusinessType, AIAssistant, QnA, KnowledgeBase
from .forms import CustomUserCreationForm, BusinessTypeForm


def home(request):
    if request.user.is_authenticated:
        # Check if user is admin, redirect to admin dashboard
        if request.user.is_staff or request.user.is_superuser:
            return redirect('admin_dashboard')
        else:
            return redirect('dashboard')
    return render(request, 'core/home.html')


def admin_redirect_view(request):
    """
    View untuk menangani redirect dari /admin/ ke dashboard yang sesuai
    """
    if request.user.is_authenticated:
        # Cek apakah user adalah admin
        if request.user.is_staff or request.user.is_superuser:
            # Redirect ke dashboard admin kustom
            return redirect('admin_dashboard')
        else:
            # User biasa, redirect ke dashboard user
            messages.info(request, 'You do not have admin privileges. Redirected to user dashboard.')
            return redirect('dashboard')
    else:
        # User belum login, redirect ke halaman login
        messages.info(request, 'Please login to access the system.')
        return redirect('login')


def custom_login_view(request):
    """
    Custom login view that shows approval messages for pending users
    """
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Try to authenticate user
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # User credentials are correct and approved
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            # Check if user exists but is not approved
            try:
                user_obj = User.objects.get(username=username)
                # Check if password is correct
                if user_obj.check_password(password):
                    if hasattr(user_obj, 'profile') and user_obj.profile.status == 'pending':
                        messages.error(request, 
                            '🔒 Akun Anda sedang menunggu persetujuan admin. '
                            'Silakan tunggu hingga akun Anda disetujui untuk dapat login.')
                    elif hasattr(user_obj, 'profile') and user_obj.profile.status == 'suspended':
                        messages.error(request, 
                            '⛔ Akun Anda telah disuspend. Silakan hubungi administrator.')
                    elif hasattr(user_obj, 'profile') and user_obj.profile.status == 'rejected':
                        messages.error(request, 
                            '❌ Akun Anda telah ditolak. Silakan hubungi administrator.')
                    else:
                        messages.error(request, '❌ Login gagal. Silakan coba lagi.')
                else:
                    messages.error(request, '❌ Username atau password salah.')
            except User.DoesNotExist:
                messages.error(request, '❌ Username atau password salah.')
                
            form = AuthenticationForm()
    else:
        form = AuthenticationForm()
    
    return render(request, 'core/login.html', {'form': form})


def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            
            # Don't automatically log in - user needs admin approval
            messages.success(request, 
                f'Account created for {username}! Your account is pending admin approval. '
                'You will be able to login once approved.')
            
            return redirect('home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'core/register.html', {'form': form})


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
                from .services import EmbeddingService
                embedding_service = EmbeddingService()
                embedding_service.generate_embeddings_for_item(kb_item)
        
        # Process embeddings for knowledge base (for manual content)
        try:
            from .services import EmbeddingService
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
    from .services import EmbeddingService
    embedding_service = EmbeddingService()
    return embedding_service.extract_file_content(file)


@login_required
def test_chat_view(request):
    """Test chat functionality"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        
        # Check subscription limits
        profile = request.user.profile
        profile.reset_monthly_usage_if_needed()
        
        if not profile.can_make_api_request():
            messages.error(request, f'You have reached your monthly API request limit ({profile.monthly_api_limit}). Please upgrade your subscription to continue using this feature.')
            return redirect('dashboard')
        
        if request.method == 'POST':
            from .services import ChatService
            import json
            
            data = json.loads(request.body)
            message = data.get('message', '')
            session_id = data.get('session_id')
            language = data.get('language', 'auto')  # Get language preference
            
            # Double-check limits before processing
            if not profile.can_make_api_request():
                return JsonResponse({
                    'error': 'API limit exceeded',
                    'message': f'You have reached your monthly API request limit ({profile.monthly_api_limit}). Please upgrade your subscription.',
                    'status': 'error'
                }, status=429)
            
            chat_service = ChatService(assistant)
            # Set language preference on chat service
            chat_service.preferred_language = language
            session_id, response = chat_service.process_message(message, session_id)
            
            return JsonResponse({
                'session_id': str(session_id),
                'response': response,
                'status': 'success'
            })
        
        return render(request, 'core/test_chat.html', {'assistant': assistant})
        
    except AIAssistant.DoesNotExist:
        return redirect('business_type_selection')




@login_required
@login_required
def test_realtime_voice_view(request):
    """Test realtime voice functionality with OpenAI Realtime API"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        
        # Check subscription limits
        profile = request.user.profile
        profile.reset_monthly_usage_if_needed()
        
        if not profile.can_make_api_request():
            messages.error(request, f'You have reached your monthly API request limit ({profile.monthly_api_limit}). Please upgrade your subscription to continue using this feature.')
            return redirect('dashboard')
        
        return render(request, 'core/test_realtime_voice.html', {'assistant': assistant})
        
    except AIAssistant.DoesNotExist:
        return redirect('business_type_selection')


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


@login_required
def edit_qna_view(request):
    """Edit Q&A for existing assistant"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        qnas = assistant.qnas.all().order_by('order')
        
        if request.method == 'POST':
            # Check if regenerate was requested
            if request.POST.get('regenerate') == 'true':
                # Delete all existing Q&As
                assistant.qnas.all().delete()
                
                # Generate new Q&As
                qnas = generate_default_qnas(assistant.business_type.name)
                
                # Save new Q&As
                for i, qna in enumerate(qnas):
                    QnA.objects.create(
                        assistant=assistant,
                        question=qna['question'],
                        answer=qna['answer'],
                        order=i
                    )
                
                # Update system instructions
                system_instructions = create_system_instructions(assistant.business_type.name, qnas)
                assistant.system_instructions = system_instructions
                assistant.save()
                
                # Update OpenAI Assistant if exists
                if assistant.openai_assistant_id:
                    try:
                        from .services import OpenAIService
                        openai_service = OpenAIService()
                        openai_service.client.beta.assistants.update(
                            assistant.openai_assistant_id,
                            instructions=system_instructions
                        )
                    except Exception as e:
                        print(f"Error updating OpenAI assistant: {e}")
                
                messages.success(request, "Q&As regenerated successfully!")
                return redirect('edit_qna')
            
            # Delete Q&As marked for deletion
            delete_ids = request.POST.getlist('delete_qna')
            # Filter out empty strings
            delete_ids = [id for id in delete_ids if id.strip()]
            if delete_ids:
                assistant.qnas.filter(id__in=delete_ids).delete()
            
            # Update existing Q&As and create new ones
            qna_data = []
            order = 0
            
            # Get fresh list of Q&As after deletion
            current_qnas = assistant.qnas.all().order_by('order')
            
            # Process existing Q&As
            for qna in current_qnas:
                if str(qna.id) not in delete_ids:
                    question = request.POST.get(f'question_{qna.id}', '').strip()
                    answer = request.POST.get(f'answer_{qna.id}', '').strip()
                    
                    if question and answer:
                        qna.question = question
                        qna.answer = answer
                        qna.order = order
                        qna.save()
                        qna_data.append({'question': question, 'answer': answer})
                        order += 1
            
            # Process new Q&As
            new_questions = request.POST.getlist('new_question')
            new_answers = request.POST.getlist('new_answer')
            
            for i, (question, answer) in enumerate(zip(new_questions, new_answers)):
                question = question.strip()
                answer = answer.strip()
                if question and answer:
                    QnA.objects.create(
                        assistant=assistant,
                        question=question,
                        answer=answer,
                        order=order
                    )
                    qna_data.append({'question': question, 'answer': answer})
                    order += 1
            
            # Update system instructions
            system_instructions = create_system_instructions(assistant.business_type.name, qna_data)
            assistant.system_instructions = system_instructions
            assistant.save()
            
            # Update OpenAI Assistant if exists
            if assistant.openai_assistant_id:
                try:
                    from .services import OpenAIService
                    openai_service = OpenAIService()
                    openai_service.client.beta.assistants.update(
                        assistant.openai_assistant_id,
                        instructions=system_instructions
                    )
                except Exception as e:
                    print(f"Error updating OpenAI assistant: {e}")
            
            messages.success(request, "Q&As updated successfully!")
            return redirect('dashboard')
        
        return render(request, 'core/edit_qna.html', {
            'assistant': assistant,
            'qnas': qnas
        })
        
    except AIAssistant.DoesNotExist:
        return redirect('business_type_selection')


@login_required
def edit_knowledge_base_view(request):
    """Edit knowledge base for existing assistant"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        knowledge_items = assistant.knowledge_base.all().order_by('-created_at')
        
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'delete':
                item_id = request.POST.get('item_id')
                if not item_id or not item_id.strip():
                    messages.error(request, "Invalid item ID!")
                    return redirect('edit_knowledge_base')
                try:
                    item = assistant.knowledge_base.get(id=item_id)
                    
                    # Django signals will automatically handle:
                    # - Embedding file cleanup (post_delete signal)
                    # - Upload file cleanup (post_delete signal)
                    item.delete()
                    messages.success(request, "Knowledge base item and its embeddings deleted successfully!")
                except KnowledgeBase.DoesNotExist:
                    messages.error(request, "Knowledge base item not found!")
                    
            elif action == 'update':
                item_id = request.POST.get('item_id')
                new_content = request.POST.get('content', '').strip()
                if not item_id or not item_id.strip():
                    messages.error(request, "Invalid item ID!")
                    return redirect('edit_knowledge_base')
                try:
                    item = assistant.knowledge_base.get(id=item_id)
                    if new_content:
                        old_content = item.content
                        item.content = new_content
                        
                        # Only update title if content actually changed
                        if old_content != new_content:
                            if not item.title.startswith("Updated: "):
                                item.title = f"Updated: {item.title}"
                            item.save()  # This will trigger the signal to refresh embeddings
                            messages.success(request, "Knowledge base item updated and embeddings are being refreshed!")
                        else:
                            messages.info(request, "No changes detected in content.")
                    else:
                        messages.error(request, "Content cannot be empty!")
                except KnowledgeBase.DoesNotExist:
                    messages.error(request, "Knowledge base item not found!")
                    
            elif action == 'add':
                # Add new knowledge base content
                manual_content = request.POST.get('manual_content', '').strip()
                title = request.POST.get('title', '').strip()
                
                if manual_content and title:
                    kb_item = KnowledgeBase.objects.create(
                        assistant=assistant,
                        title=title,
                        content=manual_content
                    )
                    # Embeddings will be generated automatically via post_save signal
                    messages.success(request, "Knowledge base item added and embeddings are being generated!")
                
                # Handle file uploads
                if 'knowledge_files' in request.FILES:
                    for file in request.FILES.getlist('knowledge_files'):
                        content = process_uploaded_file(file)
                        kb_item = KnowledgeBase.objects.create(
                            assistant=assistant,
                            title=file.name,
                            content=content,
                            file_path=file
                        )
                        # Embeddings will be generated automatically via post_save signal
                    
                    messages.success(request, "Files uploaded and embeddings are being generated!")
            
            return redirect('edit_knowledge_base')
        
        return render(request, 'core/edit_knowledge_base.html', {
            'assistant': assistant,
            'knowledge_items': knowledge_items
        })
        
    except AIAssistant.DoesNotExist:
        return redirect('business_type_selection')


@login_required
def edit_business_type_view(request):
    """Edit business type for existing assistant"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        
        if request.method == 'POST':
            form = BusinessTypeForm(request.POST)
            if form.is_valid():
                new_business_type = form.cleaned_data['business_type']
                old_business_type = assistant.business_type
                
                # Check if business type actually changed
                if new_business_type != old_business_type:
                    assistant.business_type = new_business_type
                    
                    # Option to regenerate Q&As for new business type
                    regenerate_qnas = request.POST.get('regenerate_qnas') == 'on'
                    
                    if regenerate_qnas:
                        # Delete existing Q&As
                        assistant.qnas.all().delete()
                        
                        # Generate new Q&As for new business type
                        qnas = generate_default_qnas(new_business_type.name)
                        
                        # Save new Q&As
                        for i, qna in enumerate(qnas):
                            QnA.objects.create(
                                assistant=assistant,
                                question=qna['question'],
                                answer=qna['answer'],
                                order=i
                            )
                        
                        qna_data = qnas
                    else:
                        # Keep existing Q&As, just update business type references
                        qna_data = [{'question': qna.question, 'answer': qna.answer} 
                                   for qna in assistant.qnas.all()]
                    
                    # Update system instructions with new business type
                    system_instructions = create_system_instructions(new_business_type.name, qna_data)
                    assistant.system_instructions = system_instructions
                    assistant.save()
                    
                    # Update OpenAI Assistant if exists
                    if assistant.openai_assistant_id:
                        try:
                            from .services import OpenAIService
                            openai_service = OpenAIService()
                            openai_service.client.beta.assistants.update(
                                assistant.openai_assistant_id,
                                name=f"{new_business_type.name} Customer Service",
                                instructions=system_instructions
                            )
                        except Exception as e:
                            print(f"Error updating OpenAI assistant: {e}")
                    
                    if regenerate_qnas:
                        messages.success(request, f"Business type updated to {new_business_type.name} and Q&As regenerated successfully!")
                    else:
                        messages.success(request, f"Business type updated to {new_business_type.name} successfully!")
                else:
                    messages.info(request, "No changes were made.")
                
                return redirect('dashboard')
        else:
            # Pre-populate form with current business type
            form = BusinessTypeForm(initial={'business_type': assistant.business_type})
        
        return render(request, 'core/edit_business_type.html', {
            'assistant': assistant,
            'form': form
        })
        
    except AIAssistant.DoesNotExist:
        return redirect('business_type_selection')


@login_required
def widget_generator_view(request):
    """Generate embeddable widget code"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
    except AIAssistant.DoesNotExist:
        messages.error(request, 'Please set up your assistant first.')
        return redirect('business_type_selection')
    
    if request.method == 'POST':
        # Handle widget configuration updates
        widget_config = {
            'mode': request.POST.get('mode', 'chat'),
            'theme': request.POST.get('theme', 'light'),
            'base_bg_color': request.POST.get('base_bg_color', '#ffffff'),
            'accent_color': request.POST.get('accent_color', '#007bff'),
            'cta_button_color': request.POST.get('cta_button_color', '#007bff'),
            'cta_button_text_color': request.POST.get('cta_button_text_color', '#ffffff'),
            'border_radius': request.POST.get('border_radius', 'medium'),
            'size': request.POST.get('size', 'medium'),
            'position': request.POST.get('position', 'bottom-right'),
            'title': request.POST.get('title', f'{assistant.business_type.name} Assistant'),
            'chat_first_message': request.POST.get('chat_first_message', 'Hello! How can I help you today?'),
            'chat_placeholder': request.POST.get('chat_placeholder', 'Type your message...'),
            'voice_show_transcript': request.POST.get('voice_show_transcript', 'true'),
            'consent_required': request.POST.get('consent_required', 'false'),
            'consent_title': request.POST.get('consent_title', 'Terms and Conditions'),
            'consent_content': request.POST.get('consent_content', 'By using this chat, you agree to our terms of service.'),
        }
        
        # Generate widget code
        widget_code = generate_widget_code(assistant, widget_config, request)
        
        return render(request, 'core/widget_generator.html', {
            'assistant': assistant,
            'widget_config': widget_config,
            'widget_code': widget_code,
            'show_code': True
        })
    
    # Default configuration
    default_config = {
        'mode': 'both',
        'theme': 'light',
        'base_bg_color': '#ffffff',
        'accent_color': '#007bff',
        'cta_button_color': '#007bff',
        'cta_button_text_color': '#ffffff',
        'border_radius': 'medium',
        'size': 'medium',
        'position': 'bottom-right',
        'title': f'{assistant.business_type.name} Assistant',
        'chat_first_message': 'Hello! How can I help you today?',
        'chat_placeholder': 'Type your message...',
        'voice_show_transcript': 'true',
        'consent_required': 'false',
        'consent_title': 'Terms and Conditions',
        'consent_content': 'By using this chat, you agree to our terms of service.',
    }
    
    return render(request, 'core/widget_generator.html', {
        'assistant': assistant,
        'widget_config': default_config,
        'show_code': False
    })


def generate_widget_code(assistant, config, request):
    """Generate the embeddable widget code"""
    base_url = f"{request.scheme}://{request.get_host()}"
    
    # Build widget attributes
    attributes = []
    attributes.append(f'api-key="{assistant.api_key}"')
    attributes.append(f'assistant-id="{assistant.id}"')
    
    for key, value in config.items():
        if value:  # Only add non-empty values
            attr_name = key.replace('_', '-')
            attributes.append(f'{attr_name}="{value}"')
    
    widget_attributes = '\n  '.join(attributes)
    
    widget_code = f'''<!-- AI Agent Widget -->
<ai-agent-widget
  {widget_attributes}
></ai-agent-widget>

<script src="{base_url}/static/js/ai-agent-widget.js" async type="text/javascript"></script>'''
    
    return widget_code


def logout_view(request):
    """Custom logout view that handles both GET and POST"""
    logout(request)
    messages.success(request, "You have been logged out successfully!")
    return redirect('home')
