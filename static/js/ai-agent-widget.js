/**
 * AI Agent Widget - Embeddable Chat & Voice Widget with Realtime Voice
 * Usage: <ai-agent-widget api-key="your-key" assistant-id="id" mode="chat" theme="light"></ai-agent-widget>
 */

(function() {
    'use strict';

    // Widget configuration defaults
    const DEFAULT_CONFIG = {
        mode: 'chat', // 'chat', 'voice', 'both'
        theme: 'light', // 'light', 'dark'
        baseBgColor: '#ffffff',
        accentColor: '#007bff',
        ctaButtonColor: '#007bff',
        ctaButtonTextColor: '#ffffff',
        borderRadius: 'medium', // 'small', 'medium', 'large'
        size: 'medium', // 'small', 'medium', 'large', 'full'
        position: 'bottom-right', // 'bottom-right', 'bottom-left', 'top-right', 'top-left'
        title: 'AI Assistant',
        startButtonText: 'Start Chat',
        endButtonText: 'End Chat',
        chatFirstMessage: 'Hello! How can I help you today?',
        chatPlaceholder: 'Type your message...',
        voiceShowTranscript: 'true',
        consentRequired: 'false',
        consentTitle: 'Terms and Conditions',
        consentContent: 'By using this chat, you agree to our terms of service.',
        consentStorageKey: 'ai_agent_widget_consent'
    };

    // Base URL for API calls (will be set dynamically)
    let BASE_URL = '';

    // Detect the base URL from the script tag
    function detectBaseUrl() {
        const scripts = document.getElementsByTagName('script');
        for (let script of scripts) {
            if (script.src && script.src.includes('ai-agent-widget.js')) {
                const url = new URL(script.src);
                BASE_URL = `${url.protocol}//${url.host}`;
                console.log('Detected BASE_URL from script:', BASE_URL);
                break;
            }
        }
        // Fallback for development
        if (!BASE_URL) {
            BASE_URL = window.location.origin;
            console.log('Using fallback BASE_URL:', BASE_URL);
        }
        
        // Special handling for localhost development
        if (BASE_URL.includes('file://') || !BASE_URL.includes('http')) {
            BASE_URL = 'http://127.0.0.1:8000';
            console.log('Development mode - hardcoded BASE_URL:', BASE_URL);
        }
    }

    // Call detectBaseUrl when script loads
    detectBaseUrl();

    class AIAgentWidget extends HTMLElement {
        constructor() {
            super();
            this.attachShadow({ mode: 'open' });
            this.config = { ...DEFAULT_CONFIG };
            this.isOpen = false;
            this.sessionId = null;
            
            // Realtime voice properties
            this.voiceWebSocket = null;
            this.isVoiceActive = false;
            this.isVoiceConnecting = false;
            this.audioContext = null;
            this.mediaRecorder = null;
            this.audioStream = null;
            this.voiceSessionId = null;
            
            // Audio playback for realtime voice
            this.globalAudioContext = null;
            this.audioChunksBuffer = [];
            this.isBuffering = false;
            this.nextPlayTime = 0;
        }

        connectedCallback() {
            this.parseAttributes();
            this.render();
            this.attachEventListeners();
            this.checkConsent();
        }

        parseAttributes() {
            // Parse all attributes and override defaults
            for (let attr of this.attributes) {
                const key = attr.name.replace(/-([a-z])/g, (g) => g[1].toUpperCase());
                this.config[key] = attr.value;
            }
            console.log('Widget config after parsing:', this.config);
        }

        checkConsent() {
            if (this.config.consentRequired === 'true') {
                const consent = localStorage.getItem(this.config.consentStorageKey);
                if (!consent) {
                    this.showConsentDialog();
                    return;
                }
            }
        }

        showConsentDialog() {
            const overlay = this.shadowRoot.getElementById('consentOverlay');
            if (overlay) overlay.style.display = 'flex';
        }

        hideConsentDialog() {
            const overlay = this.shadowRoot.getElementById('consentOverlay');
            if (overlay) overlay.style.display = 'none';
        }

        acceptConsent() {
            localStorage.setItem(this.config.consentStorageKey, 'true');
            this.hideConsentDialog();
        }

        render() {
            const isDark = this.config.theme === 'dark';
            
            this.shadowRoot.innerHTML = `
                <style>
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }

                    :host {
                        position: fixed;
                        z-index: 9999;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        ${this.getPositionStyles()}
                    }

                    .widget-toggle {
                        width: 60px;
                        height: 60px;
                        border-radius: 50%;
                        background: ${this.config.ctaButtonColor};
                        color: ${this.config.ctaButtonTextColor};
                        border: none;
                        cursor: pointer;
                        font-size: 24px;
                        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
                        transition: all 0.3s ease;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }

                    .widget-toggle:hover {
                        transform: scale(1.1);
                        box-shadow: 0 6px 25px rgba(0, 0, 0, 0.2);
                    }

                    .widget-panel {
                        position: absolute;
                        bottom: 80px;
                        right: 0;
                        width: 380px;
                        height: 520px;
                        max-height: 80vh;
                        max-width: 90vw;
                        background: ${isDark ? '#2d2d2d' : '#ffffff'};
                        border-radius: ${this.getBorderRadius()};
                        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                        transform: scale(0.8) translateY(20px);
                        opacity: 0;
                        visibility: hidden;
                        transition: all 0.3s ease;
                        display: flex;
                        flex-direction: column;
                        overflow: hidden;
                        z-index: 999999;
                    }

                    .widget-panel.open {
                        transform: scale(1) translateY(0);
                        opacity: 1;
                        visibility: visible;
                    }

                    .widget-header {
                        background: ${this.config.accentColor};
                        color: white;
                        padding: 16px;
                        text-align: center;
                        font-weight: 600;
                    }

                    .widget-modes {
                        display: flex;
                        background: ${isDark ? '#3d3d3d' : '#f8f9fa'};
                    }

                    .mode-button {
                        flex: 1;
                        padding: 12px;
                        border: none;
                        background: transparent;
                        color: ${isDark ? '#fff' : '#666'};
                        cursor: pointer;
                        font-size: 14px;
                        transition: all 0.3s ease;
                    }

                    .mode-button.active {
                        background: ${this.config.accentColor};
                        color: white;
                    }

                    .widget-content {
                        flex: 1;
                        display: flex;
                        flex-direction: column;
                        overflow: hidden;
                    }

                    .chat-container, .voice-container {
                        flex: 1;
                        display: none;
                        flex-direction: column;
                    }
                    
                    .chat-container.active, .voice-container.active {
                        display: flex;
                    }
                    
                    .chat-messages {
                        flex: 1;
                        padding: 16px;
                        overflow-y: auto;
                        overflow-x: hidden;
                        background: ${isDark ? '#1a1a1a' : '#ffffff'};
                        max-height: calc(100vh - 200px);
                        scrollbar-width: thin;
                        scrollbar-color: ${isDark ? '#555 #333' : '#ccc #f1f1f1'};
                    }
                    
                    .chat-messages::-webkit-scrollbar {
                        width: 6px;
                    }
                    
                    .chat-messages::-webkit-scrollbar-track {
                        background: ${isDark ? '#333' : '#f1f1f1'};
                        border-radius: 3px;
                    }
                    
                    .chat-messages::-webkit-scrollbar-thumb {
                        background: ${isDark ? '#555' : '#ccc'};
                        border-radius: 3px;
                    }
                    
                    .chat-messages::-webkit-scrollbar-thumb:hover {
                        background: ${isDark ? '#777' : '#999'};
                    }
                    
                    .message {
                        margin-bottom: 16px;
                        display: flex;
                        max-width: 80%;
                        word-wrap: break-word;
                        overflow-wrap: break-word;
                    }
                    
                    .message.user {
                        margin-left: auto;
                    }
                    
                    .message.user .message-content {
                        background: ${this.config.accentColor};
                        color: white;
                        border-radius: 18px 18px 4px 18px;
                    }
                    
                    .message.assistant .message-content {
                        background: ${isDark ? '#444' : '#f0f0f0'};
                        color: ${isDark ? '#fff' : '#333'};
                        border-radius: 18px 18px 18px 4px;
                    }
                    
                    .message-content {
                        padding: 12px 16px;
                        word-wrap: break-word;
                        overflow-wrap: break-word;
                        white-space: pre-wrap;
                        font-size: 14px;
                        line-height: 1.4;
                        max-width: 100%;
                        min-width: 0;
                        flex: 1;
                        border-radius: 18px;
                    }

                    .chat-input {
                        display: flex;
                        padding: 16px;
                        background: ${isDark ? '#2d2d2d' : '#ffffff'};
                        border-top: 1px solid ${isDark ? '#444' : '#eee'};
                    }

                    .chat-input input {
                        flex: 1;
                        padding: 12px;
                        border: 1px solid ${isDark ? '#555' : '#ddd'};
                        border-radius: 24px;
                        background: ${isDark ? '#444' : '#fff'};
                        color: ${isDark ? '#fff' : '#333'};
                        outline: none;
                        font-size: 14px;
                        margin-right: 8px;
                    }

                    .chat-input button {
                        padding: 12px 16px;
                        background: ${this.config.accentColor};
                        color: white;
                        border: none;
                        border-radius: 24px;
                        cursor: pointer;
                        font-size: 14px;
                        transition: background 0.3s ease;
                    }

                    .chat-input button:hover:not(:disabled) {
                        opacity: 0.9;
                    }

                    .chat-input button:disabled {
                        opacity: 0.5;
                        cursor: not-allowed;
                    }

                    /* Voice Container Styles */
                    .voice-container {
                        padding: 20px;
                        text-align: center;
                        background: ${isDark ? '#1a1a1a' : '#ffffff'};
                    }
                    
                    .voice-status {
                        color: ${isDark ? '#fff' : '#666'};
                        margin-bottom: 20px;
                        font-size: 16px;
                        font-weight: 500;
                    }
                    
                    .voice-button {
                        width: 100px;
                        height: 100px;
                        border-radius: 50%;
                        background: ${this.config.accentColor};
                        color: white;
                        border: none;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 32px;
                        margin: 20px auto;
                        transition: all 0.3s ease;
                        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
                    }
                    
                    .voice-button:hover {
                        transform: scale(1.05);
                    }
                    
                    .voice-button.active {
                        background: #dc3545;
                        animation: pulse 1.5s infinite;
                    }
                    
                    .voice-button:disabled {
                        opacity: 0.5;
                        cursor: not-allowed;
                        animation: none;
                    }
                    
                    @keyframes pulse {
                        0% { transform: scale(1); box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2); }
                        50% { transform: scale(1.05); box-shadow: 0 6px 20px rgba(220, 53, 69, 0.4); }
                        100% { transform: scale(1); box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2); }
                    }
                    
                    .voice-transcript {
                        background: ${isDark ? '#333' : '#f8f9fa'};
                        padding: 16px;
                        border-radius: 12px;
                        margin-top: 20px;
                        color: ${isDark ? '#fff' : '#333'};
                        font-size: 14px;
                        min-height: 120px;
                        text-align: left;
                        overflow-y: auto;
                        max-height: 200px;
                        line-height: 1.4;
                    }
                    
                    .transcript-entry {
                        margin-bottom: 12px;
                        padding-bottom: 8px;
                        border-bottom: 1px solid ${isDark ? '#444' : '#eee'};
                    }
                    
                    .transcript-entry:last-child {
                        border-bottom: none;
                        margin-bottom: 0;
                    }
                    
                    .transcript-user {
                        color: ${this.config.accentColor};
                        font-weight: 600;
                    }
                    
                    .transcript-assistant {
                        color: ${isDark ? '#4CAF50' : '#28a745'};
                        font-weight: 600;
                    }

                    /* Consent Dialog */
                    .consent-overlay {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100vw;
                        height: 100vh;
                        background: rgba(0, 0, 0, 0.5);
                        display: none;
                        align-items: center;
                        justify-content: center;
                        z-index: 10000;
                    }

                    .consent-dialog {
                        background: ${isDark ? '#2d2d2d' : '#ffffff'};
                        color: ${isDark ? '#fff' : '#333'};
                        padding: 24px;
                        border-radius: 12px;
                        max-width: 400px;
                        width: 90%;
                        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                    }

                    .consent-title {
                        font-size: 18px;
                        font-weight: 600;
                        margin-bottom: 12px;
                    }

                    .consent-content {
                        font-size: 14px;
                        line-height: 1.5;
                        margin-bottom: 20px;
                        color: ${isDark ? '#ccc' : '#666'};
                    }

                    .consent-buttons {
                        display: flex;
                        gap: 12px;
                        justify-content: flex-end;
                    }

                    .consent-button {
                        padding: 10px 20px;
                        border: none;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 500;
                        transition: all 0.3s ease;
                    }

                    .consent-accept {
                        background: ${this.config.accentColor};
                        color: white;
                    }

                    .consent-decline {
                        background: ${isDark ? '#555' : '#f0f0f0'};
                        color: ${isDark ? '#fff' : '#333'};
                    }

                    .consent-button:hover {
                        opacity: 0.9;
                        transform: translateY(-1px);
                    }

                    /* Loading states */
                    .loading {
                        opacity: 0.7;
                    }
                    
                    .loading::after {
                        content: '...';
                        animation: loading 1.5s infinite;
                    }
                    
                    @keyframes loading {
                        0%, 20% { content: '.'; }
                        40% { content: '..'; }
                        60%, 100% { content: '...'; }
                    }

                    /* Error states */
                    .error {
                        color: #dc3545;
                        font-size: 13px;
                        margin-top: 8px;
                        padding: 8px 12px;
                        background: ${isDark ? '#2d1b1b' : '#f8d7da'};
                        border-radius: 6px;
                        border: 1px solid #dc3545;
                    }

                    /* Responsive design */
                    @media (max-width: 480px) {
                        .widget-panel {
                            width: 100vw;
                            height: 100vh;
                            max-height: 100vh;
                            max-width: 100vw;
                            right: 0;
                            bottom: 0;
                            border-radius: 0;
                        }
                        
                        .chat-messages {
                            max-height: calc(100vh - 150px);
                        }
                        
                        :host {
                            bottom: 20px;
                            right: 20px;
                        }
                    }
                    
                    @media (max-width: 768px) {
                        .widget-panel {
                            width: calc(100vw - 40px);
                            max-width: calc(100vw - 40px);
                            right: 20px;
                        }
                        
                        .chat-messages {
                            max-height: calc(80vh - 150px);
                        }
                    }
                </style>

                <div class="widget-toggle" id="widgetToggle">💬</div>
                
                <div class="widget-panel" id="widgetPanel">
                    <div class="widget-header">
                        ${this.config.title}
                    </div>
                    
                    ${(this.config.mode === 'both') ? `
                    <div class="widget-modes">
                        <button class="mode-button active" data-mode="chat">💬 Chat</button>
                        <button class="mode-button" data-mode="voice">🎤 Voice</button>
                    </div>
                    ` : ''}
                    
                    <div class="widget-content">
                        <div class="chat-container ${this.config.mode === 'chat' || this.config.mode === 'both' ? 'active' : ''}">
                            <div class="chat-messages" id="chatMessages">
                                <div class="message assistant">
                                    <div class="message-content">${this.config.chatFirstMessage}</div>
                                </div>
                            </div>
                            <div class="chat-input">
                                <input type="text" id="chatInput" placeholder="${this.config.chatPlaceholder}" />
                                <button id="sendButton">Send</button>
                            </div>
                        </div>
                        
                        <div class="voice-container ${this.config.mode === 'voice' ? 'active' : ''}">
                            <div class="voice-status" id="voiceStatus">Click to start conversation</div>
                            <button class="voice-button" id="voiceButton">🎤</button>
                            ${this.config.voiceShowTranscript === 'true' ? '<div class="voice-transcript" id="voiceTranscript">Conversation will appear here...</div>' : ''}
                            <div id="voiceError" class="error" style="display: none;"></div>
                        </div>
                    </div>
                </div>
                
                ${this.config.consentRequired === 'true' ? `
                <div class="consent-overlay" id="consentOverlay">
                    <div class="consent-dialog">
                        <div class="consent-title">${this.config.consentTitle}</div>
                        <div class="consent-content">${this.config.consentContent}</div>
                        <div class="consent-buttons">
                            <button class="consent-button consent-decline" id="consentDecline">Decline</button>
                            <button class="consent-button consent-accept" id="consentAccept">Accept</button>
                        </div>
                    </div>
                </div>
                ` : ''}
            `;
        }

        getPositionStyles() {
            const positions = {
                'bottom-right': 'bottom: 20px; right: 20px;',
                'bottom-left': 'bottom: 20px; left: 20px;',
                'top-right': 'top: 20px; right: 20px;',
                'top-left': 'top: 20px; left: 20px;'
            };
            return positions[this.config.position] || positions['bottom-right'];
        }

        getBorderRadius() {
            const radius = {
                'small': '8px',
                'medium': '16px',
                'large': '24px'
            };
            return radius[this.config.borderRadius] || radius['medium'];
        }

        attachEventListeners() {
            const toggleButton = this.shadowRoot.getElementById('widgetToggle');
            const chatInput = this.shadowRoot.getElementById('chatInput');
            const sendButton = this.shadowRoot.getElementById('sendButton');
            const voiceButton = this.shadowRoot.getElementById('voiceButton');
            const consentAccept = this.shadowRoot.getElementById('consentAccept');
            const consentDecline = this.shadowRoot.getElementById('consentDecline');

            // Mode selector
            const modeButtons = this.shadowRoot.querySelectorAll('.mode-button');
            modeButtons.forEach(button => {
                button.addEventListener('click', () => this.switchMode(button.dataset.mode));
            });

            // Widget toggle
            toggleButton.addEventListener('click', () => this.toggleWidget());

            // Chat functionality
            chatInput?.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
            sendButton?.addEventListener('click', () => this.sendMessage());

            // Realtime Voice functionality
            voiceButton?.addEventListener('click', () => this.toggleVoiceConversation());

            // Consent handling
            consentAccept?.addEventListener('click', () => this.acceptConsent());
            consentDecline?.addEventListener('click', () => this.hideConsentDialog());
        }

        switchMode(mode) {
            const modeButtons = this.shadowRoot.querySelectorAll('.mode-button');
            const chatContainer = this.shadowRoot.querySelector('.chat-container');
            const voiceContainer = this.shadowRoot.querySelector('.voice-container');

            modeButtons.forEach(btn => btn.classList.remove('active'));
            this.shadowRoot.querySelector(`[data-mode="${mode}"]`).classList.add('active');

            chatContainer.classList.toggle('active', mode === 'chat');
            voiceContainer.classList.toggle('active', mode === 'voice');
            
            // Stop voice if switching away from voice mode
            if (mode !== 'voice' && this.isVoiceActive) {
                this.stopVoiceConversation();
            }
        }

        toggleWidget() {
            const panel = this.shadowRoot.getElementById('widgetPanel');
            const button = this.shadowRoot.getElementById('widgetToggle');
            
            this.isOpen = !this.isOpen;
            panel.classList.toggle('open', this.isOpen);
            button.textContent = this.isOpen ? '×' : '💬';
            
            // Stop voice if closing widget
            if (!this.isOpen && this.isVoiceActive) {
                this.stopVoiceConversation();
            }
        }

        async sendMessage() {
            const chatInput = this.shadowRoot.getElementById('chatInput');
            const sendButton = this.shadowRoot.getElementById('sendButton');
            const message = chatInput.value.trim();

            if (!message) return;

            // Add user message to UI
            this.addChatMessage(message, 'user');
            chatInput.value = '';
            sendButton.disabled = true;
            sendButton.textContent = 'Sending...';

            try {
                const response = await fetch(`${BASE_URL}/api/widget/chat/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: message,
                        session_id: this.sessionId,
                        api_key: this.config.apiKey,
                        assistant_id: this.config.assistantId,
                        language: 'auto'  // Enable auto language detection
                    })
                });

                const data = await response.json();

                if (data.status === 'success') {
                    this.sessionId = data.session_id;
                    this.addChatMessage(data.response, 'assistant');
                } else if (response.status === 429) {
                    // Quota exceeded
                    this.addChatMessage(`❌ ${data.message || 'Usage limit exceeded. Please upgrade your subscription.'}`, 'assistant error');
                } else {
                    this.addChatMessage('❌ Sorry, there was an error processing your message.', 'assistant error');
                }
            } catch (error) {
                console.error('Chat error:', error);
                this.addChatMessage('❌ Connection error. Please try again.', 'assistant error');
            }

            sendButton.disabled = false;
            sendButton.textContent = 'Send';
            chatInput.focus();
        }

        addChatMessage(text, sender) {
            const messagesContainer = this.shadowRoot.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${sender}`;
            
            const isError = sender.includes('error');
            const messageContent = document.createElement('div');
            messageContent.className = 'message-content';
            messageContent.innerHTML = text;
            
            if (isError) {
                messageContent.style.background = '#f8d7da';
                messageContent.style.color = '#721c24';
                messageContent.style.border = '1px solid #f5c6cb';
            }
            
            messageDiv.appendChild(messageContent);
            messagesContainer.appendChild(messageDiv);
            
            // Smooth scroll to bottom with better behavior
            setTimeout(() => {
                messagesContainer.scrollTo({
                    top: messagesContainer.scrollHeight,
                    behavior: 'smooth'
                });
            }, 100);
        }

        // ===== REALTIME VOICE FUNCTIONALITY =====
        
        async toggleVoiceConversation() {
            if (this.isVoiceConnecting) return;
            
            if (!this.isVoiceActive) {
                await this.startVoiceConversation();
            } else {
                this.stopVoiceConversation();
            }
        }

        async startVoiceConversation() {
            try {
                this.isVoiceConnecting = true;
                this.updateVoiceStatus('Connecting...', true);
                this.hideVoiceError();
                
                // Get WebSocket URL from API
                const response = await fetch(`${BASE_URL}/api/widget/voice/?api_key=${this.config.apiKey}&assistant_id=${this.config.assistantId}`);
                const data = await response.json();
                
                if (data.status !== 'success') {
                    if (response.status === 429) {
                        throw new Error(data.message || 'Usage limit exceeded');
                    }
                    throw new Error(data.error || 'Failed to get voice connection');
                }
                
                // Connect to WebSocket
                const wsUrl = data.websocket_url;
                this.voiceWebSocket = new WebSocket(wsUrl);
                
                this.voiceWebSocket.onopen = async () => {
                    console.log('Voice WebSocket connected');
                    this.isVoiceConnecting = false;
                    
                    // Initialize audio context and microphone
                    await this.initializeAudioContext();
                    
                    // Start voice session
                    this.voiceWebSocket.send(JSON.stringify({
                        type: 'start_voice',
                        language: 'auto'
                    }));
                };
                
                this.voiceWebSocket.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    this.handleVoiceMessage(data);
                };
                
                this.voiceWebSocket.onclose = () => {
                    console.log('Voice WebSocket closed');
                    this.cleanupVoice();
                };
                
                this.voiceWebSocket.onerror = (error) => {
                    console.error('Voice WebSocket error:', error);
                    this.showVoiceError('Connection error. Please try again.');
                    this.cleanupVoice();
                };
                
            } catch (error) {
                console.error('Voice start error:', error);
                this.showVoiceError(error.message);
                this.cleanupVoice();
            }
        }

        stopVoiceConversation() {
            if (this.voiceWebSocket) {
                this.voiceWebSocket.send(JSON.stringify({ type: 'stop_voice' }));
                this.voiceWebSocket.close();
            }
            this.cleanupVoice();
        }

        cleanupVoice() {
            this.isVoiceActive = false;
            this.isVoiceConnecting = false;
            this.voiceSessionId = null;
            
            // Stop audio recording
            if (this.audioStream) {
                this.audioStream.getTracks().forEach(track => track.stop());
                this.audioStream = null;
            }
            
            if (this.mediaRecorder) {
                this.mediaRecorder.stop();
                this.mediaRecorder = null;
            }
            
            // Close audio context
            if (this.audioContext) {
                this.audioContext.close();
                this.audioContext = null;
            }
            
            if (this.globalAudioContext) {
                this.globalAudioContext.close();
                this.globalAudioContext = null;
            }
            
            // Update UI
            this.updateVoiceButton(false);
            this.updateVoiceStatus('Click to start conversation');
        }

        async initializeAudioContext() {
            try {
                // Initialize audio context for playback
                this.globalAudioContext = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: 24000
                });
                
                if (this.globalAudioContext.state === 'suspended') {
                    await this.globalAudioContext.resume();
                }
                
                // Get microphone access
                this.audioStream = await navigator.mediaDevices.getUserMedia({ 
                    audio: {
                        sampleRate: 24000,
                        channelCount: 1,
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
                
                // Create audio context for recording
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: 24000
                });
                
                const source = this.audioContext.createMediaStreamSource(this.audioStream);
                
                // Use AudioWorklet for real-time audio processing
                if (this.audioContext.audioWorklet) {
                    try {
                        // Create inline AudioWorklet processor
                        const processorCode = `
                            class AudioProcessor extends AudioWorkletProcessor {
                                process(inputs, outputs, parameters) {
                                    const input = inputs[0];
                                    if (input.length > 0) {
                                        const channelData = input[0];
                                        
                                        // Convert float32 to int16 PCM
                                        const pcm16 = new Int16Array(channelData.length);
                                        for (let i = 0; i < channelData.length; i++) {
                                            pcm16[i] = Math.max(-32768, Math.min(32767, channelData[i] * 32768));
                                        }
                                        
                                        // Send PCM data to main thread
                                        this.port.postMessage({
                                            type: 'audio_data',
                                            data: pcm16.buffer
                                        });
                                    }
                                    return true;
                                }
                            }
                            registerProcessor('audio-processor', AudioProcessor);
                        `;
                        
                        const blob = new Blob([processorCode], { type: 'application/javascript' });
                        const processorUrl = URL.createObjectURL(blob);
                        
                        await this.audioContext.audioWorklet.addModule(processorUrl);
                        const processorNode = new AudioWorkletNode(this.audioContext, 'audio-processor');
                        
                        processorNode.port.onmessage = (event) => {
                            if (event.data.type === 'audio_data' && this.voiceWebSocket && this.voiceWebSocket.readyState === WebSocket.OPEN) {
                                // Convert ArrayBuffer to base64
                                const uint8Array = new Uint8Array(event.data.data);
                                let binaryString = '';
                                for (let i = 0; i < uint8Array.byteLength; i++) {
                                    binaryString += String.fromCharCode(uint8Array[i]);
                                }
                                const base64Audio = btoa(binaryString);
                                
                                this.voiceWebSocket.send(JSON.stringify({
                                    type: 'audio_data',
                                    audio: base64Audio
                                }));
                            }
                        };
                        
                        source.connect(processorNode);
                        processorNode.connect(this.audioContext.destination);
                        
                        console.log('Using AudioWorklet for audio processing');
                        
                    } catch (error) {
                        console.warn('AudioWorklet failed, falling back to ScriptProcessor:', error);
                        this.useScriptProcessor(source);
                    }
                } else {
                    this.useScriptProcessor(source);
                }
                
            } catch (error) {
                throw new Error(`Microphone access denied: ${error.message}`);
            }
        }
        
        useScriptProcessor(source) {
            const processor = this.audioContext.createScriptProcessor(4096, 1, 1);
            
            processor.onaudioprocess = (e) => {
                if (this.voiceWebSocket && this.voiceWebSocket.readyState === WebSocket.OPEN) {
                    const inputData = e.inputBuffer.getChannelData(0);
                    
                    // Convert float32 to int16 PCM
                    const pcm16 = new Int16Array(inputData.length);
                    for (let i = 0; i < inputData.length; i++) {
                        pcm16[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
                    }
                    
                    // Convert to base64
                    const uint8Array = new Uint8Array(pcm16.buffer);
                    let binaryString = '';
                    for (let i = 0; i < uint8Array.byteLength; i++) {
                        binaryString += String.fromCharCode(uint8Array[i]);
                    }
                    const base64Audio = btoa(binaryString);
                    
                    this.voiceWebSocket.send(JSON.stringify({
                        type: 'audio_data',
                        audio: base64Audio
                    }));
                }
            };
            
            source.connect(processor);
            processor.connect(this.audioContext.destination);
            
            console.log('Using ScriptProcessor for audio processing');
        }

        handleVoiceMessage(data) {
            console.log('Voice message received:', data.type);
            
            switch (data.type) {
                case 'connection_status':
                    this.updateVoiceStatus(data.message);
                    break;
                    
                case 'voice_started':
                    this.isVoiceActive = true;
                    this.voiceSessionId = data.session_id;
                    this.updateVoiceButton(true);
                    this.updateVoiceStatus('🟢 Listening... Speak naturally');
                    break;
                    
                case 'voice_stopped':
                    this.cleanupVoice();
                    break;
                    
                case 'user_transcript_delta':
                    // Show live transcription
                    this.updateVoiceStatus(`🎤 "${data.delta}"`);
                    break;
                    
                case 'user_transcript':
                    // Complete user transcription
                    if (data.transcript) {
                        this.addVoiceTranscript(data.transcript, 'user');
                        this.updateVoiceStatus('🤖 AI is responding...');
                    }
                    break;
                    
                case 'ai_response_text':
                    // AI text response
                    if (data.text) {
                        this.addVoiceTranscript(data.text, 'assistant');
                        this.updateVoiceStatus('🟢 Listening... Speak naturally');
                    }
                    break;
                    
                case 'ai_audio_delta':
                    // AI audio response chunk
                    if (data.audio) {
                        this.playAudioChunk(data.audio);
                    }
                    break;
                    
                case 'audio_buffer_start':
                    this.startAudioBuffer();
                    break;
                    
                case 'audio_buffer_complete':
                    this.completeAudioBuffer();
                    break;
                    
                case 'quota_exceeded':
                    this.showVoiceError(data.message || 'Usage limit exceeded');
                    this.cleanupVoice();
                    break;
                    
                case 'error':
                    this.showVoiceError(data.message || 'Voice error occurred');
                    break;
            }
        }

        updateVoiceButton(isActive) {
            const voiceButton = this.shadowRoot.getElementById('voiceButton');
            if (voiceButton) {
                if (isActive) {
                    voiceButton.classList.add('active');
                    voiceButton.textContent = '🛑';
                } else {
                    voiceButton.classList.remove('active');
                    voiceButton.textContent = '🎤';
                }
                voiceButton.disabled = this.isVoiceConnecting;
            }
        }

        updateVoiceStatus(status, isLoading = false) {
            const voiceStatus = this.shadowRoot.getElementById('voiceStatus');
            if (voiceStatus) {
                voiceStatus.textContent = status;
                voiceStatus.classList.toggle('loading', isLoading);
            }
        }

        showVoiceError(message) {
            const voiceError = this.shadowRoot.getElementById('voiceError');
            if (voiceError) {
                voiceError.textContent = message;
                voiceError.style.display = 'block';
            }
            this.updateVoiceStatus('Error occurred. Click to retry.');
        }

        hideVoiceError() {
            const voiceError = this.shadowRoot.getElementById('voiceError');
            if (voiceError) {
                voiceError.style.display = 'none';
            }
        }

        addVoiceTranscript(text, speaker) {
            if (this.config.voiceShowTranscript !== 'true') return;
            
            const transcript = this.shadowRoot.getElementById('voiceTranscript');
            if (transcript) {
                const entryDiv = document.createElement('div');
                entryDiv.className = 'transcript-entry';
                
                const speakerSpan = document.createElement('span');
                speakerSpan.className = speaker === 'user' ? 'transcript-user' : 'transcript-assistant';
                speakerSpan.textContent = speaker === 'user' ? 'You: ' : 'Assistant: ';
                
                const textSpan = document.createElement('span');
                textSpan.textContent = text;
                
                entryDiv.appendChild(speakerSpan);
                entryDiv.appendChild(textSpan);
                transcript.appendChild(entryDiv);
                transcript.scrollTop = transcript.scrollHeight;
            }
        }

        // Audio playback methods
        async playAudioChunk(audioData) {
            try {
                if (!audioData) return;
                
                if (this.isBuffering) {
                    this.audioChunksBuffer.push(audioData);
                } else {
                    await this.playAudioDirect(audioData);
                }
            } catch (error) {
                console.error('Error playing audio chunk:', error);
            }
        }

        async playAudioDirect(audioData) {
            try {
                if (!this.globalAudioContext) {
                    this.globalAudioContext = new (window.AudioContext || window.webkitAudioContext)({
                        sampleRate: 24000
                    });
                    
                    if (this.globalAudioContext.state === 'suspended') {
                        await this.globalAudioContext.resume();
                    }
                    
                    this.nextPlayTime = this.globalAudioContext.currentTime;
                }
                
                // Decode base64 to binary
                const binaryString = atob(audioData);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                
                // Convert PCM16 to AudioBuffer
                const pcm16Array = new Int16Array(bytes.buffer);
                
                if (pcm16Array.length > 0) {
                    const audioBuffer = this.globalAudioContext.createBuffer(1, pcm16Array.length, 24000);
                    const channelData = audioBuffer.getChannelData(0);
                    
                    // Convert int16 to float32
                    for (let i = 0; i < pcm16Array.length; i++) {
                        channelData[i] = pcm16Array[i] / 32768;
                    }
                    
                    // Create and schedule audio source
                    const source = this.globalAudioContext.createBufferSource();
                    source.buffer = audioBuffer;
                    source.connect(this.globalAudioContext.destination);
                    
                    // Schedule at next available time
                    const startTime = Math.max(this.nextPlayTime, this.globalAudioContext.currentTime);
                    source.start(startTime);
                    
                    // Update next play time
                    this.nextPlayTime = startTime + audioBuffer.duration;
                }
            } catch (error) {
                console.error('Error playing audio:', error);
            }
        }

        startAudioBuffer() {
            this.audioChunksBuffer = [];
            this.isBuffering = true;
        }

        async completeAudioBuffer() {
            this.isBuffering = false;
            
            // Play all buffered chunks in sequence
            for (const chunk of this.audioChunksBuffer) {
                await this.playAudioDirect(chunk);
            }
            
            this.audioChunksBuffer = [];
        }
    }

    // Register the custom element
    if (!customElements.get('ai-agent-widget')) {
        customElements.define('ai-agent-widget', AIAgentWidget);
    }

})();