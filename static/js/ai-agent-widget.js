/**
 * AI Agent Widget - Embeddable Chat & Voice Widget
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
            this.isRecording = false;
            this.mediaRecorder = null;
            this.audioChunks = [];
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
            const consentOverlay = this.shadowRoot.querySelector('.consent-overlay');
            if (consentOverlay) {
                consentOverlay.style.display = 'flex';
            }
        }

        hideConsentDialog() {
            const consentOverlay = this.shadowRoot.querySelector('.consent-overlay');
            if (consentOverlay) {
                consentOverlay.style.display = 'none';
            }
        }

        acceptConsent() {
            localStorage.setItem(this.config.consentStorageKey, 'true');
            this.hideConsentDialog();
        }

        getBorderRadiusValue() {
            const radiusMap = {
                'small': '4px',
                'medium': '8px',
                'large': '16px'
            };
            return radiusMap[this.config.borderRadius] || '8px';
        }

        getSizeConfig() {
            const sizeMap = {
                'small': { width: '300px', height: '400px' },
                'medium': { width: '350px', height: '500px' },
                'large': { width: '400px', height: '600px' },
                'full': { width: '100vw', height: '100vh' }
            };
            return sizeMap[this.config.size] || sizeMap.medium;
        }

        getPositionStyles() {
            const positionMap = {
                'bottom-right': { bottom: '20px', right: '20px' },
                'bottom-left': { bottom: '20px', left: '20px' },
                'top-right': { top: '20px', right: '20px' },
                'top-left': { top: '20px', left: '20px' }
            };
            return positionMap[this.config.position] || positionMap['bottom-right'];
        }

        render() {
            const sizeConfig = this.getSizeConfig();
            const positionStyles = this.getPositionStyles();
            const borderRadius = this.getBorderRadiusValue();
            const isDark = this.config.theme === 'dark';

            this.shadowRoot.innerHTML = `
                <style>
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }
                    
                    .widget-container {
                        position: fixed;
                        ${Object.entries(positionStyles).map(([key, value]) => `${key}: ${value}`).join('; ')};
                        z-index: 10000;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    }
                    
                    .widget-button {
                        width: 60px;
                        height: 60px;
                        border-radius: 50%;
                        background: ${this.config.ctaButtonColor};
                        color: ${this.config.ctaButtonTextColor};
                        border: none;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 24px;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                        transition: all 0.3s ease;
                    }
                    
                    .widget-button:hover {
                        transform: scale(1.05);
                        box-shadow: 0 6px 16px rgba(0,0,0,0.2);
                    }
                    
                    .widget-panel {
                        position: absolute;
                        bottom: 80px;
                        right: 0;
                        width: ${sizeConfig.width};
                        height: ${sizeConfig.height};
                        background: ${this.config.baseBgColor};
                        border-radius: ${borderRadius};
                        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                        display: none;
                        flex-direction: column;
                        overflow: hidden;
                        border: 1px solid ${isDark ? '#333' : '#e1e5e9'};
                    }
                    
                    .widget-panel.open {
                        display: flex;
                        animation: slideUp 0.3s ease;
                    }
                    
                    @keyframes slideUp {
                        from {
                            opacity: 0;
                            transform: translateY(20px);
                        }
                        to {
                            opacity: 1;
                            transform: translateY(0);
                        }
                    }
                    
                    .widget-header {
                        background: ${this.config.accentColor};
                        color: white;
                        padding: 16px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }
                    
                    .widget-title {
                        font-weight: 600;
                        font-size: 16px;
                    }
                    
                    .close-button {
                        background: none;
                        border: none;
                        color: white;
                        cursor: pointer;
                        font-size: 20px;
                        padding: 4px;
                        border-radius: 4px;
                    }
                    
                    .close-button:hover {
                        background: rgba(255,255,255,0.1);
                    }
                    
                    .mode-selector {
                        display: flex;
                        background: ${isDark ? '#2a2a2a' : '#f8f9fa'};
                        border-bottom: 1px solid ${isDark ? '#333' : '#e1e5e9'};
                    }
                    
                    .mode-button {
                        flex: 1;
                        padding: 12px;
                        background: none;
                        border: none;
                        cursor: pointer;
                        color: ${isDark ? '#fff' : '#666'};
                        transition: all 0.2s ease;
                    }
                    
                    .mode-button.active {
                        background: ${this.config.accentColor};
                        color: white;
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
                        background: ${isDark ? '#1a1a1a' : '#ffffff'};
                    }
                    
                    .message {
                        margin-bottom: 12px;
                        max-width: 80%;
                    }
                    
                    .message.user {
                        margin-left: auto;
                    }
                    
                    .message-content {
                        padding: 8px 12px;
                        border-radius: 12px;
                        font-size: 14px;
                        line-height: 1.4;
                    }
                    
                    .message.user .message-content {
                        background: ${this.config.accentColor};
                        color: white;
                    }
                    
                    .message.assistant .message-content {
                        background: ${isDark ? '#333' : '#f1f3f4'};
                        color: ${isDark ? '#fff' : '#333'};
                    }
                    
                    .chat-input {
                        padding: 16px;
                        border-top: 1px solid ${isDark ? '#333' : '#e1e5e9'};
                        background: ${isDark ? '#2a2a2a' : '#ffffff'};
                    }
                    
                    .input-group {
                        display: flex;
                        gap: 8px;
                    }
                    
                    .message-input {
                        flex: 1;
                        padding: 10px 12px;
                        border: 1px solid ${isDark ? '#444' : '#ddd'};
                        border-radius: 20px;
                        background: ${isDark ? '#333' : '#fff'};
                        color: ${isDark ? '#fff' : '#333'};
                        outline: none;
                        font-size: 14px;
                    }
                    
                    .message-input:focus {
                        border-color: ${this.config.accentColor};
                    }
                    
                    .send-button {
                        width: 40px;
                        height: 40px;
                        border-radius: 50%;
                        background: ${this.config.accentColor};
                        color: white;
                        border: none;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    
                    .send-button:hover {
                        opacity: 0.9;
                    }
                    
                    .voice-container {
                        padding: 20px;
                        text-align: center;
                        background: ${isDark ? '#1a1a1a' : '#ffffff'};
                    }
                    
                    .voice-button {
                        width: 80px;
                        height: 80px;
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
                    }
                    
                    .voice-button:hover {
                        transform: scale(1.05);
                    }
                    
                    .voice-button.recording {
                        background: #dc3545;
                        animation: pulse 1s infinite;
                    }
                    
                    @keyframes pulse {
                        0% { transform: scale(1); }
                        50% { transform: scale(1.1); }
                        100% { transform: scale(1); }
                    }
                    
                    .voice-status {
                        color: ${isDark ? '#fff' : '#666'};
                        margin-bottom: 10px;
                    }
                    
                    .voice-transcript {
                        background: ${isDark ? '#333' : '#f8f9fa'};
                        padding: 12px;
                        border-radius: 8px;
                        margin-top: 16px;
                        color: ${isDark ? '#fff' : '#333'};
                        font-size: 14px;
                        min-height: 100px;
                        text-align: left;
                    }
                    
                    .consent-overlay {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100vw;
                        height: 100vh;
                        background: rgba(0,0,0,0.5);
                        display: none;
                        align-items: center;
                        justify-content: center;
                        z-index: 10001;
                    }
                    
                    .consent-dialog {
                        background: white;
                        padding: 24px;
                        border-radius: 12px;
                        max-width: 400px;
                        margin: 20px;
                    }
                    
                    .consent-title {
                        font-weight: 600;
                        margin-bottom: 12px;
                        color: #333;
                    }
                    
                    .consent-content {
                        margin-bottom: 20px;
                        line-height: 1.5;
                        color: #666;
                        font-size: 14px;
                    }
                    
                    .consent-buttons {
                        display: flex;
                        gap: 12px;
                        justify-content: flex-end;
                    }
                    
                    .consent-button {
                        padding: 8px 16px;
                        border: none;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 14px;
                    }
                    
                    .consent-accept {
                        background: ${this.config.accentColor};
                        color: white;
                    }
                    
                    .consent-decline {
                        background: #6c757d;
                        color: white;
                    }
                    
                    .typing-indicator {
                        display: flex;
                        gap: 3px;
                        padding: 8px 12px;
                        align-items: center;
                    }
                    
                    .typing-dot {
                        width: 6px;
                        height: 6px;
                        background: #999;
                        border-radius: 50%;
                        animation: typing 1.4s infinite;
                    }
                    
                    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
                    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
                    
                    @keyframes typing {
                        0%, 60%, 100% { transform: translateY(0); }
                        30% { transform: translateY(-10px); }
                    }
                </style>
                
                <div class="widget-container">
                    <button class="widget-button" id="widgetToggle">
                        💬
                    </button>
                    
                    <div class="widget-panel" id="widgetPanel">
                        <div class="widget-header">
                            <div class="widget-title">${this.config.title}</div>
                            <button class="close-button" id="closeButton">×</button>
                        </div>
                        
                        ${this.config.mode === 'both' ? `
                        <div class="mode-selector">
                            <button class="mode-button active" data-mode="chat">💬 Chat</button>
                            <button class="mode-button" data-mode="voice">🎤 Voice</button>
                        </div>
                        ` : ''}
                        
                        <div class="chat-container ${this.config.mode === 'chat' || this.config.mode === 'both' ? 'active' : ''}">
                            <div class="chat-messages" id="chatMessages">
                                <div class="message assistant">
                                    <div class="message-content">${this.config.chatFirstMessage}</div>
                                </div>
                            </div>
                            <div class="chat-input">
                                <div class="input-group">
                                    <input type="text" class="message-input" placeholder="${this.config.chatPlaceholder}" id="messageInput">
                                    <button class="send-button" id="sendButton">➤</button>
                                </div>
                            </div>
                        </div>
                        
                        <div class="voice-container ${this.config.mode === 'voice' ? 'active' : ''}">
                            <div class="voice-status" id="voiceStatus">Click to start recording</div>
                            <button class="voice-button" id="voiceButton">🎤</button>
                            ${this.config.voiceShowTranscript === 'true' ? '<div class="voice-transcript" id="voiceTranscript">Transcript will appear here...</div>' : ''}
                        </div>
                    </div>
                    
                    ${this.config.consentRequired === 'true' ? `
                    <div class="consent-overlay" id="consentOverlay">
                        <div class="consent-dialog">
                            <div class="consent-title">${this.config.consentTitle}</div>
                            <div class="consent-content">${this.config.consentContent}</div>
                            <div class="consent-buttons">
                                <button class="consent-button consent-decline" id="consentDecline">Decline</button>
                                <button class="consent-button consent-accept" id="consentAccept">Agree</button>
                            </div>
                        </div>
                    </div>
                    ` : ''}
                </div>
            `;
        }

        attachEventListeners() {
            const toggleButton = this.shadowRoot.getElementById('widgetToggle');
            const closeButton = this.shadowRoot.getElementById('closeButton');
            const panel = this.shadowRoot.getElementById('widgetPanel');
            const sendButton = this.shadowRoot.getElementById('sendButton');
            const messageInput = this.shadowRoot.getElementById('messageInput');
            const voiceButton = this.shadowRoot.getElementById('voiceButton');
            const consentAccept = this.shadowRoot.getElementById('consentAccept');
            const consentDecline = this.shadowRoot.getElementById('consentDecline');

            // Mode selector
            const modeButtons = this.shadowRoot.querySelectorAll('.mode-button');
            modeButtons.forEach(button => {
                button.addEventListener('click', () => this.switchMode(button.dataset.mode));
            });

            // Widget toggle
            toggleButton?.addEventListener('click', () => this.toggleWidget());
            closeButton?.addEventListener('click', () => this.closeWidget());

            // Chat functionality
            sendButton?.addEventListener('click', () => this.sendMessage());
            messageInput?.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.sendMessage();
            });

            // Voice functionality
            voiceButton?.addEventListener('click', () => this.toggleVoiceRecording());

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
        }

        toggleWidget() {
            const panel = this.shadowRoot.getElementById('widgetPanel');
            const button = this.shadowRoot.getElementById('widgetToggle');
            
            this.isOpen = !this.isOpen;
            panel.classList.toggle('open', this.isOpen);
            button.textContent = this.isOpen ? '×' : '💬';
        }

        closeWidget() {
            this.isOpen = false;
            const panel = this.shadowRoot.getElementById('widgetPanel');
            const button = this.shadowRoot.getElementById('widgetToggle');
            
            panel.classList.remove('open');
            button.textContent = '💬';
        }

        async sendMessage() {
            const input = this.shadowRoot.getElementById('messageInput');
            const message = input.value.trim();
            
            if (!message) return;

            input.value = '';
            this.addMessage(message, 'user');
            this.showTypingIndicator();

            try {
                const response = await this.sendChatRequest(message);
                this.hideTypingIndicator();
                
                if (response.status === 'success') {
                    this.sessionId = response.session_id;
                    this.addMessage(response.response, 'assistant');
                } else {
                    console.error('Server error response:', response);
                    const errorMsg = response.error || 'Unknown error';
                    this.addMessage(`Error: ${errorMsg}. Please try again.`, 'assistant');
                }
            } catch (error) {
                this.hideTypingIndicator();
                this.addMessage(`Network Error: ${error.message}. Please check connection and try again.`, 'assistant');
                console.error('Chat error:', error);
            }
        }

        async sendChatRequest(message) {
            const requestData = {
                message: message,
                api_key: this.config.apiKey,
                assistant_id: this.config.assistantId,
                session_id: this.sessionId
            };
            
            console.log('Sending chat request:', requestData);
            console.log('BASE_URL:', BASE_URL);
            
            const response = await fetch(`${BASE_URL}/api/widget/chat/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            console.log('Response status:', response.status);
            console.log('Response ok:', response.ok);

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Response error:', errorText);
                throw new Error(`Network response was not ok: ${response.status}`);
            }

            const responseData = await response.json();
            console.log('Response data:', responseData);
            return responseData;
        }

        addMessage(content, type) {
            const messagesContainer = this.shadowRoot.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${type}`;
            messageDiv.innerHTML = `<div class="message-content">${content}</div>`;
            
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        showTypingIndicator() {
            const messagesContainer = this.shadowRoot.getElementById('chatMessages');
            const typingDiv = document.createElement('div');
            typingDiv.className = 'message assistant typing-indicator';
            typingDiv.id = 'typingIndicator';
            typingDiv.innerHTML = `
                <div class="message-content">
                    <div class="typing-indicator">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>
                </div>
            `;
            
            messagesContainer.appendChild(typingDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        hideTypingIndicator() {
            const typingIndicator = this.shadowRoot.getElementById('typingIndicator');
            if (typingIndicator) {
                typingIndicator.remove();
            }
        }

        async toggleVoiceRecording() {
            if (!this.isRecording) {
                await this.startRecording();
            } else {
                this.stopRecording();
            }
        }

        async startRecording() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                this.mediaRecorder = new MediaRecorder(stream);
                this.audioChunks = [];

                this.mediaRecorder.ondataavailable = (event) => {
                    this.audioChunks.push(event.data);
                };

                this.mediaRecorder.onstop = () => {
                    this.processVoiceRecording();
                };

                this.mediaRecorder.start();
                this.isRecording = true;

                const voiceButton = this.shadowRoot.getElementById('voiceButton');
                const voiceStatus = this.shadowRoot.getElementById('voiceStatus');
                
                voiceButton.classList.add('recording');
                voiceButton.textContent = '⏹️';
                voiceStatus.textContent = 'Recording... Click to stop';

            } catch (error) {
                console.error('Error starting recording:', error);
                this.updateVoiceStatus('Error: Could not access microphone');
            }
        }

        stopRecording() {
            if (this.mediaRecorder && this.isRecording) {
                this.mediaRecorder.stop();
                this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
                this.isRecording = false;

                const voiceButton = this.shadowRoot.getElementById('voiceButton');
                const voiceStatus = this.shadowRoot.getElementById('voiceStatus');
                
                voiceButton.classList.remove('recording');
                voiceButton.textContent = '🎤';
                voiceStatus.textContent = 'Processing...';
            }
        }

        async processVoiceRecording() {
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.webm');
            formData.append('api_key', this.config.apiKey);
            formData.append('assistant_id', this.config.assistantId);
            formData.append('session_id', this.sessionId || '');

            try {
                const response = await fetch(`${BASE_URL}/api/widget/voice/`, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                
                if (data.status === 'success') {
                    this.sessionId = data.session_id;
                    this.updateVoiceTranscript(data.transcribed_text, data.response_text);
                    
                    // Play audio response if available
                    if (data.audio_response) {
                        this.playAudioResponse(data.audio_response);
                    }
                } else {
                    this.updateVoiceStatus('Error processing voice message');
                }
            } catch (error) {
                console.error('Voice processing error:', error);
                this.updateVoiceStatus('Error processing voice message');
            }

            this.updateVoiceStatus('Click to start recording');
        }

        updateVoiceStatus(status) {
            const voiceStatus = this.shadowRoot.getElementById('voiceStatus');
            if (voiceStatus) {
                voiceStatus.textContent = status;
            }
        }

        updateVoiceTranscript(userText, assistantText) {
            if (this.config.voiceShowTranscript !== 'true') return;
            
            const transcript = this.shadowRoot.getElementById('voiceTranscript');
            if (transcript) {
                transcript.innerHTML += `
                    <div style="margin-bottom: 8px;"><strong>You:</strong> ${userText}</div>
                    <div style="margin-bottom: 12px;"><strong>Assistant:</strong> ${assistantText}</div>
                `;
                transcript.scrollTop = transcript.scrollHeight;
            }
        }

        playAudioResponse(audioBase64) {
            const audio = new Audio(`data:audio/mpeg;base64,${audioBase64}`);
            audio.play().catch(error => {
                console.error('Error playing audio:', error);
            });
        }
    }

    // Register the custom element
    if (!customElements.get('ai-agent-widget')) {
        customElements.define('ai-agent-widget', AIAgentWidget);
    }

})();