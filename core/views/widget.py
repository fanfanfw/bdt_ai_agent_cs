from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string

from ..models import AIAssistant

# ALL WIDGET GENERATOR VIEWS REMOVED - USING CDN WIDGET IN DASHBOARD INSTEAD

def widget_cdn_js(request):
    """CDN-style widget JavaScript endpoint"""
    # Extract parameters from URL
    api_key = request.GET.get('key') or request.GET.get('api_key')
    assistant_id = request.GET.get('id') or request.GET.get('assistant_id', '1')
    
    # Get widget configuration from parameters with defaults
    config = {
        'mode': request.GET.get('mode', 'both'),
        'theme': request.GET.get('theme', 'light'),
        'title': request.GET.get('title', 'AI Assistant'),
        'position': request.GET.get('position', 'bottom-right'),
        'accentColor': request.GET.get('accent_color', '#007bff'),
        'baseBgColor': request.GET.get('base_bg_color', '#ffffff'),
        'chatFirstMessage': request.GET.get('chat_first_message', 'Hello! How can I help you today?'),
        'chatPlaceholder': request.GET.get('chat_placeholder', 'Type your message...'),
        'voiceShowTranscript': request.GET.get('voice_show_transcript', 'true'),
        'consentRequired': request.GET.get('consent_required', 'false'),
        'consentTitle': request.GET.get('consent_title', 'Privacy Notice'),
        'consentContent': request.GET.get('consent_content', 'This chat uses AI to provide assistance.'),
    }
    
    if not api_key:
        return HttpResponse(
            '/* Error: API key is required. Usage: /widget.js?key=YOUR_API_KEY&id=ASSISTANT_ID */',
            content_type='application/javascript'
        )
    
    # Get base URL for API calls
    base_url = f"{request.scheme}://{request.get_host()}"
    
    # Generate the complete JavaScript widget
    javascript_content = generate_cdn_javascript(api_key, assistant_id, config, base_url)
    
    return HttpResponse(javascript_content, content_type='application/javascript')


def generate_cdn_javascript(api_key, assistant_id, config, base_url):
    """Generate complete self-contained JavaScript widget"""
    
    # Read the existing widget JavaScript
    import os
    from django.conf import settings
    
    widget_js_path = os.path.join(settings.STATICFILES_DIRS[0], 'js', 'ai-agent-widget.js')
    
    try:
        with open(widget_js_path, 'r') as f:
            base_js = f.read()
    except FileNotFoundError:
        # Fallback to staticfiles
        widget_js_path = os.path.join(settings.STATIC_ROOT, 'js', 'ai-agent-widget.js')
        try:
            with open(widget_js_path, 'r') as f:
                base_js = f.read()
        except FileNotFoundError:
            return '/* Error: Widget JavaScript file not found */'
    
    # Create widget configuration
    widget_config_js = f'''
// Auto-generated CDN Widget Configuration
(function() {{
    // Create and insert widget element with configuration
    const widgetElement = document.createElement('ai-agent-widget');
    widgetElement.setAttribute('api-key', '{api_key}');
    widgetElement.setAttribute('assistant-id', '{assistant_id}');
    widgetElement.setAttribute('mode', '{config["mode"]}');
    widgetElement.setAttribute('theme', '{config["theme"]}');
    widgetElement.setAttribute('title', '{config["title"]}');
    widgetElement.setAttribute('position', '{config["position"]}');
    widgetElement.setAttribute('accent-color', '{config["accentColor"]}');
    widgetElement.setAttribute('base-bg-color', '{config["baseBgColor"]}');
    widgetElement.setAttribute('chat-first-message', '{config["chatFirstMessage"]}');
    widgetElement.setAttribute('chat-placeholder', '{config["chatPlaceholder"]}');
    widgetElement.setAttribute('voice-show-transcript', '{config["voiceShowTranscript"]}');
    widgetElement.setAttribute('consent-required', '{config["consentRequired"]}');
    widgetElement.setAttribute('consent-title', '{config["consentTitle"]}');
    widgetElement.setAttribute('consent-content', '{config["consentContent"]}');
    
    // Insert widget when DOM is ready
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', function() {{
            document.body.appendChild(widgetElement);
        }});
    }} else {{
        document.body.appendChild(widgetElement);
    }}
}})();
'''
    
    # Combine base JavaScript with configuration
    complete_js = base_js + '\n' + widget_config_js
    
    return complete_js