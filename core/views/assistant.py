from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import AIAssistant, QnA, KnowledgeBase, BusinessType
from ..forms import BusinessTypeForm
from ..services import EmbeddingService, OpenAIService
from .dashboard import generate_default_qnas, create_system_instructions, process_uploaded_file


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