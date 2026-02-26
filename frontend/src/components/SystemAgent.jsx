import React, { useState, useEffect, useRef } from "react";
import { MessageSquare, X, Send, Bot, User, Settings, Database, Play } from "lucide-react";

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
    });

    const messagesEndRef = useRef(null);

    useEffect(() => {
        checkAgentStatus();
    }, [isOpen]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const checkAgentStatus = async () => {
        try {
            const res = await fetch("http://localhost:8000/api/agent/status");
            const data = await res.json();
            setAgentStatus(data);
        } catch (err) {
            console.error("Failed to get agent status", err);
        }
    };

    const initAgent = async () => {
        try {
            await fetch("http://localhost:8000/api/agent/init", { method: "POST" });
            setTimeout(checkAgentStatus, 3000);
        } catch (err) {
            console.error(err);
        }
    };

    const startAgent = async () => {
        try {
            await fetch("http://localhost:8000/api/agent/start", { method: "POST" });
            setTimeout(checkAgentStatus, 2000);
        } catch (err) {
            console.error(err);
        }
    };

    const generateDataset = async () => {
        try {
            await fetch("http://localhost:8000/api/agent/generate-dataset", { method: "POST" });
            setTimeout(checkAgentStatus, 1000);
        } catch (err) {
            console.error(err);
        }
    };

    const fineTuneAgent = async () => {
        try {
            const gRes = await fetch("http://localhost:8000/api/models/all");
            const gData = await gRes.json();
            const agentModel = gData.models.find(m => m.name === "NPU-STACK System Agent (Phi-3-mini)");

            if (!agentModel) {
                alert("Agent model not found in database. Please download it first.");
                return;
            }

            const formData = new FormData();
            formData.append("model_id", agentModel.id);
            formData.append("dataset", "npu_stack_knowledge.jsonl");
            formData.append("epochs", "3");

            const fRes = await fetch("http://localhost:8000/api/finetune/start", {
                method: "POST",
                body: formData,
            });
            const fData = await fRes.json();
            alert(`Fine-tuning started! Job ID: ${fData.job_id}`);
        } catch (err) {
            console.error(err);
            alert("Failed to start fine-tuning.");
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
            const res = await fetch("http://localhost:8000/api/agent/chat", {
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
            } else {
                throw new Error("Invalid response format");
            }
        } catch (err) {
            console.error(err);
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
                className="fixed bottom-6 right-6 p-4 rounded-full bg-primary text-white shadow-lg hover:shadow-primary/50 transition-all z-50 flex items-center justify-center animate-pulse"
            >
                <Bot size={28} />
            </button>

            {isOpen && (
                <div className="fixed bottom-24 right-6 w-[400px] h-[600px] bg-[#1a1c23] border border-border shadow-2xl rounded-xl flex flex-col z-50 overflow-hidden transform transition-all">
                    {/* Header */}
                    <div className="p-4 border-b border-border flex justify-between items-center bg-[#1a1c23]">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-primary/20 text-primary rounded-lg">
                                <Bot size={20} />
                            </div>
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

                    {!agentStatus.is_running ? (
                        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
                            <Bot size={48} className="text-secondary-text mb-4" />
                            <h4 className="text-lg font-medium text-white mb-2">Agent is Offline</h4>
                            <p className="text-sm text-secondary-text mb-6">
                                The NPU-STACK local orchestrator model is not currently running.
                            </p>

                            {!agentStatus.is_downloaded ? (
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
                                                {msg.role === "user" ? <User size={14} /> : <Bot size={14} />}
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
                            </div>
                        </>
                    )}
                </div>
            )}
        </>
    );
}
