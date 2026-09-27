// Gemini AI Assistant & Intelligent Suite JavaScript

document.addEventListener('DOMContentLoaded', () => {
    initGeminiAIAssistantWidget();
    initGeminiAIVoiceSearch();
    initGeminiAISellerDescriptionGenerator();
    initGeminiAIProjectManagerDashboard();
});

// Helper: Convert Gemini Markdown format into clean HTML
function formatMarkdownToHTML(markdownText) {
    if (!markdownText) return '';
    let str = String(markdownText);

    // Headers ### Title
    str = str.replace(/^###\s*(.*$)/gim, '<h4 style="margin: 0.6rem 0 0.3rem; color: #4338ca; font-weight: 700; font-size: 0.98rem;">$1</h4>');
    str = str.replace(/^##\s*(.*$)/gim, '<h3 style="margin: 0.7rem 0 0.4rem; color: #3730a3; font-weight: 800; font-size: 1.05rem;">$1</h3>');
    str = str.replace(/^#\s*(.*$)/gim, '<h2 style="margin: 0.8rem 0 0.5rem; color: #312e81; font-weight: 800; font-size: 1.15rem;">$1</h2>');

    // Bold **text**
    str = str.replace(/\*\*(.*?)\*\*/g, '<strong style="color: var(--text-primary); font-weight: 700;">$1</strong>');
    
    // Italic *text*
    str = str.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Bullet list lines "- item" or "* item"
    const lines = str.split('\n');
    let inList = false;
    let resultLines = [];

    for (let line of lines) {
        let trimmed = line.trim();
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            if (!inList) {
                resultLines.push('<ul style="margin: 0.4rem 0; padding-left: 1.25rem; font-size: 0.88rem; line-height: 1.5;">');
                inList = true;
            }
            resultLines.push(`<li style="margin-bottom: 0.3rem;">${trimmed.substring(2)}</li>`);
        } else {
            if (inList) {
                resultLines.push('</ul>');
                inList = false;
            }
            if (trimmed.length > 0) {
                resultLines.push(`<p style="margin: 0.3rem 0; line-height: 1.5;">${trimmed}</p>`);
            }
        }
    }
    if (inList) {
        resultLines.push('</ul>');
    }

    return resultLines.join('');
}

// 1. Floating Storefront Gemini AI Shopping Assistant Drawer Widget
function initGeminiAIAssistantWidget() {
    if (document.getElementById('gemini-ai-floating-btn')) return;

    const btn = document.createElement('button');
    btn.id = 'gemini-ai-floating-btn';
    btn.className = 'gemini-ai-floating-btn';
    btn.setAttribute('aria-label', 'Open Gemini AI Shopping Assistant');
    btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Ask Gemini AI</span>`;
    document.body.appendChild(btn);

    const drawer = document.createElement('div');
    drawer.id = 'gemini-ai-drawer';
    drawer.className = 'gemini-ai-drawer hidden';
    drawer.innerHTML = `
        <div class="gemini-ai-header">
            <div class="gemini-ai-title">
                <i class="fa-solid fa-sparkles" style="color: #60a5fa;"></i>
                <span>Gemini AI Store Assistant</span>
            </div>
            <button class="gemini-ai-close" id="gemini-ai-close-btn" title="Close AI Assistant">&times;</button>
        </div>
        <div class="gemini-ai-body" id="gemini-ai-body">
            <div class="gemini-msg bot">
                👋 Hello! I am your <strong>Gemini AI Store Assistant</strong>. Ask me for product advice, shopping recommendations, or deals!
            </div>
            <div style="display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.25rem;" id="gemini-ai-prompts">
                <button class="gemini-ai-badge-btn" onclick="sendGeminiPreset('Top smartphone picks under 20000')">📱 Phone deals</button>
                <button class="gemini-ai-badge-btn" onclick="sendGeminiPreset('Best running shoes')">👟 Running Shoes</button>
                <button class="gemini-ai-badge-btn" onclick="sendGeminiPreset('Gift recommendations for friend')">🎁 Gift Ideas</button>
            </div>
        </div>
        <form class="gemini-ai-footer" id="gemini-ai-form">
            <input type="text" id="gemini-ai-input" class="gemini-ai-input" placeholder="Ask Gemini AI (e.g. best shoes under 2000)..." autocomplete="off">
            <button type="submit" class="gemini-ai-send" title="Send"><i class="fa-solid fa-paper-plane"></i></button>
        </form>
    `;
    document.body.appendChild(drawer);

    btn.addEventListener('click', () => {
        drawer.classList.toggle('hidden');
        if (!drawer.classList.contains('hidden')) {
            document.getElementById('gemini-ai-input').focus();
        }
    });

    document.getElementById('gemini-ai-close-btn').addEventListener('click', () => {
        drawer.classList.add('hidden');
    });

    document.getElementById('gemini-ai-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const input = document.getElementById('gemini-ai-input');
        const text = input.value.trim();
        if (!text) return;
        
        appendGeminiMessage(text, 'user');
        input.value = '';

        appendGeminiThinking();

        fetch('/api/ai/project-assistant', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({ message: text })
        })
        .then(r => r.json())
        .then(data => {
            removeGeminiThinking();
            if (data && data.reply) {
                appendGeminiMessage(data.reply, 'bot');
            } else {
                appendGeminiMessage("I found great catalog items for you! Explore our latest products.", 'bot');
            }
        })
        .catch(err => {
            removeGeminiThinking();
            appendGeminiMessage("Gemini AI processed your request! Check out our catalog products.", 'bot');
        });
    });
}

function sendGeminiPreset(promptText) {
    const input = document.getElementById('gemini-ai-input');
    if (input) {
        input.value = promptText;
        document.getElementById('gemini-ai-form').dispatchEvent(new Event('submit'));
    }
}

function appendGeminiMessage(content, sender) {
    const body = document.getElementById('gemini-ai-body');
    if (!body) return;

    const msg = document.createElement('div');
    msg.className = `gemini-msg ${sender}`;
    msg.innerHTML = sender === 'bot' ? formatMarkdownToHTML(content) : content;
    body.appendChild(msg);
    body.scrollTop = body.scrollHeight;
}

function appendGeminiThinking() {
    const body = document.getElementById('gemini-ai-body');
    if (!body) return;
    const thinking = document.createElement('div');
    thinking.id = 'gemini-ai-thinking';
    thinking.className = 'gemini-msg bot';
    thinking.innerHTML = `<i class="fa-solid fa-spinner fa-spin" style="color: #2563eb;"></i> Gemini AI is analyzing...`;
    body.appendChild(thinking);
    body.scrollTop = body.scrollHeight;
}

function removeGeminiThinking() {
    const thinking = document.getElementById('gemini-ai-thinking');
    if (thinking) thinking.remove();
}

// 2. Intelligent Gemini AI Speech Voice Recognition & Query Parsing
function initGeminiAIVoiceSearch() {
    const voiceBtn = document.getElementById('voice-search-btn');
    const searchInput = document.getElementById('search-input');
    const searchForm = document.getElementById('search-form');
    if (!voiceBtn || !searchInput) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    voiceBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();

        if (SpeechRecognition) {
            try {
                const recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = false;
                recognition.lang = 'en-US';

                voiceBtn.style.color = '#ef4444';
                voiceBtn.style.transform = 'scale(1.2)';
                searchInput.placeholder = "🎤 Listening... Speak now in English or Tamil...";

                recognition.onresult = (event) => {
                    const transcript = event.results[0][0].transcript;
                    searchInput.value = transcript;
                    searchInput.placeholder = "✨ Gemini AI parsing voice intent...";

                    fetch('/api/ai/voice-parse', {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
                        },
                        body: JSON.stringify({ text: transcript })
                    })
                    .then(r => r.json())
                    .then(data => {
                        if (data && data.search_query) {
                            searchInput.value = data.search_query;
                        }
                        if (searchForm) searchForm.submit();
                    })
                    .catch(() => {
                        if (searchForm) searchForm.submit();
                    })
                    .finally(() => {
                        voiceBtn.style.color = '';
                        voiceBtn.style.transform = '';
                    });
                };

                recognition.onerror = (err) => {
                    voiceBtn.style.color = '';
                    voiceBtn.style.transform = '';
                    console.warn('Voice speech recognition error:', err);
                    fallbackVoicePrompt(searchInput, searchForm);
                };

                recognition.onend = () => {
                    voiceBtn.style.color = '';
                    voiceBtn.style.transform = '';
                };

                recognition.start();
            } catch (err) {
                fallbackVoicePrompt(searchInput, searchForm);
            }
        } else {
            fallbackVoicePrompt(searchInput, searchForm);
        }
    });
}

function fallbackVoicePrompt(searchInput, searchForm) {
    const userVoiceText = prompt("Voice Typing Search: Type or speak your product query:");
    if (userVoiceText && userVoiceText.trim()) {
        searchInput.value = userVoiceText.trim();
        if (searchForm) searchForm.submit();
    }
}

// 3. Seller Product Form AI Generator
function initGeminiAISellerDescriptionGenerator() {
    const nameInput = document.getElementById('product-name-input') || document.querySelector('input[name="name"]');
    const descTextarea = document.getElementById('product-desc-textarea') || document.querySelector('textarea[name="description"]');
    if (!nameInput || !descTextarea) return;

    if (document.getElementById('ai-generate-desc-btn')) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'ai-generate-desc-btn';
    btn.className = 'btn btn-secondary';
    btn.style.cssText = 'margin-top: 0.5rem; background: linear-gradient(135deg, #2563eb, #7c3aed); color: #fff; font-weight: 600; border: none;';
    btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Auto-Generate Description with Gemini AI`;

    descTextarea.parentElement.appendChild(btn);

    btn.addEventListener('click', () => {
        const prodName = nameInput.value.trim();
        if (!prodName) {
            alert('Please enter a Product Name first before generating description with Gemini AI.');
            nameInput.focus();
            return;
        }

        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Generating with Gemini AI...`;

        const categorySelect = document.querySelector('select[name="category_id"]');
        const catName = categorySelect && categorySelect.options[categorySelect.selectedIndex] ? categorySelect.options[categorySelect.selectedIndex].text : 'General';

        fetch('/api/ai/seller-generate-desc', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({ name: prodName, category: catName })
        })
        .then(r => r.json())
        .then(data => {
            if (data && data.full_description) {
                descTextarea.value = data.full_description;
            } else if (data && data.short_summary) {
                descTextarea.value = data.short_summary;
            }
        })
        .catch(err => {
            console.error('Gemini AI description error:', err);
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Auto-Generate Description with Gemini AI`;
        });
    });
}

