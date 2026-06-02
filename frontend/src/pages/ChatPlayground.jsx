import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send, Loader2, Trash2, Settings, Copy, AlertCircle, Play, Upload,
  Image, MessageSquare, Sparkles, Crosshair, Volume2, Video, Mic,
  ChevronDown, ChevronUp, Zap, Bot, RefreshCw, X, CheckCircle,
  BarChart2, Clock, Hash, Cpu, FlaskConical, BookOpen, Save, Download
} from 'lucide-react';
import {
  API_BASE,
  getSystemInfo,
  getFLMStatus,
  listFLMModels,
  serveFLMModel,
  stopFLMServer,
  checkFLMModel,
  chatFLM,
} from '../api/client';

// ─── Nirvana slash commands ───────────────────────────────────────────────────
const SLASH_COMMANDS = [
  { cmd: '/help',    usage: '/help',             desc: 'Show available commands',                    category: 'meta' },
  { cmd: '/clear',   usage: '/clear',            desc: 'Clear conversation history',                 category: 'meta' },
  { cmd: '/reset',   usage: '/reset',            desc: 'Start a new session thread',                 category: 'meta' },
  { cmd: '/export',  usage: '/export',           desc: 'Export conversation to JSON',                category: 'meta' },
  { cmd: '/status',  usage: '/status',           desc: 'Show Nirvana runtime status',                 category: 'info' },
  { cmd: '/tools',   usage: '/tools',            desc: 'List available tools and MCP servers',       category: 'info' },
  { cmd: '/model',   usage: '/model',            desc: 'Show active model info',                     category: 'info' },
  { cmd: '/config',  usage: '/config',           desc: 'Show Nirvana runtime config and config files', category: 'info' },
  { cmd: '/mcp',     usage: '/mcp',              desc: 'List connected MCP servers',                 category: 'info' },
  { cmd: '/context', usage: '/context <name>',   desc: 'Switch context (general/training/fleet/models)', category: 'session' },
  { cmd: '/history', usage: '/history',          desc: 'Show session thread info',                   category: 'session' },
];

// ─── Unsloth-sourced inference presets ───────────────────────────────────────
const CHAT_TEMPLATES = [
  { id: 'auto',     label: 'Auto-Detect',  description: 'Let the model pick its format' },
  { id: 'alpaca',   label: 'Alpaca',       description: 'Instruction / Response pairs' },
  { id: 'chatml',   label: 'ChatML',       description: '<|im_start|> / <|im_end|> format' },
  { id: 'sharegpt', label: 'ShareGPT',     description: 'Multi-turn conversation format' },
  { id: 'llama3',   label: 'Llama 3',      description: '<|begin_of_text|> token format' },
  { id: 'mistral',  label: 'Mistral',      description: '[INST] / [/INST] format' },
  { id: 'phi3',     label: 'Phi-3',        description: '<|user|> / <|assistant|> format' },
  { id: 'gemma',    label: 'Gemma',        description: '<start_of_turn> format' },
  { id: 'qwen2',    label: 'Qwen 2',       description: '<|im_start|> with Qwen tokenizer' },
  { id: 'raw',      label: 'Raw',          description: 'No template, plain text generation' },
];

const SYSTEM_PROMPTS = {
  auto:     'You are a helpful AI assistant.',
  alpaca:   'Below is an instruction that describes a task. Write a response that appropriately completes the request.',
  chatml:   'You are a helpful AI assistant.',
  sharegpt: 'You are a helpful AI assistant.',
  llama3:   'You are a helpful AI assistant. Always be truthful, accurate, and safe.',
  mistral:  'You are a helpful AI assistant.',
  phi3:     'You are a helpful AI assistant. Respond clearly and concisely.',
  gemma:    'You are a helpful AI assistant.',
  qwen2:    'You are a helpful AI assistant.',
  raw:      '',
};

const BUILTIN_PRESETS = [
  {
    name: 'Default',
    params: { temperature: 0.7, topP: 0.95, topK: 50, minP: 0.0, repetitionPenalty: 1.0, maxTokens: 512 }
  },
  {
    name: 'Creative',
    params: { temperature: 1.1, topP: 0.98, topK: 80, minP: 0.0, repetitionPenalty: 1.05, maxTokens: 1024 }
  },
  {
    name: 'Precise',
    params: { temperature: 0.2, topP: 0.9,  topK: 20, minP: 0.0, repetitionPenalty: 1.1, maxTokens: 512 }
  },
  {
    name: 'Code',
    params: { temperature: 0.1, topP: 0.95, topK: 40, minP: 0.0, repetitionPenalty: 1.0, maxTokens: 2048 }
  },
  {
    name: 'Storytelling',
    params: { temperature: 0.9, topP: 0.98, topK: 100, minP: 0.0, repetitionPenalty: 1.08, maxTokens: 2048 }
  },
];

// Playground tabs (from original Playground.jsx)
const PLAYGROUND_TABS = [
  { id: 'text',     label: 'Text Gen',   icon: MessageSquare },
  { id: 'classify', label: 'Classify',   icon: Image },
  { id: 'detect',   label: 'Detect',     icon: Crosshair },
  { id: 'imagegen', label: 'Image Gen',  icon: Sparkles },
  { id: 'audio',    label: 'Audio',      icon: Volume2 },
  { id: 'video',    label: 'Video',      icon: Video },
];

function SliderControl({ label, value, onChange, min, max, step, decimals = 2, description }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <label style={{ fontSize: 12, color: '#a0aec0', fontWeight: 600 }}>{label}</label>
        <span style={{
          fontSize: 12, fontFamily: 'monospace', background: '#2d3748',
          padding: '1px 6px', borderRadius: 4, color: '#90cdf4'
        }}>{Number(value).toFixed(decimals)}</span>
      </div>
      {description && <div style={{ fontSize: 10, color: '#718096', marginBottom: 4 }}>{description}</div>}
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: '#667eea', cursor: 'pointer' }}
      />
    </div>
  );
}

