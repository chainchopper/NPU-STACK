/**
 * API client for NPU-STACK backend.
 * Wraps fetch calls and provides WebSocket connection management.
 */

const DEV_FRONTEND_PORTS = new Set(['5173', '5174']);
const DEFAULT_DEV_BACKEND_PORT = (import.meta.env?.VITE_BACKEND_PORT || '8010').trim();
const CONFIGURED_DEV_BACKEND_ORIGIN = (import.meta.env?.VITE_BACKEND_ORIGIN || '').trim().replace(/\/$/, '');

function resolveDevBackendOrigin(currentUrl = null) {
    if (CONFIGURED_DEV_BACKEND_ORIGIN) return CONFIGURED_DEV_BACKEND_ORIGIN;

    const fallbackUrl = currentUrl || (typeof window !== 'undefined' ? window.location.href : '');
    if (!fallbackUrl) return '';

    try {
        const url = new URL(fallbackUrl, typeof window !== 'undefined' ? window.location.origin : undefined);
        if (!DEV_FRONTEND_PORTS.has(url.port)) return '';
        url.port = DEFAULT_DEV_BACKEND_PORT;
        return url.origin;
    } catch {
        return '';
    }
}

function resolveRuntimeBase(basePath) {
    const devOrigin = resolveDevBackendOrigin();
    return devOrigin ? `${devOrigin}${basePath}` : basePath;
}

export const API_BASE = resolveRuntimeBase('/api');
export const OPENAI_BASE = resolveRuntimeBase('/v1');

function normalizePath(path = '') {
    if (!path) return '';
    return path.startsWith('/') ? path : `/${path}`;
}

export function apiUrl(path = '') {
    return `${API_BASE}${normalizePath(path)}`;
}

export function openAIUrl(path = '') {
    return `${OPENAI_BASE}${normalizePath(path)}`;
}

export function absoluteUrl(path = '') {
    const normalized = path || '/';
    if (typeof window === 'undefined') return normalized;

    const backendOrigin = resolveDevBackendOrigin();
    const useBackendOrigin = backendOrigin && /^\/(api|v1|ws)(\/|$)/.test(normalized);
    return new URL(normalized, useBackendOrigin ? backendOrigin : window.location.origin).toString();
}

export function inferBackendOrigin(currentUrl = null) {
    const devOrigin = resolveDevBackendOrigin(currentUrl);
    if (devOrigin) return devOrigin;

    const fallbackUrl = currentUrl || (typeof window !== 'undefined' ? window.location.href : '');
    if (!fallbackUrl) return '';

    try {
        const url = new URL(fallbackUrl, typeof window !== 'undefined' ? window.location.origin : undefined);
        return url.origin;
    } catch {
        return typeof window !== 'undefined' ? window.location.origin : '';
    }
}

export function websocketUrl(path = '') {
    const backendOrigin = resolveDevBackendOrigin() || window.location.origin;
    const url = new URL(normalizePath(path), backendOrigin);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.toString();
}

function buildApiError(message, details = {}) {
    const error = new Error(message);
    Object.assign(error, details);
    return error;
}

/**
 * Safe JSON fetch — checks response.ok before parsing.
 * Falls back to empty array/object on non-OK or parse failure.
 */
export async function safeFetch(url, options = {}, fallback = null) {
    try {
        const res = await fetch(url, options);
        if (!res.ok) {
            console.warn(`safeFetch ${res.status} for ${url}`);
            return fallback;
        }
        const text = await res.text();
        if (!text || !text.trim()) return fallback;
        return JSON.parse(text);
    } catch (e) {
        console.warn(`safeFetch failed for ${url}:`, e.message);
        return fallback;
    }
}

export function diagnoseBackendError(error, feature = 'This feature') {
    const backendOrigin = inferBackendOrigin();
    const target = backendOrigin || (typeof window !== 'undefined' ? window.location.origin : 'the backend');

    if (!error) {
        return `${feature} could not reach the NPU-STACK backend.`;
    }

    if (error.kind === 'network') {
        return `${feature} cannot reach the NPU-STACK backend at ${target}. Start the backend or point the frontend at the correct port.`;
    }

    if (error.status === 404) {
        return `${feature} reached ${target}, but that service does not look like the NPU-STACK backend. The expected API route returned 404 Not Found.`;
    }

    if (error.status >= 500) {
        return `${feature} reached the backend at ${target}, but it returned a server error (${error.status}).`;
    }

    return error.message || `${feature} failed while talking to the backend at ${target}.`;
}

