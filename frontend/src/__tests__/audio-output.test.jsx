import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const audioMocks = vi.hoisted(() => ({
    listManagedAudioProfiles: vi.fn(() => ({ profiles: [] })),
    createManagedAudioProfile: vi.fn(),
    updateManagedAudioProfile: vi.fn(),
    deleteManagedAudioProfile: vi.fn(),
    listManagedAudioEntities: vi.fn(),
    testManagedAudioProfile: vi.fn(),
    createAudioPairingChallenge: vi.fn(),
    claimAudioPairing: vi.fn(),
    listAudioEndpoints: vi.fn(),
    listAudioGroups: vi.fn(),
    createAudioGroup: vi.fn(),
    updateAudioGroup: vi.fn(),
    deleteAudioGroup: vi.fn(),
    routeAudio: vi.fn(),
    audioWebsocketUrl: vi.fn(() => 'ws://localhost/api/nirvana/audio/ws'),
}));

vi.mock('../api/client', () => audioMocks);

import AudioOutput from '../pages/AudioOutput';
import RemoteAudioPanel from '../components/RemoteAudioPanel';

class MockWebSocket {
    static instances = [];

    constructor(url) {
        this.url = url;
        this.readyState = MockWebSocket.CONNECTING;
        this.sent = [];
        MockWebSocket.instances.push(this);
        queueMicrotask(() => {
            this.readyState = MockWebSocket.OPEN;
            this.onopen?.();
        });
    }

    send(value) {
        this.sent.push(JSON.parse(value));
    }

    close() {
        this.readyState = MockWebSocket.CLOSED;
        this.onclose?.();
    }
}

MockWebSocket.CONNECTING = 0;
MockWebSocket.OPEN = 1;
MockWebSocket.CLOSED = 3;

describe('room audio output', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        const values = new Map();
        const storage = {
            clear: () => values.clear(),
            getItem: (key) => values.get(key) || null,
            setItem: (key, value) => values.set(key, String(value)),
            removeItem: (key) => values.delete(key),
        };
        Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
        MockWebSocket.instances = [];
        window.WebSocket = MockWebSocket;
        globalThis.WebSocket = MockWebSocket;
        window.speechSynthesis = {
            cancel: vi.fn(),
            speak: vi.fn(),
            getVoices: vi.fn(() => []),
        };
        window.SpeechSynthesisUtterance = function SpeechSynthesisUtterance(text) {
            this.text = text;
        };
    });

    it('registers a stable browser endpoint and acknowledges speech playback', async () => {
        const user = userEvent.setup();
        render(<AudioOutput />);

        await waitFor(() => expect(MockWebSocket.instances[0].sent[0].type).toBe('register'));
        await user.click(screen.getByRole('button', { name: /enable audio/i }));
        expect(screen.getByRole('button', { name: /audio enabled/i })).toBeDisabled();

        const socket = MockWebSocket.instances[0];
        socket.onmessage({ data: JSON.stringify({ type: 'error', error: 'Transient connection error' }) });
        socket.onmessage({ data: JSON.stringify({ type: 'registered', endpoint: { endpoint_id: 'browser-1' }, heartbeat_interval_seconds: 15 }) });
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        socket.onmessage({ data: JSON.stringify({ type: 'speak', message_id: 'audio-1', text: 'Welcome home' }) });
        expect(window.speechSynthesis.speak).toHaveBeenCalled();
        expect(socket.sent.map((item) => item.type)).toContain('playback_ack');
    });

    it('selects an online endpoint and dispatches a test phrase', async () => {
        const user = userEvent.setup();
        audioMocks.listAudioEndpoints.mockResolvedValue({
            endpoints: [{ endpoint_id: 'pc-1', name: 'Living room PC', endpoint_type: 'browser', online: true }],
        });
        audioMocks.listAudioGroups.mockResolvedValue({ groups: [] });
        audioMocks.routeAudio.mockResolvedValue({ target_count: 1, results: [{ status: 'delivered' }] });

        render(<RemoteAudioPanel />);

        expect(await screen.findByRole('option', { name: /Living room PC/i })).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /test speech/i }));
        await waitFor(() => expect(audioMocks.routeAudio).toHaveBeenCalledWith(expect.objectContaining({
            endpoint_id: 'pc-1',
            text: 'Hello from Nirvana.',
        })));
        expect(await screen.findByText(/Audio dispatched/i)).toBeInTheDocument();
    });
});
