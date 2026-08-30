import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const runtimeMocks = vi.hoisted(() => ({
    useAgentRuntime: vi.fn(),
}));

const chatPlaygroundApiMocks = vi.hoisted(() => ({
    getSystemInfo: vi.fn(),
    getFLMStatus: vi.fn(),
    listFLMModels: vi.fn(),
    serveFLMModel: vi.fn(),
    stopFLMServer: vi.fn(),
    checkFLMModel: vi.fn(),
    chatFLM: vi.fn(),
}));

vi.mock('../context/AgentRuntimeContext', () => runtimeMocks);
vi.mock('../components/AgentRuntimeSelector', () => ({ default: () => null }));
vi.mock('../api/client', () => ({
    API_BASE: '/api',
    ...chatPlaygroundApiMocks,
}));

import { useChat } from '../hooks/useChat';
import ChatPlayground from '../pages/ChatPlayground';

function ChatHarness({ selectedModel = null, runtimeId }) {
    const { sendMessage } = useChat({ selectedModel, runtimeId });
    return <button onClick={() => sendMessage('hello')}>Send test message</button>;
}

function jsonResponse(data = {}) {
    return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => data,
    };
}

function responseFor(url) {
    if (url.endsWith('/agent/status')) {
        return jsonResponse({ is_downloaded: true, is_running: true });
    }
    if (url.endsWith('/models')) {
        return jsonResponse([]);
    }
    if (url.endsWith('/models/staff-picks')) {
        return jsonResponse({ models: [] });
    }
    if (url.endsWith('/agent/chat')) {
        return jsonResponse({ response: 'agent response' });
    }
    if (url.endsWith('/inference/generate-text')) {
        return jsonResponse({ text: 'native response' });
    }
    return jsonResponse({});
}

describe('universal runtime request boundaries', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        window.localStorage.clear();
        global.fetch.mockImplementation((url) => Promise.resolve(responseFor(url)));
        runtimeMocks.useAgentRuntime.mockReturnValue({
            runtimeIdForRequests: undefined,
            selectedRuntime: null,
        });
        chatPlaygroundApiMocks.getSystemInfo.mockResolvedValue({});
        chatPlaygroundApiMocks.getFLMStatus.mockResolvedValue({ available: false, server: {} });
        chatPlaygroundApiMocks.listFLMModels.mockResolvedValue({ local: [] });
        chatPlaygroundApiMocks.serveFLMModel.mockResolvedValue({});
        chatPlaygroundApiMocks.stopFLMServer.mockResolvedValue({});
        chatPlaygroundApiMocks.checkFLMModel.mockResolvedValue({ available: true });
        chatPlaygroundApiMocks.chatFLM.mockImplementation(async (...args) => {
            args[4]?.('fastflow response');
        });
    });

    it.each([undefined, 'nirvana-default'])('omits %s from default Nirvana chat requests', async (runtimeId) => {
        const user = userEvent.setup();
        render(<ChatHarness runtimeId={runtimeId} />);

        await user.click(screen.getByRole('button', { name: /send test message/i }));
        await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/api/agent/chat', expect.any(Object)));

        const request = global.fetch.mock.calls.find(([url]) => url === '/api/agent/chat');
        const body = JSON.parse(request[1].body);
        expect(body).not.toHaveProperty('runtime_id');
    });

    it('adds a selected non-default runtime only to agent chat requests', async () => {
        const user = userEvent.setup();
        render(<ChatHarness runtimeId="openai-compatible:selected" />);

        await user.click(screen.getByRole('button', { name: /send test message/i }));
        await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/api/agent/chat', expect.any(Object)));

        const request = global.fetch.mock.calls.find(([url]) => url === '/api/agent/chat');
        expect(JSON.parse(request[1].body)).toMatchObject({ runtime_id: 'openai-compatible:selected' });
    });

    it('does not pass a universal runtime ID to direct selected-model chat', async () => {
        const user = userEvent.setup();
        render(
            <ChatHarness
                runtimeId="openai-compatible:selected"
                selectedModel={{ id: 'local-gguf', format: 'gguf', framework: 'llama.cpp', display_name: 'Local GGUF' }}
            />,
        );

        await user.click(screen.getByRole('button', { name: /send test message/i }));
        await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/api/models/local-gguf/chat', expect.any(Object)));

        const request = global.fetch.mock.calls.find(([url]) => url === '/api/models/local-gguf/chat');
        expect(JSON.parse(request[1].body)).not.toHaveProperty('runtime_id');
    });

    it('keeps ChatPlayground agent mode runtime-aware', async () => {
        const user = userEvent.setup();
        runtimeMocks.useAgentRuntime.mockReturnValue({
            runtimeIdForRequests: 'ollama-local',
            selectedRuntime: { runtime_id: 'ollama-local', display_name: 'Ollama (Local)' },
        });
        render(<ChatPlayground defaultMode="agent" />);

        const input = await screen.findByPlaceholderText(/Message Nirvana/i);
        await user.type(input, 'hello agent');
        await user.click(screen.getByRole('button', { name: /^send$/i }));
        await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/api/agent/chat', expect.any(Object)));

        const request = global.fetch.mock.calls.find(([url]) => url === '/api/agent/chat');
        expect(JSON.parse(request[1].body)).toMatchObject({ runtime_id: 'ollama-local' });
    });

    it('keeps ChatPlayground native inference isolated from universal runtime selection', async () => {
        const user = userEvent.setup();
        runtimeMocks.useAgentRuntime.mockReturnValue({
            runtimeIdForRequests: 'ollama-local',
            selectedRuntime: { runtime_id: 'ollama-local' },
        });
        render(<ChatPlayground defaultMode="direct" />);

        await user.type(await screen.findByPlaceholderText(/Model URL\/ID\/tag or local path/i), 'local-model');
        await user.type(screen.getByPlaceholderText(/Enter your prompt/i), 'hello native');
        await user.click(screen.getByRole('button', { name: /^send$/i }));
        await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/api/inference/generate-text', expect.any(Object)));

        const request = global.fetch.mock.calls.find(([url]) => url === '/api/inference/generate-text');
        expect(request[1].body).toBeInstanceOf(FormData);
        expect(request[1].body.has('runtime_id')).toBe(false);
    });

    it('keeps ChatPlayground FastFlowLM inference provider-specific', async () => {
        const user = userEvent.setup();
        runtimeMocks.useAgentRuntime.mockReturnValue({
            runtimeIdForRequests: 'ollama-local',
            selectedRuntime: { runtime_id: 'ollama-local' },
        });
        chatPlaygroundApiMocks.getFLMStatus.mockResolvedValue({ available: true, server: {} });
        render(<ChatPlayground defaultMode="direct" />);

        const combos = await screen.findAllByRole('combobox');
        await user.selectOptions(combos[1], 'fastflowlm');
        await user.type(await screen.findByPlaceholderText(/Model URL\/ID\/tag or local path/i), 'qwen3.5');
        await user.type(screen.getByPlaceholderText(/Enter your prompt/i), 'hello NPU');
        await user.click(screen.getByRole('button', { name: /^send$/i }));

        await waitFor(() => expect(chatPlaygroundApiMocks.chatFLM).toHaveBeenCalled());
        const args = chatPlaygroundApiMocks.chatFLM.mock.calls[0];
        expect(args[1]).toBe('qwen3.5');
        expect(args).not.toContain('ollama-local');
    });
});
