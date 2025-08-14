/**
 * AI Agent Widget - Embeddable Chat & Voice Widget with Realtime Voice
 * Usage: <ai-agent-widget api-key="your-key" assistant-id="id" mode="chat" theme="light"></ai-agent-widget>
 */

(function() {
    'use strict';

    // Widget configuration defaults - Modern Standardized Design
    const DEFAULT_CONFIG = {
        mode: 'both', // Always enable both chat and voice
        theme: 'modern', // Standardized modern theme
        title: 'AI Assistant',
        chatFirstMessage: 'Hi there! 👋 How can I help you today?',
        chatPlaceholder: 'Type your message...',
        voiceShowTranscript: 'true',
        consentRequired: 'false',
        consentTitle: 'Privacy Notice',
        consentContent: 'This chat uses AI to provide assistance. Your conversations help us improve our service.',
        consentStorageKey: 'ai_agent_widget_consent'
    };

    // Base URL for API calls (will be set dynamically)
    let BASE_URL = '';

    // Detect the base URL from the script tag
    function detectBaseUrl() {
        const scripts = document.getElementsByTagName('script');
        for (let script of scripts) {
            if (script.src && (script.src.includes('widget.js') || script.src.includes('ai-agent-widget.js'))) {
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
        
        // Only use fallback for file:// protocol or invalid URLs
        if (BASE_URL.includes('file://') || (!BASE_URL.includes('http') && !BASE_URL)) {
            BASE_URL = 'http://127.0.0.1:8000';
            console.log('Development mode - fallback BASE_URL:', BASE_URL);
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
            // Define theme variables with custom color palette
            const isDark = this.config.theme === 'dark';
            
            // Custom Color Palette
            const colors = {
                primary: '#00ADB5',        // Cyan/Teal - for accent elements
                darkBg: '#222831',         // Dark gray - main dark background
                mediumBg: '#393E46',       // Medium gray - secondary elements
                lightBg: '#EEEEEE',        // Light gray - main light background
                text: isDark ? '#EEEEEE' : '#222831',
                textSecondary: isDark ? '#EEEEEE' : '#393E46',
                border: isDark ? '#393E46' : '#E0E0E0',
                shadow: isDark ? 'rgba(34, 40, 49, 0.3)' : 'rgba(57, 62, 70, 0.15)'
            };
            
            this.shadowRoot.innerHTML = `
                <style>
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }

                    :host {
                        position: fixed;
                        bottom: 24px;
                        right: 24px;
                        z-index: 9999;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', sans-serif;
                    }

                    /* Modern Toggle Button with Gradient */
                    .widget-toggle {
                        width: 64px;
                        height: 64px;
                        border-radius: 50%;
                        background: linear-gradient(135deg, ${colors.primary} 0%, ${colors.mediumBg} 100%);
                        color: white;
                        border: none;
                        cursor: pointer;
                        font-size: 24px;
                        box-shadow: 0 8px 32px rgba(0, 173, 181, 0.3);
                        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        backdrop-filter: blur(10px);
                        -webkit-backdrop-filter: blur(10px);
                        position: relative;
                        overflow: hidden;
                    }

                    .widget-toggle:before {
                        content: '';
                        position: absolute;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        background: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0.05) 100%);
                        border-radius: inherit;
                        transition: opacity 0.3s ease;
                    }

                    .widget-toggle:hover {
                        transform: scale(1.05) translateY(-2px);
                        box-shadow: 0 12px 48px rgba(0, 173, 181, 0.4);
                    }

                    .widget-toggle:active {
                        transform: scale(0.95);
                    }

                    /* Modern Widget Panel with Glassmorphism */
                    .widget-panel {
                        position: absolute;
                        bottom: 84px;
                        right: 0;
                        width: 400px;
                        height: 600px;
                        max-height: 85vh;
                        max-width: 95vw;
                        background: ${isDark ? colors.darkBg : colors.lightBg};
                        backdrop-filter: blur(20px);
                        -webkit-backdrop-filter: blur(20px);
                        border-radius: 24px;
                        border: 1px solid ${colors.border};
                        box-shadow: 0 20px 64px ${colors.shadow};
                        transform: scale(0.85) translateY(40px);
                        opacity: 0;
                        visibility: hidden;
                        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
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

                    /* Modern Gradient Header */
                    .widget-header {
                        background: linear-gradient(135deg, ${colors.primary} 0%, ${colors.mediumBg} 100%);
                        color: white;
                        padding: 20px;
                        text-align: center;
                        font-weight: 600;
                        font-size: 18px;
                        letter-spacing: -0.02em;
                        position: relative;
                        border-radius: 24px 24px 0 0;
                    }

                    .widget-header:before {
                        content: '';
                        position: absolute;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%);
                        border-radius: inherit;
                    }

                    /* Modern Mode Toggle */
                    .widget-modes {
                        display: flex;
                        background: ${isDark ? colors.mediumBg : 'rgba(238, 238, 238, 0.8)'};
                        backdrop-filter: blur(10px);
                        border-bottom: 1px solid ${colors.border};
                        padding: 8px;
                    }

                    .mode-button {
                        flex: 1;
                        padding: 12px 16px;
                        border: none;
                        background: transparent;
                        color: ${colors.textSecondary};
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 500;
                        border-radius: 12px;
                        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                        position: relative;
                        margin: 0 4px;
                    }

                    .mode-button.active {
                        background: rgba(0, 173, 181, 0.1);
                        color: ${colors.primary};
                        transform: translateY(-1px);
                    }

                    .mode-button:hover:not(.active) {
                        background: ${isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)'};
                        color: ${colors.text};
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
                        /* Ensure proper flex layout */
                        height: 100%;
                        min-height: 0;
                    }
                    
                    .chat-container.active, .voice-container.active {
                        display: flex;
                    }
                    
                    /* Modern Chat Messages Area - Fixed Scroll with Proper Flex */
                    .chat-messages {
                        flex: 1;
                        padding: 20px;
                        overflow-y: auto;
                        overflow-x: hidden;
                        background: transparent;
                        scrollbar-width: thin;
                        scrollbar-color: rgba(0, 173, 181, 0.3) transparent;
                        scroll-behavior: smooth;
                        /* Ensure it takes available space but doesn't overflow */
                        min-height: 0;
                        height: 0;
                    }
                    
                    .chat-messages::-webkit-scrollbar {
                        width: 4px;
                    }
                    
                    .chat-messages::-webkit-scrollbar-track {
                        background: transparent;
                    }
                    
                    .chat-messages::-webkit-scrollbar-thumb {
                        background: rgba(0, 173, 181, 0.2);
                        border-radius: 8px;
                    }
                    
                    .chat-messages::-webkit-scrollbar-thumb:hover {
                        background: rgba(0, 173, 181, 0.4);
                    }
                    
                    /* Modern Chat Messages */
                    .message {
                        margin-bottom: 20px;
                        display: flex;
                        max-width: 85%;
                        word-wrap: break-word;
                        overflow-wrap: break-word;
                        animation: slideIn 0.3s ease-out;
                    }
                    
                    @keyframes slideIn {
                        from {
                            opacity: 0;
                            transform: translateY(10px);
                        }
                        to {
                            opacity: 1;
                            transform: translateY(0);
                        }
                    }
                    
                    .message.user {
                        margin-left: auto;
                        justify-content: flex-end;
                    }
                    
                    .message.user .message-content {
                        background: linear-gradient(135deg, ${colors.primary} 0%, ${colors.mediumBg} 100%);
                        color: white;
                        border-radius: 20px 20px 4px 20px;
                        box-shadow: 0 4px 16px rgba(0, 173, 181, 0.2);
                    }
                    
                    .message.assistant .message-content {
                        background: ${isDark ? colors.mediumBg : 'rgba(238, 238, 238, 0.8)'};
                        color: ${colors.text};
                        border-radius: 20px 20px 20px 4px;
                        border: 1px solid ${colors.border};
                        backdrop-filter: blur(10px);
                    }
                    
                    .message-content {
                        padding: 14px 18px;
                        word-wrap: break-word;
                        overflow-wrap: break-word;
                        white-space: pre-wrap;
                        font-size: 14px;
                        line-height: 1.5;
                        max-width: 100%;
                        min-width: 0;
                        flex: 1;
                        font-weight: 400;
                        letter-spacing: -0.01em;
                    }

                    /* Modern Chat Input - Fixed Position */
                    .chat-input {
                        display: flex;
                        padding: 20px;
                        background: ${isDark ? colors.darkBg : colors.lightBg};
                        backdrop-filter: blur(10px);
                        border-top: 1px solid ${colors.border};
                        align-items: center;
                        gap: 12px;
                        border-radius: 0 0 24px 24px;
                        /* Ensure input stays at bottom */
                        flex-shrink: 0;
                        position: relative;
                        z-index: 1;
                    }

                    .chat-input input {
                        flex: 1;
                        padding: 14px 18px;
                        border: 1px solid ${colors.border};
                        border-radius: 24px;
                        background: ${isDark ? colors.mediumBg : 'rgba(255, 255, 255, 0.9)'};
                        color: ${colors.text};
                        outline: none;
                        font-size: 14px;
                        font-weight: 400;
                        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                        backdrop-filter: blur(10px);
                    }

                    .chat-input input:focus {
                        border-color: ${colors.primary};
                        box-shadow: 0 0 0 3px rgba(0, 173, 181, 0.1);
                        background: ${isDark ? colors.mediumBg : 'rgba(255, 255, 255, 1)'};
                    }

                    .chat-input input::placeholder {
                        color: ${colors.textSecondary};
                        opacity: 0.7;
                    }

                    .chat-input button {
                        padding: 14px 18px;
                        background: linear-gradient(135deg, ${colors.primary} 0%, ${colors.mediumBg} 100%);
                        color: white;
                        border: none;
                        border-radius: 24px;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 500;
                        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                        box-shadow: 0 4px 16px rgba(0, 173, 181, 0.2);
                        min-width: 60px;
                    }

                    .chat-input button:hover:not(:disabled) {
                        transform: translateY(-1px);
                        box-shadow: 0 6px 20px rgba(0, 173, 181, 0.3);
                    }

                    .chat-input button:active:not(:disabled) {
                        transform: translateY(0);
                    }

                    .chat-input button:disabled {
                        opacity: 0.5;
                        cursor: not-allowed;
                        transform: none;
                        box-shadow: 0 4px 16px rgba(0, 173, 181, 0.1);
                    }

                    /* Voice Container Styles */
                    .voice-container {
                        padding: 20px;
                        text-align: center;
                        background: ${isDark ? colors.darkBg : colors.lightBg};
                    }
                    
                    .voice-status {
                        color: ${colors.text};
                        margin-bottom: 20px;
                        font-size: 16px;
                        font-weight: 500;
                    }
                    
                    .voice-button {
                        width: 100px;
                        height: 100px;
                        border-radius: 50%;
                        background: ${colors.primary};
                        color: white;
                        border: none;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 32px;
                        margin: 20px auto;
                        transition: all 0.3s ease;
                        box-shadow: 0 4px 15px ${colors.shadow};
                    }
                    
                    .voice-button:hover {
                        transform: scale(1.05);
                    }
                    
                    .voice-button.active {
                        background: ${colors.mediumBg};
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
                        color: ${this.config.accentColor || '#007bff'};
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
                        background: ${this.config.accentColor || '#007bff'};
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
                        
                        .widget-content {
                            height: calc(100vh - 140px);
                        }
                        
                        .chat-container {
                            height: 100%;
                        }
                        
                        .chat-messages {
                            /* Make sure messages area doesn't push input out */
                            flex: 1;
                            min-height: 0;
                            height: calc(100% - 100px);
                        }
                        
                        .chat-input {
                            /* Fixed at bottom on mobile */
                            position: sticky;
                            bottom: 0;
                            flex-shrink: 0;
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
                            height: 600px;
                            max-height: 80vh;
                        }
                        
                        .widget-content {
                            height: calc(100% - 120px);
                        }
                        
                        .chat-container {
                            height: 100%;
                        }
                        
                        .chat-messages {
                            flex: 1;
                            min-height: 0;
                            height: calc(100% - 100px);
                        }
                        
                        .chat-input {
                            flex-shrink: 0;
                        }
                    }
                </style>

                <div class="widget-toggle" id="widgetToggle">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
                    </svg>
                </div>
                
                <div class="widget-panel" id="widgetPanel">
                    <div class="widget-header">
                        ${this.config.title}
                    </div>
                    
                    <div class="widget-modes">
                        <button class="mode-button active" data-mode="chat">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="margin-right: 8px;">
                                <path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
                            </svg>
                            Chat
                        </button>
                        <button class="mode-button" data-mode="voice">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="margin-right: 8px;">
                                <path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
                            </svg>
                            Voice
                        </button>
                    </div>
                    
                    <div class="widget-content">
                        <div class="chat-container active">
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
                        
                        <div class="voice-container">
                            <div class="voice-status" id="voiceStatus">Click to start conversation</div>
                            <button class="voice-button" id="voiceButton">
                                <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
                                </svg>
                            </button>
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
            
            // Update button icon with SVG
            if (this.isOpen) {
                button.innerHTML = `
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                    </svg>
                `;
            } else {
                button.innerHTML = `
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
                    </svg>
                `;
            }
            
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
                    this.updateVoiceStatus('Listening... Speak naturally');
                    break;
                    
                case 'voice_stopped':
                    this.cleanupVoice();
                    break;
                    
                case 'user_transcript_delta':
                    // Show live transcription
                    this.updateVoiceStatus(`"${data.delta}"`);
                    break;
                    
                case 'user_transcript':
                    // Complete user transcription
                    if (data.transcript) {
                        this.addVoiceTranscript(data.transcript, 'user');
                        this.updateVoiceStatus('AI is responding...');
                    }
                    break;
                    
                case 'ai_response_text':
                    // AI text response
                    if (data.text) {
                        this.addVoiceTranscript(data.text, 'assistant');
                        this.updateVoiceStatus('Listening... Speak naturally');
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
                    // Stop icon (square)
                    voiceButton.innerHTML = `
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M6 6h12v12H6z"/>
                        </svg>
                    `;
                } else {
                    voiceButton.classList.remove('active');
                    // Microphone icon
                    voiceButton.innerHTML = `
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/>
                        </svg>
                    `;
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