function titleCaseSlug(value = '') {
    return value
        .replace(/[-_]+/g, ' ')
        .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatFlmModelName(tag = '') {
    if (!tag) return 'Unknown Model';
    const [base, variant] = tag.split(':');
    const baseName = titleCaseSlug(base);
    return variant ? `${baseName} ${variant}` : baseName;
}

async function request(path, options = {}) {
    const url = apiUrl(path);
    let res;
    try {
        res = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
        });
    } catch (error) {
        throw buildApiError(`Unable to reach ${url}`, {
            url,
            kind: 'network',
            status: 0,
            cause: error,
        });
    }

    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }));
        throw buildApiError(error.detail || `Request failed: ${res.status}`, {
            url,
            status: res.status,
            kind: res.status === 404 ? 'not-found' : 'http',
            detail: error.detail || null,
        });
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
    const ws = new WebSocket(websocketUrl(`/ws/training/${jobId}`));

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

// ─── FastFlowLM ───────────────────────────────────────
export async function getFLMStatus() {
    const status = await request('/flm/status');
    return {
        ...status,
        version: status.version || 'N/A',
        latest_version: status.latest_version || null,
        update_available: Boolean(status.update_available),
        npu_ready: Boolean(status.server_running || status.installed),
        server: {
            running: Boolean(status.server_running),
            managed: Boolean(status.server_managed),
            model: status.active_model || status.server_models?.[0] || null,
            models: status.server_models || [],
        },
    };
}

export async function listFLMModels() {
    const data = await request('/flm/models');

    const normalizeModel = (model = {}) => ({
        ...model,
        name: model.name || formatFlmModelName(model.tag),
        size: model.size || model.params || '—',
        context: model.context || model.ctx || 'n/a',
    });

    return {
        ...data,
        local: (data.local || []).map(normalizeModel),
        catalog: (data.catalog || []).map(normalizeModel),
    };
}

export async function pullFLMModel(tag, onProgress, force = false) {
    const res = await fetch(`${API_BASE}/flm/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag, force }),
    });

    if (!res.ok) throw new Error('Pull failed');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const rawLine of lines) {
            const line = rawLine.trim();
            if (line) {
                const payload = line.startsWith('data:') ? line.slice(5).trim() : line;
                if (!payload || payload === '[DONE]') {
                    continue;
                }

                try {
                    const data = JSON.parse(payload);
                    onProgress({
                        ...data,
                        status: data.status === 'complete' ? 'completed' : data.status,
                    });
                } catch (e) {
                    console.error('Failed to parse progress:', payload);
                }
            }
        }
    }
}

export async function checkFLMModel(tag) {
    return request('/flm/check', {
        method: 'POST',
        body: JSON.stringify({ tag }),
    });
}

export async function serveFLMModel(model, port = 52625) {
    return request('/flm/serve', {
        method: 'POST',
        body: JSON.stringify({ model, port }),
    });
}

export async function stopFLMServer() {
    return request('/flm/stop', { method: 'POST' });
}

export async function chatFLM(messages, model, temperature = 0.7, maxTokens = 1024, onDelta) {
    const res = await fetch(`${API_BASE}/flm/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            messages,
            model,
            temperature,
            max_tokens: maxTokens,
            stream: true
        }),
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Chat failed' }));
        throw new Error(err.detail);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunks = decoder.decode(value).split('\n');
        for (const chunk of chunks) {
            if (chunk.startsWith('data: ')) {
                const dataStr = chunk.slice(6).trim();
                if (dataStr === '[DONE]') break;
                try {
                    const data = JSON.parse(dataStr);
                    const content = data.choices[0]?.delta?.content || '';
                    if (content) onDelta(content);
                } catch (e) {
                    // Ignore malformed JSON in stream
                }
            }
        }
    }
}

// ─── Edge Fleet (Device Management) ──────────────────
export async function scanDevices(methods = {}) {
    const params = new URLSearchParams();
    Object.entries(methods).forEach(([k, v]) => {
        if (v == null) return;
        if (typeof v === 'string' && !v.trim()) return;
        params.set(k, String(v));
    });
    return request(`/devices/scan?${params}`);
}

export async function listDevices(includeLowConfidence = false) {
    const params = includeLowConfidence ? '?include_low_confidence=true' : '';
    return request(`/devices${params}`);
}

