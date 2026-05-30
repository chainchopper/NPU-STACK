import React, { useState, useEffect, useRef } from "react";
import { MessageSquare, X, Send, User, Settings, Database, Play, Loader2 } from "lucide-react";
import { diagnoseBackendError } from "../api/client";
import AgentVisual from "./AgentVisual";
import ActivityLogCard from "./ActivityLogCard";
import OperationNotice from "./OperationNotice";

export default function SystemAgent() {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState([
        {
            role: "assistant",
            content: "Hello! I am the NPU-STACK Orchestrator Agent. I can help you compile models, run benchmarks, or explain the AI Factory pipeline. How can I assist you today?",
        },
    ]);
    const [inputValue, setInputValue] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [agentStatus, setAgentStatus] = useState({
        is_downloaded: false,
        is_running: false,
        dataset_ready: false,
        download_in_progress: false,
    });
    const [notice, setNotice] = useState(null);
    const [activityLog, setActivityLog] = useState([]);

    const messagesEndRef = useRef(null);

    const addLog = (line) => {
        const timestamp = new Date().toLocaleTimeString();
        setActivityLog((prev) => [...prev.slice(-39), `${timestamp} — ${line}`]);
    };

    const parseErrorMessage = async (res, fallback) => {
        try {
            const data = await res.json();
            return data?.detail || data?.message || fallback;
        } catch {
            return fallback;
        }
    };

    useEffect(() => {
        checkAgentStatus();
    }, [isOpen]);

    // Poll status while a download is in progress so the UI updates automatically
    useEffect(() => {
        if (!agentStatus.download_in_progress) return;
        const id = setInterval(checkAgentStatus, 5000); // eslint-disable-line react-hooks/exhaustive-deps
        return () => clearInterval(id);
    }, [agentStatus.download_in_progress]); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const checkAgentStatus = async () => {
        try {
            const res = await fetch("/api/agent/status");
            if (!res.ok) {
                throw new Error(await parseErrorMessage(res, "Failed to get agent status."));
            }
            const data = await res.json();
            setAgentStatus(data);
        } catch (err) {
            const message = diagnoseBackendError(err, "Agent status");
            setNotice({ tone: "warning", title: "Agent status unavailable", message, details: err?.message || null });
            addLog(`Status check failed: ${message}`);
        }
    };

    const initAgent = async () => {
        try {
            const res = await fetch("/api/agent/init", { method: "POST" });
            if (!res.ok) {
                throw new Error(await parseErrorMessage(res, "Failed to initialize agent."));
            }
            setNotice({ tone: "info", title: "Agent download started", message: "Downloading Phi-3-mini GGUF in the background." });
            addLog("Agent initialization started");
            setTimeout(checkAgentStatus, 3000);
        } catch (err) {
            const message = diagnoseBackendError(err, "Agent initialization");
            setNotice({ tone: "danger", title: "Agent initialization failed", message, details: err?.message || null });
            addLog(`Init failed: ${message}`);
        }
    };

    const startAgent = async () => {
        try {
            const res = await fetch("/api/agent/start", { method: "POST" });
            if (!res.ok) {
                throw new Error(await parseErrorMessage(res, "Failed to start agent."));
            }
            setNotice({ tone: "success", title: "Agent engine started", message: "Phi-3-mini service is now coming online." });
            addLog("Agent engine start requested");
            setTimeout(checkAgentStatus, 2000);
        } catch (err) {
            const message = diagnoseBackendError(err, "Agent start");
            setNotice({ tone: "danger", title: "Agent start failed", message, details: err?.message || null });
            addLog(`Start failed: ${message}`);
        }
    };

    const generateDataset = async () => {
        try {
            const res = await fetch("/api/agent/generate-dataset", { method: "POST" });
            if (!res.ok) {
                throw new Error(await parseErrorMessage(res, "Failed to generate dataset."));
            }
            setNotice({ tone: "success", title: "Dataset generation started", message: "Knowledge dataset generation is in progress." });
            addLog("Knowledge dataset generation requested");
            setTimeout(checkAgentStatus, 1000);
        } catch (err) {
            const message = diagnoseBackendError(err, "Dataset generation");
            setNotice({ tone: "danger", title: "Dataset generation failed", message, details: err?.message || null });
            addLog(`Dataset generation failed: ${message}`);
        }
    };

    const fineTuneAgent = async () => {
        try {
            const gRes = await fetch("/api/models");
            if (!gRes.ok) {
                throw new Error(await parseErrorMessage(gRes, "Failed to load models for fine-tuning."));
            }
            const gData = await gRes.json();
            const agentModel = gData.find(m => m.name === "NPU-STACK System Agent (Phi-3-mini)");

            if (!agentModel) {
                const message = "Agent model not found in registry. Download it first.";
                setNotice({ tone: "warning", title: "Fine-tuning unavailable", message });
                addLog(message);
                return;
            }

            const formData = new FormData();
            formData.append("model_id", agentModel.id);
            formData.append("dataset", "npu_stack_knowledge.jsonl");
            formData.append("epochs", "3");

            const fRes = await fetch("/api/finetune/start", {
                method: "POST",
                body: formData,
            });
            if (!fRes.ok) {
                throw new Error(await parseErrorMessage(fRes, "Failed to start fine-tuning."));
            }
            const fData = await fRes.json();
            setNotice({ tone: "success", title: "Fine-tuning started", message: `Job ID: ${fData.job_id}` });
            addLog(`Fine-tuning started (job ${fData.job_id})`);
        } catch (err) {
            const message = diagnoseBackendError(err, "Fine-tuning");
            setNotice({ tone: "danger", title: "Fine-tuning failed", message, details: err?.message || null });
            addLog(`Fine-tuning failed: ${message}`);
        }
    };

    const sendMessage = async () => {
        if (!inputValue.trim() || isLoading) return;

        const userMessage = { role: "user", content: inputValue };
        setMessages((prev) => [...prev, userMessage]);
        setInputValue("");
        setIsLoading(true);

        try {
            // Use the backend's /api/agent/chat which routes through gguf_service
            const res = await fetch("/api/agent/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    messages: [...messages, userMessage],
                    temperature: 0.7,
                    max_tokens: 512,
                }),
            });

            const data = await res.json();
            if (data.choices && data.choices.length > 0) {
                setMessages((prev) => [
                    ...prev,
                    { role: "assistant", content: data.choices[0].message.content },
                ]);
                addLog("Agent response received");
            } else {
                throw new Error("Invalid response format");
            }
        } catch (err) {
            const message = diagnoseBackendError(err, "Agent chat");
            setNotice({ tone: "warning", title: "Chat request failed", message, details: err?.message || null });
            addLog(`Chat failed: ${message}`);
            setMessages((prev) => [
                ...prev,
                {
                    role: "assistant",
                    content: "Sorry, I encountered an error. Make sure the agent model is loaded via the Start Agent Engine button.",
                },
            ]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <>
            <button
                onClick={() => setIsOpen(true)}
                className="fixed bottom-6 right-6 p-3 rounded-full bg-primary/20 backdrop-blur-md border border-primary/30 text-white shadow-2xl hover:shadow-primary/50 transition-all z-50 flex items-center justify-center hover:scale-110 active:scale-95 group"
            >
                <MessageSquare size={28} />
                <div className="absolute -top-1 -right-1 w-4 h-4 bg-primary rounded-full border-2 border-[#060a14] animate-pulse"></div>
            </button>

            {isOpen && (
                <div className="fixed bottom-24 right-6 w-[400px] h-[600px] bg-[#1a1c23] border border-border shadow-2xl rounded-xl flex flex-col z-50 overflow-hidden transform transition-all">
                    {/* Header */}
                    <div className="p-4 border-b border-border flex justify-between items-center bg-[#1a1c23]">
                        <div className="flex items-center gap-3">
                            <div>
                                <h3 className="font-semibold text-white">NPU-STACK Agent</h3>
                                <p className="text-xs text-secondary-text">
                                    {agentStatus.is_running ? "🟢 Online (Phi-3-mini)" : "🔴 Offline"}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {agentStatus.is_running && agentStatus.dataset_ready && (
                                <button
                                    onClick={fineTuneAgent}
                                    className="text-xs bg-primary/20 text-primary px-2 py-1 rounded hover:bg-primary/30 transition-colors flex items-center gap-1"
                                    title="Self-Train Agent on NPU-STACK Knowledge"
                                >
                                    <Settings size={12} /> Fine-Tune
                                </button>
                            )}
                            <button onClick={() => setIsOpen(false)} className="text-secondary-text hover:text-white p-1">
                                <X size={20} />
                            </button>
                        </div>
                    </div>

                    <div className="px-4 pt-3">
                        <OperationNotice
                            tone={notice?.tone || "info"}
                            title={notice?.title}
                            message={notice?.message}
                            details={notice?.details}
                            style={{ marginBottom: 0 }}
                        />
                    </div>

                    {!agentStatus.is_running ? (
                        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
                            <AgentVisual size={80} status="offline" />
                            <h4 className="text-lg font-medium text-white mb-2">Agent is Offline</h4>
                            <p className="text-sm text-secondary-text mb-6">
                                The NPU-STACK local orchestrator model is not currently running.
                            </p>

                            {agentStatus.download_in_progress ? (
                                <div className="w-full flex flex-col items-center gap-3 mb-2">
                                    <div className="flex items-center gap-2 text-primary text-sm font-medium">
                                        <Loader2 size={16} className="animate-spin" /> Downloading Phi-3-mini GGUF...
                                    </div>
                                    <p className="text-xs text-secondary-text">This may take several minutes. Status refreshes automatically.</p>
                                </div>
                            ) : !agentStatus.is_downloaded ? (
                                <button
                                    onClick={initAgent}
                                    className="btn btn-primary w-full flex items-center justify-center gap-2 mb-2"
                                >
                                    <Database size={16} /> Download Phi-3-mini GGUF
                                </button>
                            ) : (
                                <button
                                    onClick={startAgent}
                                    className="btn btn-primary w-full flex items-center justify-center gap-2 mb-2"
                                >
                                    <Play size={16} /> Start Agent Engine
                                </button>
                            )}

                            {!agentStatus.dataset_ready && (
                                <button
                                    onClick={generateDataset}
                                    className="btn btn-secondary w-full flex items-center justify-center gap-2"
                                >
                                    <Settings size={16} /> Generate Knowledge Dataset
                                </button>
                            )}

                            <ActivityLogCard
                                title="Agent Activity"
                                lines={activityLog}
                                emptyMessage="No agent actions recorded yet."
                                onClear={() => setActivityLog([])}
                                style={{ marginTop: 12, width: '100%' }}
                            />
                        </div>
                    ) : (
                        <>
                            {/* Chat Area */}
                            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                                {messages.map((msg, i) => (
                                    <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                                        <div
                                            className={`max-w-[85%] rounded-lg p-3 ${msg.role === "user"
                                                ? "bg-primary text-white"
                                                : "bg-[#23252f] text-secondary-text border border-border"
                                                }`}
                                        >
                                            <div className="flex items-center gap-2 mb-1">
                                                {msg.role === "user" ? <User size={14} /> : <AgentVisual size={16} status={agentStatus.is_running ? "online" : "offline"} />}
                                                <span className="text-xs opacity-75">{msg.role === "user" ? "You" : "Agent"}</span>
                                            </div>
                                            <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                                        </div>
                                    </div>
                                ))}
                                {isLoading && (
                                    <div className="flex justify-start">
                                        <div className="bg-[#23252f] border border-border rounded-lg p-3 text-secondary-text flex items-center gap-2">
                                            <div className="w-2 h-2 bg-primary rounded-full animate-bounce"></div>
                                            <div className="w-2 h-2 bg-primary rounded-full animate-bounce delay-75"></div>
                                            <div className="w-2 h-2 bg-primary rounded-full animate-bounce delay-150"></div>
                                        </div>
                                    </div>
                                )}
                                <div ref={messagesEndRef} />
                            </div>

                            {/* Input Area */}
                            <div className="p-4 border-t border-border bg-[#1a1c23]">
                                <div className="flex items-center gap-2">
                                    <input
                                        type="text"
                                        value={inputValue}
                                        onChange={(e) => setInputValue(e.target.value)}
                                        onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                                        placeholder="Ask the orchestrator..."
                                        className="input flex-1"
                                        disabled={isLoading}
                                    />
                                    <button
                                        onClick={sendMessage}
                                        disabled={!inputValue.trim() || isLoading}
                                        className="p-3 bg-primary text-white rounded-lg hover:bg-primary-hover disabled:opacity-50 transition-colors"
                                    >
                                        <Send size={18} />
                                    </button>
                                </div>
                                <ActivityLogCard
                                    title="Agent Activity"
                                    lines={activityLog}
                                    emptyMessage="No agent actions recorded yet."
                                    onClear={() => setActivityLog([])}
                                    style={{ marginTop: 12 }}
                                />
                            </div>
                        </>
                    )}
                </div>
            )}
        </>
    );
}