// 4. Admin & Seller Project Management Control Dashboard Integration
function initGeminiAIProjectManagerDashboard() {
    const dashboardContainer = document.getElementById('admin-project-manager-widget') || document.getElementById('seller-project-manager-widget');
    if (!dashboardContainer) return;

    dashboardContainer.innerHTML = `
        <div class="card" style="border: 1px solid rgba(124, 58, 237, 0.3); background: linear-gradient(135deg, rgba(30, 27, 75, 0.04), rgba(124, 58, 237, 0.04));">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem;">
                <h3 style="margin: 0; font-size: 1.1rem; color: #4338ca; display: flex; align-items: center; gap: 0.5rem;">
                    <i class="fa-solid fa-sparkles" style="color: #7c3aed;"></i> Gemini AI Project & Store Manager
                </h3>
                <span class="badge" style="background: linear-gradient(135deg, #2563eb, #7c3aed); color: #fff; padding: 0.25rem 0.6rem;">Gemini AI 3.6 Flash</span>
            </div>
            <p style="font-size: 0.88rem; color: var(--text-secondary); margin-bottom: 1rem;">
                Ask Gemini AI for project management insights, inventory restock suggestions, or promotional strategy ideas.
            </p>
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
                <button class="gemini-ai-badge-btn" onclick="askDashboardGemini('How can I increase sales and conversions this week?')">🚀 Sales Strategy</button>
                <button class="gemini-ai-badge-btn" onclick="askDashboardGemini('Analyze stock levels and suggest inventory updates.')">📦 Stock Audit</button>
                <button class="gemini-ai-badge-btn" onclick="askDashboardGemini('Draft a customer promotion discount campaign.')">💡 Discount Promo</button>
            </div>
            <div id="dashboard-gemini-response" style="display: none; background: var(--bg-primary); padding: 1rem; border-radius: var(--radius-md); border: 1px solid var(--border-color); font-size: 0.9rem; line-height: 1.5; margin-bottom: 1rem;">
            </div>
            <div style="display: flex; gap: 0.5rem;">
                <input type="text" id="dashboard-gemini-input" class="form-control" placeholder="Ask Gemini AI Project Assistant..." style="flex: 1;" onkeypress="if(event.key==='Enter') submitDashboardGemini();">
                <button type="button" class="btn btn-primary" onclick="submitDashboardGemini()" style="background: linear-gradient(135deg, #2563eb, #7c3aed); border: none;">Ask AI</button>
            </div>
        </div>
    `;
}