export async function fleetScan() {
    /** Unified fleet scanner: serial ports + libusb Rockchip + MQTT devices. */
    return request('/esp/fleet/scan');
}

export async function listDeviceProfiles(deviceId) {
    const params = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : '';
    return request(`/devices/profiles${params}`);
}

export async function listPreparedBundles(deviceId) {
    const params = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : '';
    return request(`/devices/prepared${params}`);
}

export function downloadPreparedBundleUrl(bundleId) {
    return apiUrl(`/devices/prepared/${bundleId}/download`);
}

export async function updateDevice(deviceId, data) {
    return request(`/devices/${deviceId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

export async function pairDevice(deviceId) {
    return request(`/devices/${deviceId}/pair`, { method: 'POST' });
}

export async function unpairDevice(deviceId) {
    return request(`/devices/${deviceId}/unpair`, { method: 'POST' });
}

export async function prepareDevice(deviceId, data = {}) {
    return request(`/devices/${deviceId}/prepare`, {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export async function installPreparedBundle(deviceId, bundleId) {
    return request(`/devices/${deviceId}/install`, {
        method: 'POST',
        body: JSON.stringify({ bundle_id: bundleId }),
    });
}

export async function getDeviceTelemetry(deviceId, { limit = 50, refresh = false } = {}) {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (refresh) params.set('refresh', 'true');
    return request(`/devices/${deviceId}/telemetry?${params}`);
}

export async function getDeviceTelemetryHistory(deviceId, limit = 100) {
    return request(`/devices/${deviceId}/telemetry/history?limit=${encodeURIComponent(limit)}`);
}

export async function executeDeviceCommand(deviceId, command, { timeoutSeconds = 30, dryRun = false } = {}) {
    return request(`/devices/${deviceId}/exec`, {
        method: 'POST',
        body: JSON.stringify({ command, timeout_seconds: timeoutSeconds, dry_run: dryRun }),
    });
}

export async function rebootDevice(deviceId, { dryRun = false } = {}) {
    return request(`/devices/${deviceId}/reboot`, {
        method: 'POST',
        body: JSON.stringify({ dry_run: dryRun }),
    });
}

export async function removeDevice(deviceId) {
    return request(`/devices/${deviceId}`, { method: 'DELETE' });
}

export async function espDetect(port) {
    return request('/devices/esp/detect', {
        method: 'POST',
        body: JSON.stringify({ port }),
    });
}

export async function detectDeviceChip(deviceId) {
    return request(`/devices/${deviceId}/detect-chip`, {
        method: 'POST',
    });
}

export async function espBackup(port, flashSizeMb = 8) {
    return request('/devices/esp/backup', {
        method: 'POST',
        body: JSON.stringify({ port, flash_size_mb: flashSizeMb }),
    });
}

export async function espFlash(port, firmwarePath) {
    return request('/devices/esp/flash', {
        method: 'POST',
        body: JSON.stringify({ port, firmware_path: firmwarePath }),
    });
}

export async function rp2040Detect() {
    return request('/devices/rp2040/detect');
}

export async function listBackups() {
    return request('/devices/backups');
}

// ─── Orchestration (Nirvana + AutoResearch) ───────────
export async function getOrchestrationState() {
    return request('/orchestration/state');
}

export async function getNirvanaRuntimeConfig() {
    return request('/orchestration/nirvana-config');
}

export async function getNirvanaIdentity() {
    return request('/orchestration/nirvana');
}

export async function updateNirvanaIdentity(payload) {
    return request('/orchestration/nirvana', {
        method: 'PUT',
        body: JSON.stringify(payload),
    });
}

export async function getOrchestrationCapabilities() {
    return request('/orchestration/capabilities');
}

export async function updateNirvanaRuntimeConfig(payload) {
    return request('/orchestration/nirvana-config', {
        method: 'PUT',
        body: JSON.stringify(payload),
    });
}

export async function listAutoResearchProfiles() {
    return request('/orchestration/autoresearch/profiles');
}

export async function createAutoResearchProfile(payload) {
    return request('/orchestration/autoresearch/profiles', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function deleteAutoResearchProfile(profileId) {
    return request(`/orchestration/autoresearch/profiles/${encodeURIComponent(profileId)}`, {
        method: 'DELETE',
    });
}

export async function listAutoResearchRuns(limit = 25) {
    return request(`/orchestration/autoresearch/runs?limit=${limit}`);
}

export async function createAutoResearchRun(payload) {
    return request('/orchestration/autoresearch/runs', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function updateAutoResearchRun(runId, payload) {
    return request(`/orchestration/autoresearch/runs/${encodeURIComponent(runId)}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
    });
}

