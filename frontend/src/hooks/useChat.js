import { useState, useCallback, useRef } from 'react';
import { API_BASE } from '../api/client';

/**
 * Hook for managing chat state and communication with backend.
 * Current /api/agent/chat endpoint is text-only, so image attachments are
 * preserved in UI and summarized in text for backend compatibility.
 */
export function useChat({ selectedModel = null } = {}) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const threadIdRef = useRef(`thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);

  const sendMessage = useCallback(
    async (userMessage, images = []) => {
      if (!userMessage?.trim() && images.length === 0) return;

      setError(null);

      const optimisticUserMsg = {
        id: `user_${Date.now()}`,
        role: 'user',
        content: userMessage,
        images: images.length > 0 ? images : undefined,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, optimisticUserMsg]);
      setIsLoading(true);

      try {
        const backendText = (text, imgCount = 0) => {
          const t = (text || '').trim();
          if (imgCount <= 0) return t;
          return `${t}${t ? '\n\n' : ''}[Attached images: ${imgCount}. Use Model Test panel for image inference.]`;
        };

        const backendMessages = messages
          .filter((m) => m.role === 'user' || m.role === 'assistant')
          .map((m) => ({ role: m.role, content: backendText(m.content, m.images?.length || 0) }));

        backendMessages.push({
          role: 'user',
          content: backendText(userMessage, images.length),
        });

        let endpoint = `${API_BASE}/agent/chat`;
        if (selectedModel) {
          const isChatCapableModel =
            selectedModel.format === 'gguf' || selectedModel.framework === 'llama.cpp';

          if (!isChatCapableModel) {
            throw new Error(
              `Selected model (${selectedModel.display_name || selectedModel.name}) is ${selectedModel.framework}/${selectedModel.format}. ` +
              'Direct chat is currently available for GGUF/llama.cpp models. Use Model Test for ONNX/PyTorch models.'
            );
          }

          endpoint = `${API_BASE}/models/${selectedModel.id}/chat`;
        }

        const body = {
          messages: backendMessages,
          use_fleet_tools: true,
          temperature: 0.7,
          max_tokens: 512,
        };

        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          const errData = await response.json();

          if (
            endpoint.endsWith('/agent/chat') &&
            response.status === 400 &&
            (errData?.detail || '').toLowerCase().includes('not loaded')
          ) {
            // Attempt to start/load the built-in system agent automatically
            await fetch(`${API_BASE}/agent/start`, { method: 'POST' });
            throw new Error('System agent was not loaded. I triggered startup — please retry your message in a few seconds.');
          }

          throw new Error(errData.detail || `Chat failed: ${response.statusText}`);
        }

        const data = await response.json();

        const assistantMsg = {
          id: `assistant_${Date.now()}`,
          role: 'assistant',
          content: data.response || data.message || data.text || 'No response',
          timestamp: new Date(),
          metadata: {
            reasoning: data.reasoning || null,
            toolCalls: data.tool_calls || [],
            fleetContext: data.fleet_context || null,
          },
        };

        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        setError(err.message);
        const errorMsg = {
          id: `error_${Date.now()}`,
          role: 'assistant',
          content: `Error: ${err.message}`,
          timestamp: new Date(),
          isError: true,
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsLoading(false);
      }
    },
    [messages, selectedModel]
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    threadIdRef.current = `thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearChat,
    threadId: threadIdRef.current,
  };
}
