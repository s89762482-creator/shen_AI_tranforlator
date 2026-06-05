const API = {
    async request(endpoint, options = {}) {
        const url = `${CONFIG.API_BASE_URL}${endpoint}`;
        const config = { headers: {}, ...options };
        try {
            const response = await fetch(url, config);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
            return data;
        } catch (error) {
            console.error(`[API] 请求失败: ${endpoint}`, error);
            throw error;
        }
    },
    async get(endpoint) { return this.request(endpoint, { method: 'GET' }); },
    async post(endpoint, body = {}) {
        return this.request(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },
    async upload(endpoint, formData) {
        return this.request(endpoint, { method: 'POST', body: formData });
    },
    async delete(endpoint) { return this.request(endpoint, { method: 'DELETE' }); },

    async healthCheck() { return this.get(CONFIG.ENDPOINTS.HEALTH); },
    async transcribe(audioBlob) {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'audio.webm');
        return this.upload(CONFIG.ENDPOINTS.TRANSCRIBE, formData);
    },
    async translateStream(text, targetLang = 'zh', onToken, onDone, onError) {
        const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.TRANSLATE_STREAM}`;
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, target_lang: targetLang, engine: CONFIG.TRANSLATE_ENGINE }),
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            if (data.token) onToken(data.token);
                            else if (data.done) onDone();
                            else if (data.error) { if (onError) onError(data.error); }
                        } catch (e) {}
                    }
                }
            }
        } catch (error) { if (onError) onError(error.message); }
    },
    async getHistory() { return this.get(CONFIG.ENDPOINTS.HISTORY); },
    async clearHistory() { return this.delete(CONFIG.ENDPOINTS.HISTORY); },
};