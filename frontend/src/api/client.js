/**
 * API client for NPU-STACK backend.
 * Wraps fetch calls and provides WebSocket connection management.
 */

export const API_BASE = '/api';

async function request(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const res = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    });

    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(error.detail || `Request failed: ${res.status}`);
    }

    return res.json();
}

// ─── Models ────────────────────────────────────────────
export async function uploadModel(file, name, description) {
    const form = new FormData();
    form.append('file', file);
    if (name) form.append('name', name);
    if (description) form.append('description', description);

    const res = await fetch(`${API_BASE}/models/upload`, {
        method: 'POST',
        body: form,
    });
    if (!res.ok) throw new Error('Upload failed');
    return res.json();
}

export async function listModels(framework) {
    const params = framework ? `?framework=${framework}` : '';
    return request(`/models${params}`);
}

export async function getModel(id) {
    return request(`/models/${id}`);
}

export async function deleteModel(id) {
    return request(`/models/${id}`, { method: 'DELETE' });
}

// ─── Training ──────────────────────────────────────────
export async function startTraining(config) {
    return request('/training/start', {
        method: 'POST',
        body: JSON.stringify(config),
    });
}

export async function listJobs(status) {
    const params = status ? `?status=${status}` : '';
    return request(`/training/jobs${params}`);
}

export async function getJob(id) {
    return request(`/training/jobs/${id}`);
}

export async function stopJob(id) {
    return request(`/training/jobs/${id}/stop`, { method: 'POST' });
}

export function connectTrainingWS(jobId, onMessage) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/training/${jobId}`);

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            onMessage(data);
        } catch (e) {
            console.error('WS parse error:', e);
        }
    };

    ws.onerror = (err) => console.error('WS error:', err);

    return ws;
}

// ─── Conversion ────────────────────────────────────────
export async function convertModel(modelId, targetFormat, compressFp16 = true, outputName = null) {
    return request('/convert', {
        method: 'POST',
        body: JSON.stringify({
            model_id: modelId,
            target_format: targetFormat,
            compress_fp16: compressFp16,
            output_name: outputName,
        }),
    });
}

export async function quantizeModel(modelId, method, weightType = 'int8', calibrationSamples = 100) {
    return request('/convert/quantize', {
        method: 'POST',
        body: JSON.stringify({
            model_id: modelId,
            method,
            weight_type: weightType,
            calibration_samples: calibrationSamples,
        }),
    });
}

export async function validateModel(modelId) {
    return request(`/convert/validate/${modelId}`);
}

// ─── Benchmark ─────────────────────────────────────────
export async function runBenchmark(config) {
    return request('/benchmark/run', {
        method: 'POST',
        body: JSON.stringify(config),
    });
}

export async function listBenchmarks(modelId) {
    const params = modelId ? `?model_id=${modelId}` : '';
    return request(`/benchmark/results${params}`);
}

export async function compareBenchmarks(ids) {
    return request(`/benchmark/compare?ids=${ids.join(',')}`);
}

export async function getSystemInfo() {
    return request('/benchmark/system-info');
}

// ─── Inference (Playground) ────────────────────────────
export async function classifyImage(modelId, imageFile, topK = 5) {
    const fd = new FormData();
    fd.append('model_id', modelId);
    fd.append('image', imageFile);
    fd.append('top_k', topK);
    const res = await fetch(`${API_BASE}/inference/classify`, { method: 'POST', body: fd });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Classify failed'); }
    return res.json();
}

export async function detectObjects(modelId, imageFile, threshold = 0.5) {
    const fd = new FormData();
    fd.append('model_id', modelId);
    fd.append('image', imageFile);
    fd.append('confidence_threshold', threshold);
    const res = await fetch(`${API_BASE}/inference/detect`, { method: 'POST', body: fd });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Detect failed'); }
    return res.json();
}

export async function generateText(modelId, prompt, maxTokens = 128, temperature = 0.7) {
    const fd = new FormData();
    fd.append('model_id', modelId);
    fd.append('prompt', prompt);
    fd.append('max_tokens', maxTokens);
    fd.append('temperature', temperature);
    const res = await fetch(`${API_BASE}/inference/generate-text`, { method: 'POST', body: fd });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Generate failed'); }
    return res.json();
}

export async function getInferenceCapabilities() {
    return request('/inference/capabilities');
}

// ─── HuggingFace ───────────────────────────────────────
export async function searchHuggingFace(query, task, limit = 20) {
    const params = new URLSearchParams({ q: query, limit });
    if (task) params.set('task', task);
    return request(`/huggingface/search?${params}`);
}

export async function getHuggingFaceModel(repoId) {
    return request(`/huggingface/model/${encodeURIComponent(repoId)}`);
}

export async function downloadHuggingFaceModel(repoId, filename) {
    const fd = new FormData();
    fd.append('repo_id', repoId);
    if (filename) fd.append('filename', filename);
    const res = await fetch(`${API_BASE}/huggingface/download`, { method: 'POST', body: fd });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Download failed'); }
    return res.json();
}

// ─── Datasets ──────────────────────────────────────────
export async function listDatasets() {
    return request('/datasets');
}

export async function uploadDataset(file, name) {
    const fd = new FormData();
    fd.append('file', file);
    if (name) fd.append('name', name);
    const res = await fetch(`${API_BASE}/datasets/upload`, { method: 'POST', body: fd });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Upload failed'); }
    return res.json();
}

export async function scanDatasets() {
    return request('/datasets/scan', { method: 'POST' });
}

export async function deleteDataset(name) {
    return request(`/datasets/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

// ─── System ────────────────────────────────────────────
export async function healthCheck() {
    return request('/health');
}

export async function getStatus() {
    return request('/status');
}
