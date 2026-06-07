const AudioCapture = {
    isRunning: false,
    audioSource: 'system',
    currentStream: null,
    mediaRecorder: null,
    audioContext: null,
    analyser: null,
    silenceTimer: null,
    lastSpeechTime: 0,
    _audioChunks: [],
    _audioProcessor: null,
    _audioContext2: null,
    _noiseFloor: null,

    onAudioChunk: null,
    onStatusChange: null,

    async start(source = 'system') {
        if (this.isRunning) return;
        this.audioSource = source;

        try {
            // 只能使用系统音频模式
            this.currentStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
            this.currentStream.getVideoTracks()[0].onended = () => this.stop();

            const audioTracks = this.currentStream.getAudioTracks();
            console.log('[Audio] 音频轨道数:', audioTracks.length);
            if (audioTracks.length === 0) throw new Error('没有音频轨道');

            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const sourceNode = this.audioContext.createMediaStreamSource(this.currentStream);
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            sourceNode.connect(this.analyser);

            let options = {};
            if (MediaRecorder.isTypeSupported('audio/webm'))
                options = { mimeType: 'audio/webm', audioBitsPerSecond: 64000 };

            this._audioChunks = [];

            try {
                this.mediaRecorder = new MediaRecorder(this.currentStream, options);
            } catch (e) {
                this.mediaRecorder = new MediaRecorder(this.currentStream);
            }

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) this._audioChunks.push(event.data);
            };

            this.mediaRecorder.onerror = (event) => {
                console.error('[Audio] MediaRecorder 错误:', event.error);
            };

            this.mediaRecorder.onstop = () => {
                if (this._audioChunks.length > 0) {
                    const mimeType = this.mediaRecorder.mimeType || 'audio/webm';
                    const blob = new Blob(this._audioChunks, { type: mimeType });
                    this._audioChunks = [];
                    if (this.onAudioChunk) this.onAudioChunk(blob);
                }
            };

            try {
                this.mediaRecorder.start(1000);
            } catch (e) {
                this._useAudioContextRecording();
                return;
            }

            this.isRunning = true;
            this.lastSpeechTime = Date.now();
            this._startVAD();
            if (this.onStatusChange) this.onStatusChange(true);

        } catch (error) {
            console.error('[Audio] 启动失败:', error);
            if (this.currentStream) {
                this.currentStream.getTracks().forEach(t => t.stop());
                this.currentStream = null;
            }
            throw error;
        }
    },

    _useAudioContextRecording() {
        const track = this.currentStream.getAudioTracks()[0];
        const sampleRate = track.getSettings().sampleRate || 48000;
        const ctx = new AudioContext({ sampleRate });
        const source = ctx.createMediaStreamSource(this.currentStream);
        const processor = ctx.createScriptProcessor(4096, 1, 1);
        source.connect(processor);
        processor.connect(ctx.destination);

        let pcmChunks = [];
        processor.onaudioprocess = (event) => {
            if (!this.isRunning) return;
            const inputData = event.inputBuffer.getChannelData(0);
            const pcm16 = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++)
                pcm16[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
            pcmChunks.push(pcm16.buffer);

            if (pcmChunks.length >= Math.ceil(sampleRate * 3 / 4096)) {
                const totalLength = pcmChunks.reduce((acc, c) => acc + c.byteLength, 0);
                const combined = new Uint8Array(totalLength);
                let offset = 0;
                for (const chunk of pcmChunks) {
                    combined.set(new Uint8Array(chunk), offset);
                    offset += chunk.byteLength;
                }
                const wav = this._pcmToWav(combined.buffer, sampleRate);
                const blob = new Blob([wav], { type: 'audio/wav' });
                pcmChunks = [];
                if (this.onAudioChunk) this.onAudioChunk(blob);
            }
        };

        this._audioProcessor = processor;
        this._audioContext2 = ctx;
        this.isRunning = true;
        this.lastSpeechTime = Date.now();
        if (this.onStatusChange) this.onStatusChange(true);
    },

    _pcmToWav(pcmBuffer, sampleRate) {
        const numChannels = 1, bitsPerSample = 16;
        const byteRate = sampleRate * numChannels * bitsPerSample / 8;
        const blockAlign = numChannels * bitsPerSample / 8;
        const dataSize = pcmBuffer.byteLength;
        const bufferSize = 44 + dataSize;
        const buffer = new ArrayBuffer(bufferSize);
        const view = new DataView(buffer);
        const ws = (o, s) => { for (let i=0;i<s.length;i++) view.setUint8(o+i,s.charCodeAt(i)); };
        ws(0, 'RIFF'); view.setUint32(4, bufferSize-8, true);
        ws(8, 'WAVE'); ws(12, 'fmt '); view.setUint32(16, 16, true);
        view.setUint16(20, 1, true); view.setUint16(22, numChannels, true);
        view.setUint32(24, sampleRate, true); view.setUint32(28, byteRate, true);
        view.setUint16(32, blockAlign, true); view.setUint16(34, bitsPerSample, true);
        ws(36, 'data'); view.setUint32(40, dataSize, true);
        new Uint8Array(buffer).set(new Uint8Array(pcmBuffer), 44);
        return buffer;
    },

    stop() {
        if (!this.isRunning) return;
        this.isRunning = false;
        if (this._audioProcessor) { this._audioProcessor.disconnect(); this._audioProcessor = null; }
        if (this._audioContext2) { this._audioContext2.close(); this._audioContext2 = null; }
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') this.mediaRecorder.stop();
        if (this.audioContext) { this.audioContext.close(); this.audioContext = null; }
        if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
        if (this.currentStream) { this.currentStream.getTracks().forEach(t => t.stop()); this.currentStream = null; }
        if (this.onStatusChange) this.onStatusChange(false);
    },

    _startVAD() {
        if (!this.analyser) return;
        const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
        let isSpeaking = false, silenceStart = 0, speakingFrames = 0, silenceFrames = 0;
        let speechStartTime = 0;
        let totalSpeechDuration = 0;

        const check = () => {
            if (!this.isRunning) return;
            this.analyser.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
            const avgVolume = sum / dataArray.length;
            const threshold = Math.max(15, this._noiseFloor ? this._noiseFloor * 1.5 : 15);

            // 动态调整静音超时时间（根据语音时长）
            const dynamicSilenceTimeout = this._calculateDynamicTimeout(totalSpeechDuration);

            if (avgVolume > threshold) {
                speakingFrames++; silenceFrames = 0;
                if (!isSpeaking && speakingFrames > 3) {
                    isSpeaking = true;
                    speechStartTime = Date.now();
                }
                if (isSpeaking) {
                    totalSpeechDuration = Date.now() - speechStartTime;
                }
                this.lastSpeechTime = Date.now();
            } else {
                silenceFrames++; speakingFrames = 0;
                if (!this._noiseFloor || avgVolume < this._noiseFloor)
                    this._noiseFloor = this._noiseFloor ? this._noiseFloor * 0.9 + avgVolume * 0.1 : avgVolume;
                if (isSpeaking && silenceFrames > 8) { 
                    isSpeaking = false; 
                    silenceStart = Date.now(); 
                }
            }

            // 智能断句逻辑
            if (!isSpeaking && silenceStart > 0 && Date.now() - silenceStart > dynamicSilenceTimeout && this._audioChunks.length > 0) {
                // 检查是否达到最小语音时长
                if (totalSpeechDuration >= (CONFIG.VAD.MIN_SPEECH_DURATION || 200)) {
                    silenceStart = 0;
                    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                        this.mediaRecorder.requestData();
                    }
                    totalSpeechDuration = 0;
                }
            }
            
            // 最大长度限制（防止单条音频过长）
            if (isSpeaking && this._audioChunks.length > 30) {
                if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                    this.mediaRecorder.requestData();
                }
                isSpeaking = false;
                totalSpeechDuration = 0;
            }
            
            requestAnimationFrame(check);
        };
        check();
    },

    _calculateDynamicTimeout(speechDuration) {
        const baseTimeout = CONFIG.VAD.SILENCE_TIMEOUT || 1500;
        
        if (speechDuration < 2000) {
            return Math.min(baseTimeout, 1200);
        } else if (speechDuration < 5000) {
            return baseTimeout;
        } else {
            return Math.min(baseTimeout * 1.5, 3000);
        }
    },
};