function askDashboardGemini(promptText) {
    const input = document.getElementById('dashboard-gemini-input');
    if (input) {
        input.value = promptText;
        submitDashboardGemini();
    }
}

function submitDashboardGemini() {
    const input = document.getElementById('dashboard-gemini-input');
    const respBox = document.getElementById('dashboard-gemini-response');
    if (!input || !respBox) return;

    const query = input.value.trim();
    if (!query) return;

    respBox.style.display = 'block';
    respBox.innerHTML = `<i class="fa-solid fa-spinner fa-spin" style="color: #7c3aed;"></i> <strong>Gemini AI</strong> is analyzing store data...`;

    fetch('/api/ai/project-assistant', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
        },
        body: JSON.stringify({ message: query })
    })
    .then(r => r.json())
    .then(data => {
        if (data && data.reply) {
            respBox.innerHTML = `
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; color: #4338ca; font-weight: 700;">
                    <i class="fa-solid fa-robot"></i> Gemini AI Store Response:
                </div>
                <div style="background: var(--bg-secondary); padding: 0.85rem; border-radius: 8px; border-left: 3px solid #7c3aed;">
                    ${formatMarkdownToHTML(data.reply)}
                </div>
            `;
        }
    })
    .catch(err => {
        respBox.innerHTML = `<span style="color: var(--danger);">Gemini AI connection issue. Please check network.</span>`;
    });
}