export async function discoverMcpAssets() {
    return request('/orchestration/mcp/discover');
}

export async function autoAddMcpServers(payload = {}) {
    return request('/orchestration/mcp/auto-add', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

// ─── Universal Agent Runtimes ─────────────────────────
export async function listAgentRuntimes({ probe = false } = {}) {
    const query = probe ? '?probe=true' : '';
    return request(`/agent-runtimes${query}`);
}

export async function discoverAgentRuntimes({ probe = true } = {}) {
    return request('/agent-runtimes/discover', {
        method: 'POST',
        body: JSON.stringify({ probe }),
    });
}

export async function getAgentRuntime(runtimeId, { probe = false } = {}) {
    const query = probe ? '?probe=true' : '';
    return request(`/agent-runtimes/${encodeURIComponent(runtimeId)}${query}`);
}

export async function probeAgentRuntime(runtimeId) {
    return request(`/agent-runtimes/${encodeURIComponent(runtimeId)}/probe`, {
        method: 'POST',
    });
}

export async function getAgentRuntimeCapabilities(runtimeId) {
    return request(`/agent-runtimes/${encodeURIComponent(runtimeId)}/capabilities`);
}

export async function getAgentRuntimeAvailability(runtimeId, capability) {
    return request(`/agent-runtimes/${encodeURIComponent(runtimeId)}/availability/${encodeURIComponent(capability)}`);
}

export async function registerAgentRuntime(payload) {
    return request('/agent-runtimes/register', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function updateAgentRuntime(runtimeId, payload) {
    return request(`/agent-runtimes/${encodeURIComponent(runtimeId)}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
    });
}

export async function deleteAgentRuntime(runtimeId) {
    return request(`/agent-runtimes/${encodeURIComponent(runtimeId)}`, {
        method: 'DELETE',
    });
}

export async function getCurrentAgentRuntimeSelection() {
    return request('/agent-runtimes/selection/current');
}

export async function selectAgentRuntime(runtimeId, allowUnready = true) {
    return request('/agent-runtimes/selection', {
        method: 'PUT',
        body: JSON.stringify({ runtime_id: runtimeId, allow_unready: allowUnready }),
    });
}

export async function listAgentProfiles() {
    return request('/orchestration/agent-profiles');
}

export async function createAgentProfile(payload) {
    return request('/orchestration/agent-profiles', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function updateAgentProfile(profileId, payload) {
    return request(`/orchestration/agent-profiles/${encodeURIComponent(profileId)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    });
}

export async function deleteAgentProfile(profileId) {
    return request(`/orchestration/agent-profiles/${encodeURIComponent(profileId)}`, {
        method: 'DELETE',
    });
}

export async function listAgentSessions(profileId = '') {
    const query = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : '';
    return request(`/orchestration/agent-sessions${query}`);
}

export async function createAgentSession(payload) {
    return request('/orchestration/agent-sessions', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function updateAgentSession(sessionId, payload) {
    return request(`/orchestration/agent-sessions/${encodeURIComponent(sessionId)}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
    });
}

export async function deleteAgentSession(sessionId) {
    return request(`/orchestration/agent-sessions/${encodeURIComponent(sessionId)}`, {
        method: 'DELETE',
    });
}

export async function getAgentStatus() {
    return request('/agent/status');
}

export async function getAgentRuntimeDetails() {
    return request('/agent/runtime');
}

export async function getNirvanaStatus() {
    return getAgentStatus();
}

export async function getNirvanaRuntimeDetails() {
    return getAgentRuntimeDetails();
}

export async function initializeAgentDownload() {
    return request('/agent/init', {
        method: 'POST',
    });
}

export async function prepareNirvanaRuntime() {
    return initializeAgentDownload();
}

export async function startLocalAgent() {
    return request('/agent/start', {
        method: 'POST',
    });
}

export async function launchNirvana() {
    return startLocalAgent();
}

export async function chatWithAgent(payload) {
    return request('/agent/chat', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function chatWithNirvana(payload) {
    return chatWithAgent(payload);
}

// ─── Nirvana Remote Audio ────────────────────────────
export async function listAudioEndpoints({ online, endpointType } = {}) {
    const params = new URLSearchParams();
    if (online != null) params.set('online', String(online));
    if (endpointType) params.set('endpoint_type', endpointType);
    const query = params.toString();
    return request(`/nirvana/audio/endpoints${query ? `?${query}` : ''}`);
}

export async function listAudioGroups() {
    return request('/nirvana/audio/groups');
}

export async function listManagedAudioProfiles() {
    return request('/nirvana/audio/home-assistant/profiles');
}

export async function createManagedAudioProfile(payload) {
    return request('/nirvana/audio/home-assistant/profiles', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function updateManagedAudioProfile(profileId, payload) {
    return request(`/nirvana/audio/home-assistant/profiles/${encodeURIComponent(profileId)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    });
}

export async function deleteManagedAudioProfile(profileId) {
    return request(`/nirvana/audio/home-assistant/profiles/${encodeURIComponent(profileId)}`, { method: 'DELETE' });
}

export async function listManagedAudioEntities(profileId) {
    return request(`/nirvana/audio/home-assistant/profiles/${encodeURIComponent(profileId)}/entities`);
}

export async function testManagedAudioProfile(profileId, payload) {
    return request(`/nirvana/audio/home-assistant/profiles/${encodeURIComponent(profileId)}/test`, {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function createAudioPairingChallenge(payload = {}) {
    return request('/nirvana/audio/pairing/challenge', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function claimAudioPairing(payload) {
    return request('/nirvana/audio/pairing/claim', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function revokeAudioPairing(endpointId) {
    return request(`/nirvana/audio/pairing/${encodeURIComponent(endpointId)}/revoke`, { method: 'POST' });
}

export async function createAudioGroup(payload) {
    return request('/nirvana/audio/groups', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function updateAudioGroup(groupId, payload) {
    return request(`/nirvana/audio/groups/${encodeURIComponent(groupId)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    });
}

export async function deleteAudioGroup(groupId) {
    return request(`/nirvana/audio/groups/${encodeURIComponent(groupId)}`, { method: 'DELETE' });
}

export async function routeAudio(payload) {
    return request('/nirvana/audio/speak', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function stopAudio(payload) {
    return request('/nirvana/audio/stop', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export function audioWebsocketUrl() {
    return websocketUrl('/api/nirvana/audio/ws');
}

// ─── Docs Index (Unified Compatibility Docs) ─────────
export async function getDocsIndexStatus() {
    return request('/docs-index/status');
}

export async function ensureDocsIndex() {
    return request('/docs-index/ensure', {
        method: 'POST',
    });
}

export async function rebuildDocsIndex(payload = { force: true, include_external: true }) {
    return request('/docs-index/rebuild', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
}

export async function searchDocsIndex(query, topK = 6, sourceType = null) {
    return request('/docs-index/search', {
        method: 'POST',
        body: JSON.stringify({
            query,
            top_k: topK,
            source_type: sourceType,
        }),
    });
}

export async function getGitbookRegistry() {
    return request('/docs-index/gitbook/registry');
}

export async function listGitbookDocs(projectId = null) {
    const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
    return request(`/docs-index/gitbook/docs${params}`);
}

export async function readGitbookDoc(path, projectId = null) {
    return request('/docs-index/gitbook/read', {
        method: 'POST',
        body: JSON.stringify({ path, project_id: projectId }),
    });
}

export async function syncExternalDocsToGitbook(projectId = null) {
    return request('/docs-index/gitbook/sync-external', {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId }),
    });
}

export async function syncProjectDocsToGitbook(projectId = null) {
    return request('/docs-index/gitbook/sync-project', {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId }),
    });
}

export async function flashFirmwareWorkflow(deviceId, { profileId = 'circuitpython', port = '', wifiSsid = '', wifiPassword = '', backupFirst = true } = {}) {
    return request(`/fleet/command/device/${deviceId}/firmware/flash`, {
        method: 'POST',
        body: JSON.stringify({ profile_id: profileId, port, wifi_ssid: wifiSsid, wifi_password: wifiPassword, backup_first: backupFirst }),
    });
}

export async function detectDeviceFirmware(deviceId, port = '') {
    return request(`/fleet/command/device/${deviceId}/firmware/detect`, {
        method: 'POST',
        body: JSON.stringify({ port }),
    });
}

export async function backupDeviceFirmware(deviceId, port = '', flashSizeMb = 8) {
    return request(`/fleet/command/device/${deviceId}/firmware/backup`, {
        method: 'POST',
        body: JSON.stringify({ port, flash_size_mb: flashSizeMb }),
    });
}
