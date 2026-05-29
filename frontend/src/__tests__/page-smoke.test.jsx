import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../components/SystemAgent', () => ({ default: () => <div data-testid="system-agent" /> }));
vi.mock('../components/ContextWizard', () => ({ default: () => <div data-testid="context-wizard" /> }));
vi.mock('../components/FolderBrowser', () => ({
    default: ({ open, title }) => open ? <div data-testid="folder-browser">{title}</div> : null,
}));

vi.mock('../api/client', async () => {
    const actual = await vi.importActual('../api/client');
    return {
        ...actual,
        getStatus: vi.fn(),
        getSystemInfo: vi.fn(),
        getFLMStatus: vi.fn(),
        listFLMModels: vi.fn(),
        pullFLMModel: vi.fn(),
        serveFLMModel: vi.fn(),
        stopFLMServer: vi.fn(),
        chatFLM: vi.fn(),
        scanDevices: vi.fn(),
        listDevices: vi.fn(),
        listPreparedBundles: vi.fn(),
        updateDevice: vi.fn(),
        removeDevice: vi.fn(),
        pairDevice: vi.fn(),
        unpairDevice: vi.fn(),
        prepareDevice: vi.fn(),
        installPreparedBundle: vi.fn(),
        detectDeviceChip: vi.fn(),
        espDetect: vi.fn(),
        espBackup: vi.fn(),
        espFlash: vi.fn(),
        rp2040Detect: vi.fn(),
        listBackups: vi.fn(),
    };
});

import Dashboard from '../pages/Dashboard';
import Serving from '../pages/Serving';
import FineTuning from '../pages/FineTuning';
import FastFlowLM from '../pages/FastFlowLM';
import EdgeFleet from '../pages/EdgeFleet';
import ModelHub from '../pages/ModelHub';
import DataIngestion from '../pages/DataIngestion';
import {
    getStatus,
    getSystemInfo,
    getFLMStatus,
    inferBackendOrigin,
    listFLMModels,
    listDevices,
    listBackups,
    listPreparedBundles,
} from '../api/client';

function jsonResponse(data, ok = true) {
    return Promise.resolve({
        ok,
        status: ok ? 200 : 500,
        json: async () => data,
    });
}

function mockFetchRoutes(routes) {
    fetch.mockImplementation((input) => {
        const url = String(input);
        const matched = Object.entries(routes).find(([fragment]) => url.includes(fragment));
        if (!matched) {
            return Promise.reject(new Error(`Unhandled fetch in test: ${url}`));
        }
        const [, payload] = matched;
        return jsonResponse(payload.data, payload.ok ?? true);
    });
}

describe('Frontend page smoke coverage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        localStorage.clear();
        fetch.mockReset();
        localStorage.setItem('npu-wizard-dismissed', 'true');
    });

    it('renders Dashboard with empty-state hardware data', async () => {
        getStatus.mockResolvedValue({ models: 0, training_jobs: 0, running_jobs: 0, benchmarks: 0 });
        getSystemInfo.mockResolvedValue({
            platform: 'Windows',
            processor: 'Test CPU',
            memory_available_gb: 16,
            memory_total_gb: 32,
            cpu_count_physical: 8,
            cpu_count: 16,
            gpus: [],
            capabilities: {
                cpu: { available: true, label: 'CPU' },
            },
        });

        render(<Dashboard />);

        expect(await screen.findByText('Models Registered')).toBeInTheDocument();
        expect(screen.getByText('No GPU Detected')).toBeInTheDocument();
        expect(screen.getByText('Hardware Compatibility')).toBeInTheDocument();
    });

    it('renders Serving empty states for no loaded or registered models', async () => {
        mockFetchRoutes({
            '/v1/models': { data: { object: 'list', data: [] } },
            '/v1/models/status': { data: { loaded_count: 0, models: [] } },
        });

        render(<Serving />);

        expect(await screen.findByText(/No models loaded/i)).toBeInTheDocument();
        expect(screen.getByText(/No models registered/i)).toBeInTheDocument();
        expect(screen.getByText(/Load a model and start chatting/i)).toBeInTheDocument();
    });

    it('renders FineTuning empty jobs state', async () => {
        mockFetchRoutes({
            '/api/models': { data: { models: [] } },
            '/api/datasets': { data: { datasets: [] } },
            '/api/finetune/jobs': { data: { jobs: [] } },
        });

        render(<FineTuning />);

        expect(await screen.findByText(/No fine-tuning jobs yet/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /start fine-tuning/i })).toBeDisabled();
    });

    it('renders FastFlowLM library and workspace inactive state', async () => {
        getFLMStatus.mockResolvedValue({
            installed: false,
            version: 'N/A',
            npu_ready: false,
            server: { running: false, model: null },
        });
        listFLMModels.mockResolvedValue({
            local: [],
            catalog: [
                { tag: 'llama3.2:1b', name: 'Llama 3.2 1B', family: 'Llama', size: '1B', context: '128k' },
            ],
        });

        const user = userEvent.setup();
        render(<FastFlowLM />);

        expect(await screen.findByText(/FastFlowLM Integration/i)).toBeInTheDocument();
        expect(screen.getByText(/Cloud Catalog/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /npu workspace/i }));
        expect(await screen.findByText(/Workspace Inactive/i)).toBeInTheDocument();
    });

    it('renders EdgeFleet with no discovered devices', async () => {
        listDevices.mockResolvedValue({ devices: [], count: 0, last_scan: null });
        listBackups.mockResolvedValue({ backups: [] });
        listPreparedBundles.mockResolvedValue({ bundles: [] });

        render(<EdgeFleet />);

        expect(await screen.findByText(/Registered Devices/i)).toBeInTheDocument();
        expect(screen.getByText(/No devices found/i)).toBeInTheDocument();
    });

    it('maps frontend dev origins to the backend origin for bundle provisioning', () => {
        expect(inferBackendOrigin('http://127.0.0.1:5174/edge-fleet')).toBe('http://127.0.0.1:8000');
        expect(inferBackendOrigin('http://127.0.0.1:5173/hub')).toBe('http://127.0.0.1:8000');
        expect(inferBackendOrigin('http://127.0.0.1:8000/edge-fleet')).toBe('http://127.0.0.1:8000');
    });

    it('renders ModelHub no-results state from search', async () => {
        mockFetchRoutes({
            '/api/huggingface/search': { data: { models: [] } },
        });

        render(<ModelHub />);

        expect(await screen.findByText(/No models found matching your query/i)).toBeInTheDocument();
    });

    it('renders DataIngestion base upload state and supported types', async () => {
        mockFetchRoutes({
            '/api/ingest/dataset-formats': { data: { formats: [{ id: 'raw_text', description: 'Raw Text' }] } },
            '/api/ingest/supported-types': { data: { types: [{ category: 'text', extensions: ['.txt', '.md'] }] } },
            '/api/ingest/uploads': { data: { files: [] } },
        });

        render(<DataIngestion />);

        expect(await screen.findByText(/Drop files here or click to upload/i)).toBeInTheDocument();
        expect(screen.getByText(/text: \.txt, \.md/i)).toBeInTheDocument();
        await waitFor(() => expect(fetch).toHaveBeenCalled());
    });
});