function CollapsibleSection({ title, icon: Icon, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginBottom: 8, borderRadius: 8, overflow: 'hidden', border: '1px solid #2d3748' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 12px', background: '#1a2035', border: 'none', cursor: 'pointer',
          color: '#e2e8f0', fontSize: 12, fontWeight: 700
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {Icon && <Icon size={14} color="#667eea" />} {title}
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <div style={{ padding: '10px 12px', background: '#141927' }}>
          {children}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function ChatPlayground({
  defaultView = 'chat',
  defaultMode = 'agent',
  defaultContext = 'general',
}) {
  // Mode: 'agent' uses /api/agent/chat, 'direct' uses /api/inference/generate-text
  const [mode, setMode] = useState(defaultMode);
  const [activeView, setActiveView] = useState(defaultView); // 'chat' | 'playground'

  // Agent state
  const [agentStatus, setAgentStatus] = useState(null); // null | {is_downloaded, is_running, ...}
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState(null);

  // Models (for direct mode)
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [systemInfo, setSystemInfo] = useState(null);
  const [deviceTarget, setDeviceTarget] = useState('auto'); // auto | cpu | gpu | npu
  const [runtimeTarget, setRuntimeTarget] = useState('auto'); // auto | native | fastflowlm
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [runtimeNotice, setRuntimeNotice] = useState('');
  const [flmStatus, setFlmStatus] = useState(null);
  const [flmModels, setFlmModels] = useState([]);
  const [selectedFlmModel, setSelectedFlmModel] = useState('');
  const [modelReferenceInput, setModelReferenceInput] = useState('');
  const [selectedContext, setSelectedContext] = useState(defaultContext);
  const [staffPicks, setStaffPicks] = useState([]);
  const [staffPicksOpen, setStaffPicksOpen] = useState(false);
  const [downloadNotice, setDownloadNotice] = useState('');
  const [downloadingPickId, setDownloadingPickId] = useState('');

  // Chat state
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [cmdPalette, setCmdPalette] = useState({ open: false, filter: '', selectedIdx: 0 });
  const [isLoading, setIsLoading] = useState(false);
  const [chatError, setChatError] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [lastMetrics, setLastMetrics] = useState(null); // {latency_ms, tokens, tps}

  // Inference params
  const [temperature, setTemperature] = useState(0.7);
  const [topP, setTopP] = useState(0.95);
  const [topK, setTopK] = useState(50);
  const [minP, setMinP] = useState(0.0);
  const [repetitionPenalty, setRepetitionPenalty] = useState(1.0);
  const [maxTokens, setMaxTokens] = useState(512);
  const [selectedPreset, setSelectedPreset] = useState('Default');

  // Template
  const [chatTemplate, setChatTemplate] = useState('auto');
  const [systemPrompt, setSystemPrompt] = useState(SYSTEM_PROMPTS.auto);
  const [customSystemPrompt, setCustomSystemPrompt] = useState(false);

  // Playground state
  const [playTab, setPlayTab] = useState('text');
  const [playPrompt, setPlayPrompt] = useState('');
  const [playResult, setPlayResult] = useState(null);
  const [playError, setPlayError] = useState(null);
  const [playLoading, setPlayLoading] = useState(false);
  const [playPreview, setPlayPreview] = useState(null);
  const fileRef = useRef(null);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const threadId = useRef(`thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);

  // ── Effects ──────────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (activeView === 'chat') inputRef.current?.focus();
  }, [activeView]);

  useEffect(() => {
    const loadRuntimeCompatibility = async () => {
      const [hw, flm, flmCatalog] = await Promise.all([
        getSystemInfo().catch(() => null),
        getFLMStatus().catch(() => null),
        listFLMModels().catch(() => ({ local: [] })),
      ]);

      setSystemInfo(hw);
      setFlmStatus(flm);
      setFlmModels(Array.isArray(flmCatalog?.local) ? flmCatalog.local : []);
      if (!selectedFlmModel && flm?.server?.model) {
        setSelectedFlmModel(flm.server.model);
      }
    };

    // Fetch agent status
    fetch(`${API_BASE}/agent/status`)
      .then(r => r.json())
      .then(setAgentStatus)
      .catch(() => setAgentStatus({ is_downloaded: false, is_running: false, dataset_ready: false }));

    // Fetch models for direct mode
    fetch(`${API_BASE}/models`)
      .then(r => r.json())
      .then(setModels)
      .catch(() => {});

    fetch(`${API_BASE}/models/staff-picks`)
      .then(r => (r.ok ? r.json() : { models: [] }))
      .then(data => setStaffPicks(Array.isArray(data?.models) ? data.models : []))
      .catch(() => setStaffPicks([]));

    loadRuntimeCompatibility();
  }, []);

  const contextOptions = [
    { id: 'general', label: 'General', icon: '💬', description: 'General assistant flow' },
    { id: 'training', label: 'Training', icon: '🚀', description: 'Finetune and LoRA focused' },
    { id: 'fleet', label: 'Fleet Ops', icon: '🌐', description: 'Device management tool context' },
    { id: 'models', label: 'Models/Data', icon: '📦', description: 'Model sourcing and datasets' },
  ];

  const hasNpu = Boolean(systemInfo?.amd_npu_available || systemInfo?.npu_available);
  const hasGpu = Boolean(systemInfo?.cuda_available || systemInfo?.rocm_available || (systemInfo?.gpus || []).length > 0);
  const effectiveDevice = deviceTarget === 'auto'
    ? (hasNpu ? 'npu' : hasGpu ? 'gpu' : 'cpu')
    : deviceTarget;

  const effectiveRuntime = runtimeTarget === 'auto'
    ? (effectiveDevice === 'npu' && flmStatus?.available ? 'fastflowlm' : 'native')
    : runtimeTarget;

  const modelSeemsCompatible = (model, target) => {
    const haystack = `${model?.name || ''} ${model?.framework || ''} ${(model?.tags || []).join(' ')} ${(model?.supported_devices || []).join(' ')}`.toLowerCase();
    if (target === 'npu') return !/(cuda-only|gpu-only)/.test(haystack);
    if (target === 'gpu') return !/(cpu-only|npu-only|flm-only)/.test(haystack);
    if (target === 'cpu') return !/(gpu-only|cuda-only|npu-only|flm-only)/.test(haystack);
    return true;
  };

  const compatibleModels = (models || []).filter((model) => modelSeemsCompatible(model, effectiveDevice));

  useEffect(() => {
    if (!selectedModel) return;
    if (!compatibleModels.some((model) => model.id === selectedModel)) {
      setSelectedModel('');
    }
  }, [selectedModel, compatibleModels]);

  const refreshRuntimeCompatibility = async () => {
    const [hw, flm, flmCatalog] = await Promise.all([
      getSystemInfo().catch(() => null),
      getFLMStatus().catch(() => null),
      listFLMModels().catch(() => ({ local: [] })),
    ]);
    setSystemInfo(hw);
    setFlmStatus(flm);
    const localFlmModels = Array.isArray(flmCatalog?.local) ? flmCatalog.local : [];
    setFlmModels(localFlmModels);

    if (!selectedFlmModel && flm?.server?.model) {
      setSelectedFlmModel(flm.server.model);
    } else if (!selectedFlmModel && localFlmModels.length) {
      setSelectedFlmModel(localFlmModels[0].tag);
    }
  };

  const ensureFastFlowModelServed = async () => {
    const modelTag = (modelReferenceInput || selectedFlmModel || flmStatus?.server?.model || '').trim();
    if (!modelTag) throw new Error('Select or enter a FastFlowLM model tag first');

    setRuntimeBusy(true);
    setRuntimeNotice('Checking FastFlowLM model availability...');
    try {
      const check = await checkFLMModel(modelTag);
      if (!check?.available) {
        throw new Error(`${modelTag} is not available locally. Pull it from FastFlowLM model catalog first.`);
      }

      setRuntimeNotice(`Serving ${modelTag} on FastFlowLM runtime...`);
      await serveFLMModel(modelTag);
      setSelectedFlmModel(modelTag);
      await refreshRuntimeCompatibility();
      setRuntimeNotice(`✅ FastFlowLM serving model: ${modelTag}`);
    } finally {
      setRuntimeBusy(false);
    }
  };

  const refreshModels = () => {
    fetch(`${API_BASE}/models`)
      .then(r => r.json())
      .then(setModels)
      .catch(() => {});
  };

  const stopFastFlowRuntime = async () => {
    setRuntimeBusy(true);
    setRuntimeNotice('Stopping FastFlowLM runtime...');
    try {
      await stopFLMServer();
      await refreshRuntimeCompatibility();
      setRuntimeNotice('⏹️ FastFlowLM server stopped.');
    } catch (e) {
      setRuntimeNotice(`❌ ${e.message || 'Failed to stop FastFlowLM server'}`);
    } finally {
      setRuntimeBusy(false);
    }
  };

  const downloadStaffPick = async (pick) => {
    if (!pick?.repo_id) {
      setDownloadNotice('This staff pick is informational for now (no direct source attached yet).');
      return;
    }

    const confirmDownload = window.confirm(
      `Download ${pick.label}?\n\nSource: ${pick.source}\nRepo: ${pick.repo_id}${pick.filename ? `\nFile: ${pick.filename}` : ''}`
    );
    if (!confirmDownload) return;

    setDownloadNotice(`Downloading ${pick.label}...`);
    setDownloadingPickId(pick.id);

    try {
      if (pick.source === 'huggingface') {
        const fd = new FormData();
        fd.append('repo_id', pick.repo_id);
        if (pick.filename) fd.append('filename', pick.filename);
        fd.append('revision', 'main');

        const res = await fetch(`${API_BASE}/models/huggingface/download`, { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Download failed');
      } else {
        throw new Error('Direct download is currently wired for HuggingFace picks.');
      }

      setDownloadNotice(`✅ Download complete: ${pick.label}`);
      refreshModels();
    } catch (e) {
      setDownloadNotice(`❌ ${e.message || 'Download failed'}`);
    } finally {
      setDownloadingPickId('');
    }
  };

  // ── Preset apply ─────────────────────────────────────────────────────────
  const applyPreset = (preset) => {
    setSelectedPreset(preset.name);
    setTemperature(preset.params.temperature);
    setTopP(preset.params.topP);
    setTopK(preset.params.topK);
    setMinP(preset.params.minP);
    setRepetitionPenalty(preset.params.repetitionPenalty);
    setMaxTokens(preset.params.maxTokens);
  };

  // ── Template change ───────────────────────────────────────────────────────
  const handleTemplateChange = (templateId) => {
    setChatTemplate(templateId);
    if (!customSystemPrompt) {
      setSystemPrompt(SYSTEM_PROMPTS[templateId] || '');
    }
  };

  // ── Agent start ───────────────────────────────────────────────────────────
  const startAgent = async () => {
    setAgentLoading(true);
    setAgentError(null);
    try {
      const res = await fetch(`${API_BASE}/agent/start`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setAgentStatus(s => ({ ...s, is_running: true, webui_url: data.webui_url || s?.webui_url }));
      } else {
        setAgentError(data.message || 'Failed to start agent');
      }
    } catch (e) {
      setAgentError(e.message);
    } finally {
      setAgentLoading(false);
    }
  };

  const downloadAgent = async () => {
    setAgentLoading(true);
    setAgentError(null);
    try {
      const res = await fetch(`${API_BASE}/agent/init`, { method: 'POST' });
      const data = await res.json();
      setAgentError(data.message || 'Nirvana runtime prepared');
    } catch (e) {
      setAgentError(e.message);
    } finally {
      setAgentLoading(false);
    }
  };

  // ── Slash command execution ───────────────────────────────────────────────
  const executeSlashCommand = async (rawCmd) => {
    const parts = rawCmd.trim().split(/\s+/);
    const cmd  = parts[0].toLowerCase();
    const args = parts.slice(1);

    const sysMsg = (content) => ({
      id:        `sys_${Date.now()}_${Math.random().toString(36).substr(2,5)}`,
      role:      'system',
      content,
      timestamp: new Date(),
    });

    switch (cmd) {
      case '/help': {
        const cats = { meta: '--- Session ---', info: '--- Info ---', session: '--- Context ---' };
        let last = null;
        const lines = [];
        SLASH_COMMANDS.forEach(c => {
          if (c.category !== last) { lines.push(cats[c.category] || ''); last = c.category; }
          lines.push(`  ${c.usage.padEnd(24)} ${c.desc}`);
        });
        setMessages(prev => [...prev, sysMsg(`Nirvana — available commands:\n\n${lines.join('\n')}\n\nType any command above and press Enter.`)]);
        break;
      }
      case '/clear': {
        setMessages([sysMsg('Conversation cleared. New thread started.')]);
        setChatError(null);
        setLastMetrics(null);
        threadId.current = `thread_${Date.now()}_${Math.random().toString(36).substr(2,9)}`;
        break;
      }
      case '/reset': {
        setMessages([sysMsg(`Session reset.\nThread: ${(() => { const t = `thread_${Date.now()}_${Math.random().toString(36).substr(2,9)}`; threadId.current = t; return t; })()}`)]);
        setChatError(null);
        setLastMetrics(null);
        break;
      }
      case '/export': {
        const blob = new Blob([JSON.stringify({ template: chatTemplate, thread: threadId.current, messages }, null, 2)], { type: 'application/json' });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href = url; a.download = `nirvana_chat_${Date.now()}.json`; a.click();
        URL.revokeObjectURL(url);
        setMessages(prev => [...prev, sysMsg('Conversation exported.')]);
        break;
      }
      case '/context': {
        const valid = contextOptions.map(c => c.id);
        const next  = args[0];
        if (next && valid.includes(next)) {
          setSelectedContext(next);
          setMessages(prev => [...prev, sysMsg(`Context → ${next}`)]);
        } else {
          setMessages(prev => [...prev, sysMsg(`Usage: /context <name>\nAvailable: ${valid.join(' | ')}`)]);
        }
        break;
      }
      case '/status': {
        try {
          const [st, rt, orch] = await Promise.all([
            fetch(`${API_BASE}/agent/status`).then(r => r.json()),
            fetch(`${API_BASE}/agent/runtime`).then(r => r.json()),
            fetch(`${API_BASE}/orchestration/state`).then(r => r.json()),
          ]);
          const h  = orch.nirvana_config || {};
          const lines = [
            `Agent:        Nirvana`,
            `Runtime:      ${rt.webui_running ? `embedded WebUI @ ${rt.webui_url}` : rt.prepared ? 'prepared, not started' : 'not prepared'}`,
            `Setup state:  ${rt.setup_state || 'not started'}`,
            `Provider:     ${rt.current_provider || '(not configured)'}`,
            `Model:        ${rt.current_model || h.default_model || '(not set)'}`,
            `Chat ready:   ${rt.chat_ready ? 'yes' : 'no'}`,
            `Onboarding:   ${rt.completed ? 'complete' : 'pending'}`,
            `MCP servers:  ${(h.mcp_servers || []).length}`,
            `Context:      ${selectedContext}`,
            `Thread:       ${threadId.current}`,
          ];
          setMessages(prev => [...prev, sysMsg(lines.join('\n'))]);
        } catch (e) {
          setMessages(prev => [...prev, sysMsg(`Status check failed: ${e.message}`)]);
        }
        break;
      }
      case '/tools': {
        try {
          const orch    = await fetch(`${API_BASE}/orchestration/state`).then(r => r.json());
          const tools   = orch.capabilities?.tools || [];
          const servers = orch.nirvana_config?.mcp_servers || [];
          const policy  = orch.nirvana_config?.tool_policy || 'approval-required';
          const lines = [
            `Built-in tools (tool policy: ${policy}):`,
            ...tools.map(t => `  ${t.id.padEnd(22)} ${t.scope}`),
            '',
            `MCP servers (${servers.length}):`,
            ...(servers.length ? servers.map((s,i) => `  [${i}] ${s}`) : ['  (none configured)']),
          ];
          setMessages(prev => [...prev, sysMsg(lines.join('\n'))]);
        } catch (e) {
          setMessages(prev => [...prev, sysMsg(`Tools fetch failed: ${e.message}`)]);
        }
        break;
      }
      case '/model': {
        try {
          const rt = await fetch(`${API_BASE}/agent/runtime`).then(r => r.json());
          const lines = [
            `Bridge:    ${rt.webui_running ? 'embedded Nirvana WebUI online' : rt.prepared ? 'prepared, not started' : 'not prepared'}`,
            `Provider:  ${rt.current_provider || '(not configured)'}`,
            `Model:     ${rt.current_model || '(not configured)'}`,
            `URL:       ${rt.webui_url || '(not available)'}`,
          ];
          setMessages(prev => [...prev, sysMsg(lines.join('\n'))]);
        } catch (e) {
          setMessages(prev => [...prev, sysMsg(`Model info failed: ${e.message}`)]);
        }
        break;
      }
      case '/config': {
        try {
          const orch = await fetch(`${API_BASE}/orchestration/state`).then(r => r.json());
          const h   = orch.nirvana_config || {};
          const rt  = orch.nirvana_runtime || {};
          const src = rt.config_sources || {};
          const presentConfigPath = (path) => {
            const legacyBrand = ['her', 'mes'].join('');
            return String(path || '')
              .replaceAll(`${legacyBrand}-agent`, 'nirvana-agent')
              .replaceAll(`${legacyBrand}.exe`, 'nirvana.exe')
              .replaceAll(`.${legacyBrand}`, '.nirvana')
              .replaceAll(`\\\\${legacyBrand}\\\\`, '\\\\nirvana\\\\')
              .replaceAll(`/${legacyBrand}/`, '/nirvana/');
          };
          const nirvanaEnv = Object.entries(src.env_variables || {}).filter(([k]) => k.startsWith('NIRVANA_'));
          const sourceLabel = (resolvedItem) => {
            const source = resolvedItem?.source || '';
            if (!source) return 'not set';
            return source.startsWith('NIRVANA_') ? source : 'legacy alias';
          };
          const lines = [
            'Nirvana runtime configuration:',
            `  enabled:           ${h.enabled}`,
            `  api_base:          ${h.api_base || '(not set)'}`,
            `  default_model:     ${h.default_model || '(not set)'}`,
            `  default_provider:  ${h.default_provider || '(not set)'}`,
            `  tool_policy:       ${h.tool_policy}`,
            '',
            'Resolved sources:',
            `  api_base:          ${sourceLabel(src.resolved_env?.api_base)}`,
            `  default_model:     ${sourceLabel(src.resolved_env?.default_model)}`,
            `  default_provider:  ${sourceLabel(src.resolved_env?.default_provider)}`,
            `  tool_policy:       ${sourceLabel(src.resolved_env?.tool_policy)}`,
            '',
            'Config files found:',
            ...((src.existing_paths || []).length
              ? src.existing_paths.map(p => `  ✓ ${presentConfigPath(p)}`)
              : ['  (none found)']),
            '',
            'Environment:',
            ...(nirvanaEnv.length
              ? nirvanaEnv.map(([k,v]) => `  ${k}=${v || '(not set)'}`)
              : ['  (no branded env vars set)']),
          ];
          setMessages(prev => [...prev, sysMsg(lines.join('\n'))]);
        } catch (e) {
          setMessages(prev => [...prev, sysMsg(`Config fetch failed: ${e.message}`)]);
        }
        break;
      }
      case '/mcp': {
        try {
          const orch    = await fetch(`${API_BASE}/orchestration/state`).then(r => r.json());
          const servers = orch.nirvana_config?.mcp_servers || [];
          const policy  = orch.nirvana_config?.tool_policy || 'approval-required';
          const lines = [
            `MCP servers (tool policy: ${policy}):`,
            ...(servers.length ? servers.map((s,i) => `  [${i}] ${s}`) : ['  (none configured)']),
            '',
            'Configure via Orchestration → Nirvana Agent Configuration.',
          ];
          setMessages(prev => [...prev, sysMsg(lines.join('\n'))]);
        } catch (e) {
          setMessages(prev => [...prev, sysMsg(`MCP fetch failed: ${e.message}`)]);
        }
        break;
      }
      case '/history': {
        const lines = [
          `Thread:   ${threadId.current}`,
          `Messages: ${messages.length}`,
          `Context:  ${selectedContext}`,
          `Mode:     ${mode}`,
          `Template: ${chatTemplate}`,
        ];
        setMessages(prev => [...prev, sysMsg(lines.join('\n'))]);
        break;
      }
      default:
        setMessages(prev => [...prev, sysMsg(`Unknown command: ${cmd}\nType /help for available commands.`)]);
    }
  };

  // ── Send chat ─────────────────────────────────────────────────────────────
  const handleSend = useCallback(async (msg = inputValue) => {
    const trimmed = msg.trim();
    if (!trimmed || isLoading) return;

    setInputValue('');
    setCmdPalette({ open: false, filter: '', selectedIdx: 0 });
    setChatError(null);

    // ── Slash command interception ──────────────────────────────────────────
    if (trimmed.startsWith('/')) {
      await executeSlashCommand(trimmed);
      return;
    }

    const userMsg = {
      id: `user_${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    const startTime = performance.now();
    try {
      let response, data;

      if (mode === 'agent') {
        // Use system agent
        const backendMessages = messages
          .filter(m => m.role === 'user' || m.role === 'assistant')
          .map(m => ({ role: m.role, content: m.content }));
        backendMessages.push({ role: 'user', content: trimmed });

        response = await fetch(`${API_BASE}/agent/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: backendMessages,
            use_fleet_tools: selectedContext === 'fleet',
            context_hint: selectedContext,
            temperature,
            max_tokens: maxTokens,
          }),
        });
        data = await response.json();
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      } else {
        // Direct inference (native or FastFlowLM runtime)
        if (effectiveRuntime === 'fastflowlm') {
          const flmModel = (modelReferenceInput || selectedFlmModel || flmStatus?.server?.model || '').trim();
          if (!flmModel) throw new Error('Select or enter a FastFlowLM model tag for NPU inference');

          let streamed = '';
          await chatFLM(
            [{ role: 'user', content: buildPrompt(trimmed) }],
            flmModel,
            temperature,
            maxTokens,
            (delta) => { streamed += delta; }
          );

          data = {
            response: streamed || '(no response generated)',
            tokens_generated: estimateTokens(streamed || ''),
            nirvana_runtime: {
              engine: 'fastflowlm',
              model_file: flmModel,
              uses_mock_responses: false,
            },
          };
        } else {
          const nativeModelId = (selectedModel || modelReferenceInput || '').trim();
          if (!nativeModelId) throw new Error('Select a model or enter a model ID/path for direct inference');
          const fd = new FormData();
          fd.append('model_id', nativeModelId);
          fd.append('prompt', buildPrompt(trimmed));
          fd.append('max_tokens', String(maxTokens));
          fd.append('temperature', String(temperature));

          response = await fetch(`${API_BASE}/inference/generate-text`, {
            method: 'POST',
            body: fd,
          });
          data = await response.json();
          if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        }
      }

      const elapsed = performance.now() - startTime;
      const content = data.response || data.message || data.text || data.generated_text || 'No response';
      const tokenCount = data.usage?.completion_tokens || data.tokens_generated || estimateTokens(content);

      setLastMetrics({
        latency_ms: Math.round(elapsed),
        tokens: tokenCount,
        tps: tokenCount > 0 ? Math.round(tokenCount / (elapsed / 1000)) : 0,
      });

      const assistantMsg = {
        id: `assistant_${Date.now()}`,
        role: 'assistant',
        content,
        timestamp: new Date(),
        metadata: {
          reasoning: data.reasoning || null,
          toolCalls: data.tool_calls || [],
          fleetContext: data.fleet_context || null,
          runtime: data.nirvana_runtime || null,
        },
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      setChatError(err.message);
      setMessages(prev => [...prev, {
        id: `error_${Date.now()}`,
        role: 'assistant',
        content: `Error: ${err.message}`,
        timestamp: new Date(),
        isError: true,
      }]);
    } finally {
      setIsLoading(false);
    }
  }, [messages, inputValue, isLoading, mode, selectedModel, temperature, maxTokens, chatTemplate, systemPrompt, selectedContext, effectiveRuntime, modelReferenceInput, selectedFlmModel, flmStatus]);

  // Build prompt from template
  const buildPrompt = (userMsg) => {
    switch (chatTemplate) {
      case 'alpaca':
        return `${systemPrompt ? `${systemPrompt}\n\n` : ''}### Instruction:\n${userMsg}\n\n### Response:\n`;
      case 'chatml':
        return `${systemPrompt ? `<|im_start|>system\n${systemPrompt}<|im_end|>\n` : ''}<|im_start|>user\n${userMsg}<|im_end|>\n<|im_start|>assistant\n`;
      case 'llama3':
        return `<|begin_of_text|>${systemPrompt ? `<|start_header_id|>system<|end_header_id|>\n${systemPrompt}<|eot_id|>` : ''}<|start_header_id|>user<|end_header_id|>\n${userMsg}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n`;
      case 'mistral':
        return `[INST] ${systemPrompt ? `${systemPrompt}\n` : ''}${userMsg} [/INST]`;
      case 'phi3':
        return `${systemPrompt ? `<|system|>\n${systemPrompt}<|end|>\n` : ''}<|user|>\n${userMsg}<|end|>\n<|assistant|>\n`;
      case 'gemma':
        return `<start_of_turn>user\n${userMsg}<end_of_turn>\n<start_of_turn>model\n`;
      case 'qwen2':
        return `${systemPrompt ? `<|im_start|>system\n${systemPrompt}<|im_end|>\n` : ''}<|im_start|>user\n${userMsg}<|im_end|>\n<|im_start|>assistant\n`;
      case 'raw':
        return userMsg;
      default: // auto
        return userMsg;
    }
  };

  const estimateTokens = (text) => Math.ceil(text.split(/\s+/).length * 1.3);

  const handleKeyDown = (e) => {
    // ── Command palette navigation ──────────────────────────────────────────
    if (cmdPalette.open) {
      const filtered = SLASH_COMMANDS.filter(c =>
        c.cmd.startsWith(cmdPalette.filter) || c.desc.toLowerCase().includes(cmdPalette.filter.slice(1).toLowerCase())
      );
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setCmdPalette(p => ({ ...p, selectedIdx: Math.min(p.selectedIdx + 1, filtered.length - 1) }));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setCmdPalette(p => ({ ...p, selectedIdx: Math.max(p.selectedIdx - 1, 0) }));
        return;
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && filtered[cmdPalette.selectedIdx] && cmdPalette.filter !== filtered[cmdPalette.selectedIdx]?.cmd)) {
        const chosen = filtered[cmdPalette.selectedIdx];
        if (chosen && e.key === 'Tab') {
          e.preventDefault();
          setInputValue(chosen.cmd + ' ');
          setCmdPalette({ open: false, filter: '', selectedIdx: 0 });
          return;
        }
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setCmdPalette({ open: false, filter: '', selectedIdx: 0 });
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e) => {
    const val = e.target.value;
    setInputValue(val);
    if (val.startsWith('/') && val.length >= 1) {
      setCmdPalette(p => ({ open: true, filter: val.trim().split(/\s/)[0], selectedIdx: 0 }));
    } else {
      setCmdPalette({ open: false, filter: '', selectedIdx: 0 });
    }
  };

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const clearChat = () => {
    setMessages([]);
    setChatError(null);
    setLastMetrics(null);
    threadId.current = `thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  };

  const exportChat = () => {
    const blob = new Blob(
      [JSON.stringify({ template: chatTemplate, messages }, null, 2)],
      { type: 'application/json' }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat_export_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Playground inference ──────────────────────────────────────────────────
  const runPlayground = async () => {
    const nativeModelId = (selectedModel || modelReferenceInput || '').trim();
    const flmModelId = (modelReferenceInput || selectedFlmModel || flmStatus?.server?.model || '').trim();
    if (effectiveRuntime === 'fastflowlm') {
      if (!flmModelId) { setPlayError('Select or enter a FastFlowLM model tag first'); return; }
    } else if (!nativeModelId) {
      setPlayError('Select a model or enter a model ID/path first');
      return;
    }

    setPlayLoading(true);
    setPlayError(null);
    setPlayResult(null);
    try {
      const fd = new FormData();
      if (effectiveRuntime !== 'fastflowlm') {
        fd.append('model_id', nativeModelId);
      }

      if (playTab === 'text') {
        if (!playPrompt.trim()) { setPlayError('Enter a prompt'); setPlayLoading(false); return; }
        if (effectiveRuntime === 'fastflowlm') {
          const flmModel = flmModelId;
          if (!flmModel) {
            setPlayError('Select or enter a FastFlowLM model tag first');
            setPlayLoading(false);
            return;
          }

          let streamed = '';
          await chatFLM(
            [{ role: 'user', content: buildPrompt(playPrompt) }],
            flmModel,
            temperature,
            maxTokens,
            (delta) => { streamed += delta; }
          );

          setPlayResult({ text: streamed, runtime: 'fastflowlm', model: flmModel, tokens_generated: estimateTokens(streamed || '') });
        } else {
          fd.append('prompt', playPrompt);
          fd.append('max_tokens', String(maxTokens));
          fd.append('temperature', String(temperature));
          const res = await fetch(`${API_BASE}/inference/generate-text`, { method: 'POST', body: fd });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || 'Generation failed');
          setPlayResult(data);
        }
      } else if (playTab === 'classify' || playTab === 'detect') {
        const file = fileRef.current?.files?.[0];
        if (!file) { setPlayError('Upload an image first'); setPlayLoading(false); return; }
        fd.append('image', file);
        if (playTab === 'detect') fd.append('confidence_threshold', '0.3');
        const endpoint = playTab === 'classify' ? '/inference/classify' : '/inference/detect';
        const res = await fetch(`${API_BASE}${endpoint}`, { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Inference failed');
        setPlayResult(data);
      } else if (playTab === 'imagegen') {
        if (!playPrompt.trim()) { setPlayError('Enter a prompt'); setPlayLoading(false); return; }
        fd.append('prompt', playPrompt);
        fd.append('width', '512'); fd.append('height', '512');
        const res = await fetch(`${API_BASE}/inference/generate-image`, { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Generation failed');
        setPlayResult(data);
      } else if (playTab === 'audio' || playTab === 'video') {
        const file = fileRef.current?.files?.[0];
        if (!file) { setPlayError(`Upload a ${playTab} file first`); setPlayLoading(false); return; }
        fd.append('file', file);
        const res = await fetch(`${API_BASE}/inference/${playTab}`, { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Inference failed');
        setPlayResult(data);
      }
    } catch (e) {
      setPlayError(e.message);
    } finally {
      setPlayLoading(false);
    }
  };

  // ── UI Styles ─────────────────────────────────────────────────────────────
  const panelStyle = {
    background: '#141927', borderRadius: 12, border: '1px solid #2d3748',
    overflow: 'hidden', display: 'flex', flexDirection: 'column',
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, height: '100%', minHeight: 0, overflow: 'hidden', gap: 0 }}>
      {/* Page Header */}
      <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid #2d3748', background: '#0f1724', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: 8 }}>
              <FlaskConical size={22} color="#667eea" /> Chat &amp; Playground
            </h2>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: '#718096' }}>
              Unified testing panel · Unsloth Studio compatible · Multi-modal inference
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {/* View toggle */}
            <div style={{ display: 'flex', background: '#1a2035', borderRadius: 8, overflow: 'hidden', border: '1px solid #2d3748' }}>
              <button onClick={() => setActiveView('chat')} style={{
                padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                background: activeView === 'chat' ? '#667eea' : 'transparent',
                color: activeView === 'chat' ? '#fff' : '#718096',
              }}>
                <MessageSquare size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />Chat
              </button>
              <button onClick={() => setActiveView('playground')} style={{
                padding: '6px 14px', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                background: activeView === 'playground' ? '#667eea' : 'transparent',
                color: activeView === 'playground' ? '#fff' : '#718096',
              }}>
                <Play size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />Playground
              </button>
            </div>
            {/* Mode toggle (chat view only) */}
            {activeView === 'chat' && (
              <div style={{ display: 'flex', background: '#1a2035', borderRadius: 8, overflow: 'hidden', border: '1px solid #2d3748' }}>
                <button onClick={() => setMode('agent')} style={{
                  padding: '6px 12px', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 600,
                  background: mode === 'agent' ? '#38a169' : 'transparent',
                  color: mode === 'agent' ? '#fff' : '#718096',
                }}>
                  <Bot size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />Agent
                </button>
                <button onClick={() => setMode('direct')} style={{
                  padding: '6px 12px', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 600,
                  background: mode === 'direct' ? '#d69e2e' : 'transparent',
                  color: mode === 'direct' ? '#fff' : '#718096',
                }}>
                  <Cpu size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />Direct
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Layout */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden', gap: 0 }}>

        {/* LEFT SETTINGS PANEL */}
        <div style={{
          width: 260, flexShrink: 0, background: '#0f1724',
          borderRight: '1px solid #2d3748', overflowY: 'auto', padding: 10,
        }}>

          {/* Context selector */}
          <div style={{ marginBottom: 10, padding: 10, borderRadius: 8, background: '#1a2035', border: '1px solid #2d3748' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', marginBottom: 6 }}>CHAT CONTEXT</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {contextOptions.map((ctx) => (
                <button
                  key={ctx.id}
                  onClick={() => setSelectedContext(ctx.id)}
                  style={{
                    textAlign: 'left', padding: '6px 8px', borderRadius: 6, border: '1px solid',
                    borderColor: selectedContext === ctx.id ? '#667eea' : '#2d3748',
                    background: selectedContext === ctx.id ? '#667eea22' : 'transparent',
                    color: selectedContext === ctx.id ? '#90cdf4' : '#a0aec0',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontSize: 11, fontWeight: 700 }}>{ctx.icon} {ctx.label}</div>
                  <div style={{ fontSize: 10, color: '#718096' }}>{ctx.description}</div>
                </button>
              ))}
            </div>
          </div>

          {/* FastFlowLM surfaced entry point */}
          <div style={{ marginBottom: 10, padding: 10, borderRadius: 8, background: 'linear-gradient(180deg, #1a2035 0%, #141927 100%)', border: '1px solid #2d3748' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Zap size={12} color="#667eea" /> FASTFLOWLM · RYZEN AI NPU
            </div>
            <div style={{ fontSize: 10, color: '#90cdf4', fontWeight: 700, marginBottom: 4 }}>
              Best path for AMD Ryzen™ AI NPU acceleration
            </div>
            <div style={{ fontSize: 10, color: '#718096', lineHeight: 1.5, marginBottom: 8 }}>
              Use FastFlowLM to pull, validate, and serve NPU-optimized models with the local FLM runtime.
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <a
                href="/fastflowlm"
                style={{
                  flex: 1,
                  textAlign: 'center',
                  padding: '6px 8px',
                  borderRadius: 6,
                  background: '#667eea',
                  color: '#fff',
                  fontSize: 10,
                  fontWeight: 700,
                  textDecoration: 'none',
                }}
              >
                Open FastFlowLM
              </a>
              <button
                onClick={() => handleSend('How do I use FastFlowLM on Ryzen AI NPU in this workspace?')}
                style={{
                  flex: 1,
                  padding: '6px 8px',
                  borderRadius: 6,
                  border: '1px solid #2d3748',
                  background: 'transparent',
                  color: '#a0aec0',
                  fontSize: 10,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Explain Setup
              </button>
            </div>
          </div>

          {/* Unified runtime compatibility layer */}
          <div style={{ marginBottom: 10, padding: 10, borderRadius: 8, background: '#1a2035', border: '1px solid #2d3748' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Cpu size={12} color="#667eea" /> DEVICE / RUNTIME COMPATIBILITY
            </div>
            <div style={{ display: 'grid', gap: 6 }}>
              <label style={{ fontSize: 10, color: '#718096' }}>Target Device</label>
              <select
                value={deviceTarget}
                onChange={(e) => setDeviceTarget(e.target.value)}
                style={{ width: '100%', padding: '6px 8px', borderRadius: 6, background: '#141927', border: '1px solid #2d3748', color: '#e2e8f0', fontSize: 11 }}
              >
                <option value="auto">Auto-detect ({effectiveDevice.toUpperCase()})</option>
                <option value="cpu">CPU</option>
                <option value="gpu" disabled={!hasGpu}>GPU {!hasGpu ? '(not detected)' : ''}</option>
                <option value="npu" disabled={!hasNpu}>NPU {!hasNpu ? '(not detected)' : ''}</option>
              </select>

              <label style={{ fontSize: 10, color: '#718096' }}>Runtime Engine</label>
              <select
                value={runtimeTarget}
                onChange={(e) => setRuntimeTarget(e.target.value)}
                style={{ width: '100%', padding: '6px 8px', borderRadius: 6, background: '#141927', border: '1px solid #2d3748', color: '#e2e8f0', fontSize: 11 }}
              >
                <option value="auto">Auto ({effectiveRuntime})</option>
                <option value="native">Native Inference API</option>
                <option value="fastflowlm" disabled={!flmStatus?.available}>FastFlowLM {!flmStatus?.available ? '(not installed)' : ''}</option>
              </select>

              <div style={{ fontSize: 10, color: '#90cdf4' }}>
                Effective: <strong>{effectiveDevice.toUpperCase()}</strong> → <strong>{effectiveRuntime}</strong>
              </div>

              <input
                type="text"
                value={modelReferenceInput}
                onChange={(e) => setModelReferenceInput(e.target.value)}
                placeholder="Model URL/ID/tag or local path"
                style={{ width: '100%', padding: '6px 8px', borderRadius: 6, background: '#141927', border: '1px solid #2d3748', color: '#e2e8f0', fontSize: 11 }}
              />

              {effectiveRuntime === 'fastflowlm' && (
                <>
                  <select
                    value={selectedFlmModel}
                    onChange={(e) => setSelectedFlmModel(e.target.value)}
                    style={{ width: '100%', padding: '6px 8px', borderRadius: 6, background: '#141927', border: '1px solid #2d3748', color: '#e2e8f0', fontSize: 11 }}
                  >
                    <option value="">Select FastFlowLM model...</option>
                    {flmModels.map((m) => (
                      <option key={m.tag} value={m.tag}>{m.name || m.tag}</option>
                    ))}
                  </select>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={ensureFastFlowModelServed}
                      disabled={runtimeBusy}
                      style={{ flex: 1, padding: '6px 8px', borderRadius: 6, border: 'none', background: '#38a169', color: '#fff', fontSize: 10, fontWeight: 700, cursor: 'pointer' }}
                    >
                      {runtimeBusy ? 'Working...' : 'Serve FLM Model'}
                    </button>
                    <button
                      onClick={stopFastFlowRuntime}
                      disabled={runtimeBusy}
                      style={{ flex: 1, padding: '6px 8px', borderRadius: 6, border: '1px solid #2d3748', background: 'transparent', color: '#a0aec0', fontSize: 10, fontWeight: 700, cursor: 'pointer' }}
                    >
                      Stop FLM
                    </button>
                  </div>
                </>
              )}

              {runtimeNotice && (
                <div style={{ fontSize: 10, color: '#a0aec0', whiteSpace: 'pre-wrap' }}>{runtimeNotice}</div>
              )}
            </div>
          </div>

          {/* Agent Status (chat mode only) */}
          {activeView === 'chat' && mode === 'agent' && (
            <div style={{ marginBottom: 10, padding: 10, borderRadius: 8, background: '#1a2035', border: '1px solid #2d3748' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', marginBottom: 6 }}>
                <Bot size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />SYSTEM AGENT
              </div>
              {agentStatus ? (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <div style={{
                      width: 8, height: 8, borderRadius: '50%',
                      background: agentStatus.is_running ? '#48bb78' : agentStatus.is_downloaded ? '#ecc94b' : '#fc8181'
                    }} />
                    <span style={{ fontSize: 11, color: '#a0aec0' }}>
                      {agentStatus.is_running ? 'Nirvana WebUI · online' : agentStatus.is_downloaded ? 'Nirvana bridge · prepared' : 'Nirvana bridge · not prepared'}
                    </span>
                  </div>
                  {!agentStatus.is_running && (
                    <div style={{ display: 'flex', gap: 4 }}>
                      {!agentStatus.is_downloaded && (
                        <button onClick={downloadAgent} disabled={agentLoading} style={{
                          flex: 1, padding: '4px 8px', borderRadius: 6, border: 'none', cursor: 'pointer',
                          background: '#2b6cb0', color: '#fff', fontSize: 10, fontWeight: 600,
                        }}>
                          {agentLoading ? <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} /> : 'Prepare'}
                        </button>
                      )}
                      <button onClick={startAgent} disabled={agentLoading} style={{
                        flex: 1, padding: '4px 8px', borderRadius: 6, border: 'none', cursor: 'pointer',
                        background: '#38a169', color: '#fff', fontSize: 10, fontWeight: 600,
                      }}>
                        {agentLoading ? <Loader2 size={10} /> : 'Launch UI'}
                      </button>
                    </div>
                  )}
                  {agentError && <div style={{ fontSize: 10, color: '#fc8181', marginTop: 4 }}>{agentError}</div>}
                </>
              ) : (
                <div style={{ fontSize: 11, color: '#718096' }}>Checking status...</div>
              )}
            </div>
          )}

          {/* Direct inference model selector */}
          {(activeView === 'playground' || mode === 'direct') && (
            <div style={{ marginBottom: 10 }}>
              <label style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', display: 'block', marginBottom: 4 }}>
                <Cpu size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />MODEL
              </label>
              <select
                value={selectedModel}
                onChange={e => setSelectedModel(e.target.value)}
                style={{
                  width: '100%', padding: '6px 8px', borderRadius: 6, background: '#1a2035',
                  border: '1px solid #2d3748', color: '#e2e8f0', fontSize: 11,
                }}
              >
                <option value="">Select model...</option>
                {compatibleModels.map(m => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
          )}

          {/* Inference Presets */}
          <CollapsibleSection title="Inference Presets" icon={Zap} defaultOpen={true}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {BUILTIN_PRESETS.map(preset => (
                <button
                  key={preset.name}
                  onClick={() => applyPreset(preset)}
                  style={{
                    padding: '3px 8px', borderRadius: 4, border: '1px solid',
                    cursor: 'pointer', fontSize: 10, fontWeight: 600,
                    borderColor: selectedPreset === preset.name ? '#667eea' : '#2d3748',
                    background: selectedPreset === preset.name ? '#667eea22' : 'transparent',
                    color: selectedPreset === preset.name ? '#667eea' : '#718096',
                  }}
                >
                  {preset.name}
                </button>
              ))}
            </div>
          </CollapsibleSection>

          {/* Inference Parameters */}
          <CollapsibleSection title="Inference Parameters" icon={Settings} defaultOpen={true}>
            <SliderControl label="Temperature" value={temperature} onChange={v => { setTemperature(v); setSelectedPreset('Custom'); }}
              min={0} max={2} step={0.01} description="Randomness of output" />
            <SliderControl label="Top P (nucleus)" value={topP} onChange={v => { setTopP(v); setSelectedPreset('Custom'); }}
              min={0} max={1} step={0.01} description="Cumulative probability cutoff" />
            <SliderControl label="Top K" value={topK} onChange={v => { setTopK(v); setSelectedPreset('Custom'); }}
              min={1} max={200} step={1} decimals={0} description="Top K tokens to sample from" />
            <SliderControl label="Min P" value={minP} onChange={v => { setMinP(v); setSelectedPreset('Custom'); }}
              min={0} max={0.5} step={0.01} description="Minimum probability threshold" />
            <SliderControl label="Repetition Penalty" value={repetitionPenalty} onChange={v => { setRepetitionPenalty(v); setSelectedPreset('Custom'); }}
              min={1} max={2} step={0.01} description="Penalize repeated tokens" />
            <SliderControl label="Max Tokens" value={maxTokens} onChange={v => { setMaxTokens(v); setSelectedPreset('Custom'); }}
              min={64} max={4096} step={64} decimals={0} description="Maximum output length" />
          </CollapsibleSection>

          {/* Chat Template (chat view only) */}
          {activeView === 'chat' && (
            <CollapsibleSection title="Chat Template" icon={BookOpen} defaultOpen={false}>
              <div style={{ marginBottom: 8 }}>
                {CHAT_TEMPLATES.map(t => (
                  <button
                    key={t.id}
                    onClick={() => handleTemplateChange(t.id)}
                    style={{
                      display: 'block', width: '100%', textAlign: 'left', marginBottom: 3,
                      padding: '5px 8px', borderRadius: 6, border: '1px solid',
                      cursor: 'pointer', fontSize: 10,
                      borderColor: chatTemplate === t.id ? '#667eea' : '#2d3748',
                      background: chatTemplate === t.id ? '#667eea22' : 'transparent',
                      color: chatTemplate === t.id ? '#90cdf4' : '#718096',
                    }}
                  >
                    <div style={{ fontWeight: 700, color: chatTemplate === t.id ? '#90cdf4' : '#a0aec0' }}>{t.label}</div>
                    <div style={{ fontSize: 9, color: '#718096' }}>{t.description}</div>
                  </button>
                ))}
              </div>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <label style={{ fontSize: 11, color: '#a0aec0', fontWeight: 600 }}>System Prompt</label>
                  <button
                    onClick={() => setCustomSystemPrompt(v => !v)}
                    style={{ fontSize: 9, color: '#667eea', background: 'none', border: 'none', cursor: 'pointer' }}
                  >
                    {customSystemPrompt ? 'Use Default' : 'Customize'}
                  </button>
                </div>
                <textarea
                  value={systemPrompt}
                  onChange={e => { setSystemPrompt(e.target.value); setCustomSystemPrompt(true); }}
                  rows={4}
                  style={{
                    width: '100%', boxSizing: 'border-box', padding: '6px 8px',
                    borderRadius: 6, background: '#1a2035', border: '1px solid #2d3748',
                    color: '#e2e8f0', fontSize: 10, resize: 'vertical', fontFamily: 'monospace',
                  }}
                  placeholder="System prompt..."
                />
              </div>
            </CollapsibleSection>
          )}

          {/* Metrics */}
          {activeView === 'chat' && lastMetrics && (
            <div style={{ marginTop: 8, padding: 10, borderRadius: 8, background: '#1a2035', border: '1px solid #2d3748' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', marginBottom: 6 }}>
                <BarChart2 size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />LAST RESPONSE
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {[
                  { icon: Clock, label: 'Latency', value: `${lastMetrics.latency_ms}ms` },
                  { icon: Hash, label: 'Tokens', value: lastMetrics.tokens },
                  { icon: Zap, label: 'TPS', value: `${lastMetrics.tps}/s` },
                ].map(({ icon: Icon, label, value }) => (
                  <div key={label} style={{ textAlign: 'center', padding: 6, background: '#141927', borderRadius: 6 }}>
                    <Icon size={12} color="#667eea" />
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>{value}</div>
                    <div style={{ fontSize: 9, color: '#718096' }}>{label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Playground Tabs (playground view) */}
          {activeView === 'playground' && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', marginBottom: 6 }}>MODALITY</div>
              {PLAYGROUND_TABS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => { setPlayTab(id); setPlayResult(null); setPlayError(null); setPlayPreview(null); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                    padding: '6px 10px', marginBottom: 3, borderRadius: 6, border: '1px solid',
                    cursor: 'pointer', fontSize: 11, fontWeight: 600,
                    borderColor: playTab === id ? '#667eea' : '#2d3748',
                    background: playTab === id ? '#667eea22' : 'transparent',
                    color: playTab === id ? '#90cdf4' : '#718096',
                  }}
                >
                  <Icon size={13} /> {label}
                </button>
              ))}
            </div>
          )}

          {/* Staff picks and system-wide downloads */}
          <CollapsibleSection title="Staff Picks" icon={Download} defaultOpen={false}>
            <div style={{ marginBottom: 8 }}>
              <button
                onClick={() => setStaffPicksOpen(v => !v)}
                style={{
                  width: '100%', padding: '6px 8px', borderRadius: 6, border: '1px solid #2d3748',
                  background: '#1a2035', color: '#a0aec0', fontSize: 11, cursor: 'pointer',
                }}
              >
                {staffPicksOpen ? 'Hide staff picks' : `Show staff picks (${staffPicks.length})`}
              </button>
            </div>

            {staffPicksOpen && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {staffPicks.slice(0, 6).map((pick) => {
                  const canDownload = pick?.source === 'huggingface' && Boolean(pick?.repo_id);
                  const isDownloading = downloadingPickId === pick.id;

                  return (
                    <div key={pick.id} style={{ padding: 8, borderRadius: 6, background: '#1a2035', border: '1px solid #2d3748' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: '#e2e8f0' }}>{pick.label}</div>
                      <div style={{ fontSize: 10, color: '#718096' }}>{pick.framework} · {pick.size}</div>
                      <div style={{ fontSize: 10, color: '#718096' }}>{(pick.capabilities || []).join(', ')}</div>
                      {!canDownload && (
                        <div style={{ marginTop: 6, fontSize: 10, color: '#d6bcfa' }}>
                          Advisory only · no direct download target configured yet
                        </div>
                      )}
                      <button
                        onClick={() => downloadStaffPick(pick)}
                        disabled={!canDownload || isDownloading}
                        style={{
                          marginTop: 6, width: '100%', padding: '5px 8px', borderRadius: 6, border: 'none',
                          background: canDownload ? '#667eea' : '#2d3748',
                          color: canDownload ? '#fff' : '#718096',
                          fontSize: 10, fontWeight: 700, cursor: canDownload ? 'pointer' : 'not-allowed',
                        }}
                        title={canDownload ? 'Add this staff pick to your local system' : 'This pick is advisory-only for now'}
                      >
                        {isDownloading ? 'Downloading…' : canDownload ? 'Add to system' : 'Advisory only'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            {downloadNotice && (
              <div style={{ marginTop: 8, fontSize: 10, color: '#a0aec0', whiteSpace: 'pre-wrap' }}>
                {downloadNotice}
              </div>
            )}
          </CollapsibleSection>
        </div>

        {/* CENTER — Chat or Playground */}
        {activeView === 'chat' ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#0f1724' }}>
            {/* Chat toolbar */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 16px', borderBottom: '1px solid #2d3748', background: '#141927', flexShrink: 0,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: mode === 'agent' && agentStatus?.is_running ? '#48bb78' : '#ecc94b' }} />
                <span style={{ fontSize: 12, color: '#a0aec0' }}>
                  {mode === 'agent'
                    ? 'Nirvana'
                    : `Direct (${effectiveRuntime}): ${
                        effectiveRuntime === 'fastflowlm'
                          ? (modelReferenceInput || selectedFlmModel || flmStatus?.server?.model || 'no FLM model selected')
                          : (models.find(m => m.id === selectedModel)?.name || 'no model selected')
                      }`}
                </span>
                <span style={{ fontSize: 10, color: '#718096', background: '#1a2035', padding: '1px 6px', borderRadius: 4 }}>
                  {chatTemplate === 'auto' ? 'Auto template' : CHAT_TEMPLATES.find(t => t.id === chatTemplate)?.label}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={exportChat} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #2d3748', background: 'transparent', cursor: 'pointer', color: '#718096', fontSize: 11 }}>
                  <Download size={12} style={{ verticalAlign: 'middle', marginRight: 3 }} />Export
                </button>
                <button onClick={clearChat} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #2d3748', background: 'transparent', cursor: 'pointer', color: '#fc8181', fontSize: 11 }}>
                  <Trash2 size={12} style={{ verticalAlign: 'middle', marginRight: 3 }} />Clear
                </button>
              </div>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {messages.length === 0 && (
                <div style={{ textAlign: 'center', marginTop: 60, color: '#718096' }}>
                  <div style={{ fontSize: 48, marginBottom: 12 }}>💬</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#a0aec0', marginBottom: 6 }}>
                    {mode === 'agent' ? '⚡ Nirvana' : 'Start a conversation'}
                  </div>
                  <div style={{ fontSize: 12, color: '#718096' }}>
                    {mode === 'agent'
                      ? 'Type a message or /help for slash commands'
                      : 'Select a model from the left panel and start chatting'}
                  </div>
                  {/* Quick start suggestions */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center', marginTop: 20 }}>
                    {(mode === 'agent' ? [
                      '/status',
                      '/tools',
                      '/model',
                      '/mcp',
                      'What models are available?',
                      'Show fleet status',
                    ] : [
                      'What models are available?',
                      'Help me finetune a model',
                      'Explain LoRA vs QLoRA',
                      'Show fleet status',
                      'What is Alpaca format?',
                      'Compare ChatML vs ShareGPT',
                    ]).map(q => (
                      <button
                        key={q}
                        onClick={() => handleSend(q)}
                        style={{
                          padding: '6px 12px', borderRadius: 20, border: '1px solid #2d3748',
                          background: '#141927', cursor: 'pointer', color: '#90cdf4', fontSize: 12,
                        }}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg) => {
                // ── System message (slash command output) ────────────────────
                if (msg.role === 'system') {
                  return (
                    <div key={msg.id} style={{ padding: '10px 14px', borderRadius: 8, background: '#050d1a', border: '1px solid #1a3a2a', borderLeft: '3px solid #48bb78', fontSize: 12, fontFamily: 'monospace', color: '#68d391', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      <span style={{ color: '#48bb78', marginRight: 8, userSelect: 'none' }}>nirvana:~$</span>
                      {msg.content}
                      <div style={{ marginTop: 6, fontSize: 10, color: '#2f855a' }}>{new Date(msg.timestamp).toLocaleTimeString()}</div>
                    </div>
                  );
                }

                const isUser = msg.role === 'user';
                const isError = msg.isError;
                return (
                  <div key={msg.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexDirection: isUser ? 'row-reverse' : 'row' }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: isUser ? '#667eea' : isError ? '#fc8181' : '#2d3748',
                      fontSize: 13, fontWeight: 700, color: '#fff',
                    }}>
                      {isUser ? 'U' : isError ? '!' : 'A'}
                    </div>
                    <div style={{ maxWidth: '75%' }}>
                      <div style={{
                        padding: '10px 14px', borderRadius: 12, fontSize: 13, lineHeight: 1.6,
                        background: isUser ? '#667eea22' : isError ? '#fc818122' : '#1a2035',
                        border: `1px solid ${isUser ? '#667eea44' : isError ? '#fc818144' : '#2d3748'}`,
                        color: '#e2e8f0', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                      }}>
                        {msg.content}
                        {msg.metadata?.reasoning && (
                          <details style={{ marginTop: 8, fontSize: 11, color: '#718096' }}>
                            <summary style={{ cursor: 'pointer' }}>🧠 Reasoning</summary>
                            <pre style={{ margin: '4px 0 0', fontSize: 10, whiteSpace: 'pre-wrap' }}>{msg.metadata.reasoning}</pre>
                          </details>
                        )}
                        {msg.metadata?.toolCalls?.length > 0 && (
                          <details style={{ marginTop: 8, fontSize: 11, color: '#718096' }}>
                            <summary style={{ cursor: 'pointer' }}>⚙️ Tool Calls ({msg.metadata.toolCalls.length})</summary>
                            {msg.metadata.toolCalls.map((t, i) => (
                              <div key={i} style={{ fontSize: 10, marginTop: 2 }}><code>{t.name}</code> {t.result ? '✓' : ''}</div>
                            ))}
                          </details>
                        )}
                        {msg.metadata?.runtime && (
                          <details style={{ marginTop: 8, fontSize: 11, color: '#718096' }}>
                            <summary style={{ cursor: 'pointer' }}>✅ Runtime Provenance</summary>
                            <div style={{ fontSize: 10, marginTop: 2 }}><code>engine</code>: {msg.metadata.runtime.engine}</div>
                            <div style={{ fontSize: 10, marginTop: 2 }}><code>model</code>: {msg.metadata.runtime.model_file}</div>
                            <div style={{ fontSize: 10, marginTop: 2 }}><code>uses_mock_responses</code>: {String(msg.metadata.runtime.uses_mock_responses)}</div>
                          </details>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, flexDirection: isUser ? 'row-reverse' : 'row' }}>
                        <span style={{ fontSize: 10, color: '#718096' }}>{new Date(msg.timestamp).toLocaleTimeString()}</span>
                        <button
                          onClick={() => copyToClipboard(msg.content, msg.id)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#718096', padding: 2 }}
                        >
                          {copiedId === msg.id ? <CheckCircle size={12} color="#48bb78" /> : <Copy size={12} />}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}

              {isLoading && (
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#2d3748', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>A</div>
                  <div style={{ padding: '10px 14px', borderRadius: 12, background: '#1a2035', border: '1px solid #2d3748', display: 'flex', gap: 6, alignItems: 'center' }}>
                    <Loader2 size={14} color="#667eea" style={{ animation: 'spin 1s linear infinite' }} />
                    <span style={{ fontSize: 12, color: '#718096' }}>Generating...</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div style={{ padding: '12px 16px', borderTop: '1px solid #2d3748', background: '#141927', flexShrink: 0 }}>
              {chatError && (
                <div style={{ padding: '6px 10px', borderRadius: 6, background: '#fc818122', border: '1px solid #fc818144', color: '#fc8181', fontSize: 12, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <AlertCircle size={14} /> {chatError}
                  <button onClick={() => setChatError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#fc8181' }}><X size={12} /></button>
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', position: 'relative' }}>
                {/* Command palette */}
                {cmdPalette.open && (() => {
                  const filtered = SLASH_COMMANDS.filter(c =>
                    c.cmd.startsWith(cmdPalette.filter) || c.desc.toLowerCase().includes(cmdPalette.filter.slice(1).toLowerCase())
                  );
                  return filtered.length > 0 ? (
                    <div style={{ position: 'absolute', bottom: '100%', left: 0, right: 60, background: '#0d1526', border: '1px solid #667eea55', borderBottom: 'none', borderRadius: '8px 8px 0 0', zIndex: 200, maxHeight: 260, overflowY: 'auto' }}>
                      <div style={{ padding: '5px 12px', borderBottom: '1px solid #1e2a45', fontSize: 10, color: '#4a5568', letterSpacing: 1 }}>COMMANDS — {filtered.length} match{filtered.length !== 1 ? 'es' : ''} · Tab to complete · Enter to run</div>
                      {filtered.map((c, i) => (
                        <div key={c.cmd} onMouseDown={e => { e.preventDefault(); setInputValue(c.cmd + ' '); setCmdPalette({ open: false, filter: '', selectedIdx: 0 }); inputRef.current?.focus(); }}
                          style={{ padding: '7px 12px', cursor: 'pointer', display: 'flex', gap: 10, alignItems: 'center', background: i === cmdPalette.selectedIdx ? '#667eea18' : 'transparent', borderLeft: `3px solid ${i === cmdPalette.selectedIdx ? '#667eea' : 'transparent'}` }}>
                          <code style={{ fontSize: 12, color: '#90cdf4', minWidth: 100, flexShrink: 0 }}>{c.cmd}</code>
                          <span style={{ fontSize: 11, color: '#718096', flex: 1 }}>{c.desc}</span>
                          <code style={{ fontSize: 10, color: '#4a5568', flexShrink: 0 }}>{c.usage}</code>
                        </div>
                      ))}
                    </div>
                  ) : null;
                })()}
                <textarea
                  ref={inputRef}
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder={mode === 'agent' ? 'Message Nirvana… or /help for commands' : 'Enter your prompt…'}
                  rows={2}
                  style={{
                    flex: 1, padding: '10px 12px', borderRadius: cmdPalette.open ? '0 0 10px 10px' : 10, background: '#1a2035',
                    border: `1px solid ${cmdPalette.open ? '#667eea55' : '#2d3748'}`, color: '#e2e8f0', fontSize: 13, resize: 'none',
                    fontFamily: 'inherit', outline: 'none',
                  }}
                />
                <button
                  onClick={() => handleSend()}
                  disabled={isLoading || !inputValue.trim()}
                  style={{
                    padding: '10px 16px', borderRadius: 10, border: 'none', cursor: 'pointer',
                    background: isLoading || !inputValue.trim() ? '#2d3748' : '#667eea',
                    color: '#fff', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600,
                    flexShrink: 0,
                  }}
                >
                  {isLoading ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={16} />}
                  Send
                </button>
              </div>
              <div style={{ fontSize: 10, color: '#718096', marginTop: 4 }}>
                Enter to send · Shift+Enter for new line · Tab to complete command · Template: {CHAT_TEMPLATES.find(t => t.id === chatTemplate)?.label}
              </div>
            </div>
          </div>
        ) : (
          /* PLAYGROUND VIEW */
          <div style={{ flex: 1, overflowY: 'auto', padding: 20, background: '#0f1724' }}>
            <div style={{ maxWidth: 900, margin: '0 auto' }}>
              {/* Playground header */}
              <div style={{ marginBottom: 20 }}>
                <h3 style={{ margin: '0 0 4px', color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Play size={18} color="#667eea" />
                  {PLAYGROUND_TABS.find(t => t.id === playTab)?.label} Testing
                </h3>
                <p style={{ margin: 0, fontSize: 12, color: '#718096' }}>
                  Run inference on {PLAYGROUND_TABS.find(t => t.id === playTab)?.label.toLowerCase()} inputs with full parameter control
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                {/* Input Panel */}
                <div style={{ ...panelStyle }}>
                  <div style={{ padding: '12px 16px', borderBottom: '1px solid #2d3748', background: '#1a2035' }}>
                    <h4 style={{ margin: 0, fontSize: 13, color: '#e2e8f0' }}>Input</h4>
                  </div>
                  <div style={{ padding: 16, flex: 1 }}>
                    {/* Text prompt */}
                    {(playTab === 'text' || playTab === 'imagegen') && (
                      <div style={{ marginBottom: 12 }}>
                        <label style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', display: 'block', marginBottom: 4 }}>Prompt</label>
                        <textarea
                          value={playPrompt}
                          onChange={e => setPlayPrompt(e.target.value)}
                          rows={6}
                          placeholder={playTab === 'imagegen' ? 'Describe the image...' : 'Enter your prompt...'}
                          style={{
                            width: '100%', boxSizing: 'border-box', padding: '8px 10px', borderRadius: 8,
                            background: '#141927', border: '1px solid #2d3748',
                            color: '#e2e8f0', fontSize: 13, resize: 'vertical', fontFamily: 'inherit',
                          }}
                        />
                      </div>
                    )}

                    {/* File uploads */}
                    {(playTab === 'classify' || playTab === 'detect' || playTab === 'audio' || playTab === 'video') && (
                      <div>
                        <label style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', display: 'block', marginBottom: 4 }}>
                          {playTab === 'classify' || playTab === 'detect' ? 'Image' : playTab === 'audio' ? 'Audio File' : 'Video File'}
                        </label>
                        <div
                          onClick={() => fileRef.current?.click()}
                          style={{
                            border: '2px dashed #2d3748', borderRadius: 8, padding: 20, textAlign: 'center',
                            cursor: 'pointer', color: '#718096', minHeight: 120, display: 'flex',
                            flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8,
                          }}
                        >
                          {playPreview && playTab === 'classify' ? (
                            <img src={playPreview} alt="Preview" style={{ maxHeight: 200, borderRadius: 6 }} />
                          ) : playPreview && playTab === 'detect' ? (
                            <img src={playPreview} alt="Preview" style={{ maxHeight: 200, borderRadius: 6 }} />
                          ) : playPreview && playTab === 'video' ? (
                            <video src={playPreview} controls style={{ maxWidth: '100%', borderRadius: 6 }} />
                          ) : playPreview && playTab === 'audio' ? (
                            <audio src={playPreview} controls style={{ width: '100%' }} />
                          ) : (
                            <>
                              <Upload size={32} />
                              <span style={{ fontSize: 12 }}>Click to upload {playTab} file</span>
                            </>
                          )}
                          <input
                            ref={fileRef}
                            type="file"
                            accept={playTab === 'audio' ? 'audio/*' : playTab === 'video' ? 'video/*' : 'image/*'}
                            onChange={e => {
                              const file = e.target.files[0];
                              if (file) setPlayPreview(URL.createObjectURL(file));
                            }}
                            style={{ display: 'none' }}
                          />
                        </div>
                      </div>
                    )}

                    <button
                      onClick={runPlayground}
                      disabled={playLoading}
                      style={{
                        marginTop: 12, width: '100%', padding: '10px', borderRadius: 8,
                        border: 'none', cursor: playLoading ? 'not-allowed' : 'pointer',
                        background: playLoading ? '#2d3748' : '#667eea',
                        color: '#fff', fontWeight: 700, fontSize: 13,
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                      }}
                    >
                      {playLoading
                        ? <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Running...</>
                        : <><Play size={16} /> Run Inference</>}
                    </button>

                    {playError && (
                      <div style={{ marginTop: 8, padding: '6px 10px', borderRadius: 6, background: '#fc818122', border: '1px solid #fc818144', color: '#fc8181', fontSize: 12 }}>
                        {playError}
                      </div>
                    )}
                  </div>
                </div>

                {/* Results Panel */}
                <div style={{ ...panelStyle }}>
                  <div style={{ padding: '12px 16px', borderBottom: '1px solid #2d3748', background: '#1a2035' }}>
                    <h4 style={{ margin: 0, fontSize: 13, color: '#e2e8f0' }}>Output</h4>
                  </div>
                  <div style={{ padding: 16, flex: 1 }}>
                    {!playResult && !playLoading && (
                      <div style={{ textAlign: 'center', padding: 40, color: '#718096' }}>
                        <BarChart2 size={32} style={{ marginBottom: 8 }} />
                        <div style={{ fontSize: 12 }}>Results will appear here</div>
                      </div>
                    )}
                    {playLoading && (
                      <div style={{ textAlign: 'center', padding: 40, color: '#718096' }}>
                        <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', marginBottom: 8 }} color="#667eea" />
                        <div style={{ fontSize: 12 }}>Running inference...</div>
                      </div>
                    )}
                    {playResult && (
                      <div>
                        {/* Text generation result */}
                        {(playTab === 'text') && (
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', marginBottom: 6 }}>Generated Text</div>
                            <div style={{
                              padding: '10px 12px', borderRadius: 8, background: '#1a2035',
                              border: '1px solid #2d3748', fontSize: 13, color: '#e2e8f0',
                              whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto',
                            }}>
                              {playResult.text || playResult.generated_text || playResult.response || JSON.stringify(playResult, null, 2)}
                            </div>
                            {playResult.tokens_generated && (
                              <div style={{ marginTop: 8, fontSize: 11, color: '#718096' }}>
                                Tokens: {playResult.tokens_generated}
                              </div>
                            )}
                          </div>
                        )}
                        {/* Classification result */}
                        {playTab === 'classify' && playResult.predictions && (
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: '#a0aec0', marginBottom: 6 }}>Predictions</div>
                            {playResult.predictions.map((p, i) => (
                              <div key={i} style={{ marginBottom: 8 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                                  <span style={{ fontSize: 12, color: '#e2e8f0' }}>{p.label || p.class}</span>
                                  <span style={{ fontSize: 12, color: '#90cdf4', fontWeight: 700 }}>{(p.confidence * 100).toFixed(1)}%</span>
                                </div>
                                <div style={{ height: 6, background: '#2d3748', borderRadius: 3 }}>
                                  <div style={{ height: '100%', width: `${p.confidence * 100}%`, background: '#667eea', borderRadius: 3 }} />
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Generic JSON fallback */}
                        {!['text', 'classify'].includes(playTab) && (
                          <pre style={{ fontSize: 11, color: '#e2e8f0', whiteSpace: 'pre-wrap', overflowY: 'auto', maxHeight: 300 }}>
                            {JSON.stringify(playResult, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
