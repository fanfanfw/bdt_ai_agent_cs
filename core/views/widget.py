from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

from ..models import AIAssistant, WidgetConfiguration


@login_required
def widget_generator_view(request):
    """Generate embeddable widget code"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
    except AIAssistant.DoesNotExist:
        messages.error(request, 'Please set up your assistant first.')
        return redirect('business_type_selection')
    
    # Get saved widget configurations
    saved_configs = assistant.widget_configs.filter(is_active=True)
    
    if request.method == 'POST':
        action = request.POST.get('action', 'generate')
        
        if action == 'save':
            # Save current configuration
            config_name = request.POST.get('config_name', '').strip()
            if not config_name:
                messages.error(request, 'Please provide a name for the configuration.')
            else:
                widget_config = WidgetConfiguration.objects.create(
                    assistant=assistant,
                    name=config_name,
                    description=request.POST.get('config_description', ''),
                    widget_title=request.POST.get('title', f'{assistant.business_type.name} Assistant'),
                    widget_position=request.POST.get('position', 'bottom-right'),
                    primary_color=request.POST.get('accent_color', '#007bff'),
                    secondary_color=request.POST.get('base_bg_color', '#ffffff'),
                    welcome_message=request.POST.get('chat_first_message', 'Hello! How can I help you today?'),
                    chat_placeholder=request.POST.get('chat_placeholder', 'Type your message...'),
                    voice_enabled=request.POST.get('mode') == 'voice',
                    voice_language=request.POST.get('voice_language', 'auto'),
                    voice_show_transcript=request.POST.get('voice_show_transcript') == 'true',
                    consent_required=request.POST.get('consent_required') == 'true',
                    consent_title=request.POST.get('consent_title', 'Terms and Conditions'),
                    consent_content=request.POST.get('consent_content', 'By using this chat, you agree to our terms of service.'),
                )
                
                # Generate and save widget code
                widget_config.generated_code = generate_widget_code(assistant, widget_config.get_configuration_dict(), request)
                widget_config.save()
                
                messages.success(request, f'Widget configuration "{config_name}" saved successfully!')
                return redirect('widget_generator')
        
        elif action == 'generate':
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
                'saved_configs': saved_configs,
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
        'saved_configs': saved_configs,
        'show_code': False
    })


@login_required
def load_widget_config_view(request, config_id):
    """Load saved widget configuration"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        widget_config = assistant.widget_configs.get(id=config_id, is_active=True)
        
        # Convert saved config to form format
        form_config = {
            'mode': 'voice' if widget_config.voice_enabled else 'chat',
            'theme': 'light',
            'base_bg_color': widget_config.secondary_color,
            'accent_color': widget_config.primary_color,
            'cta_button_color': widget_config.primary_color,
            'cta_button_text_color': '#ffffff',
            'border_radius': 'medium',
            'size': 'medium',
            'position': widget_config.widget_position,
            'title': widget_config.widget_title,
            'chat_first_message': widget_config.welcome_message,
            'chat_placeholder': widget_config.chat_placeholder,
            'voice_show_transcript': 'true' if widget_config.voice_show_transcript else 'false',
            'consent_required': 'true' if widget_config.consent_required else 'false',
            'consent_title': widget_config.consent_title,
            'consent_content': widget_config.consent_content,
        }
        
        # Get all saved configs
        saved_configs = assistant.widget_configs.filter(is_active=True)
        
        return render(request, 'core/widget_generator.html', {
            'assistant': assistant,
            'widget_config': form_config,
            'saved_configs': saved_configs,
            'loaded_config': widget_config,
            'widget_code': widget_config.generated_code,
            'show_code': True
        })
        
    except:
        messages.error(request, 'Configuration not found.')
        return redirect('widget_generator')


@login_required
@require_http_methods(["POST"])
def delete_widget_config_view(request, config_id):
    """Delete saved widget configuration"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        widget_config = assistant.widget_configs.get(id=config_id)
        config_name = widget_config.name
        widget_config.delete()
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': True, 'message': f'Configuration "{config_name}" deleted successfully'})
        else:
            messages.success(request, f'Configuration "{config_name}" deleted successfully.')
            return redirect('widget_generator')
            
    except:
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({'success': False, 'message': 'Configuration not found'})
        else:
            messages.error(request, 'Configuration not found.')
            return redirect('widget_generator')


@login_required 
@require_http_methods(["POST"])
def copy_widget_code_view(request, config_id):
    """Mark widget code as copied and return code"""
    try:
        assistant = AIAssistant.objects.get(user=request.user)
        widget_config = assistant.widget_configs.get(id=config_id, is_active=True)
        widget_config.mark_copied()
        
        return JsonResponse({
            'success': True, 
            'code': widget_config.generated_code,
            'message': f'Widget code copied! (Used {widget_config.times_copied} times)'
        })
        
    except:
        return JsonResponse({'success': False, 'message': 'Configuration not found'})


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