import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('../pages/Dashboard', () => ({ default: () => <div>Dashboard Page</div> }));
vi.mock('../pages/Models', () => ({ default: () => <div>Models Page</div> }));
vi.mock('../pages/Training', () => ({ default: () => <div>Training Page</div> }));
vi.mock('../pages/Conversion', () => ({ default: () => <div>Conversion Page</div> }));
vi.mock('../pages/Benchmark', () => ({ default: () => <div>Benchmark Page</div> }));
vi.mock('../pages/Playground', () => ({ default: () => <div>Playground Page</div> }));
vi.mock('../pages/ModelHub', () => ({ default: () => <div>Model Hub Page</div> }));
vi.mock('../pages/Datasets', () => ({ default: () => <div>Datasets Page</div> }));
vi.mock('../pages/Serving', () => ({ default: () => <div>Serving Page</div> }));
vi.mock('../pages/FineTuning', () => ({ default: () => <div>Fine-Tuning Page</div> }));
vi.mock('../pages/Scanner', () => ({ default: () => <div>Scanner Page</div> }));
vi.mock('../pages/WebcamTest', () => ({ default: () => <div>Webcam Page</div> }));
vi.mock('../pages/DataIngestion', () => ({ default: () => <div>Data Ingestion Page</div> }));
vi.mock('../pages/GGUFStudio', () => ({ default: () => <div>GGUF Studio Page</div> }));
vi.mock('../pages/HubPublisher', () => ({ default: () => <div>HF Publisher Page</div> }));
vi.mock('../pages/FastFlowLM', () => ({ default: () => <div>FastFlowLM Page</div> }));
vi.mock('../pages/EdgeFleet', () => ({ default: () => <div>Edge Fleet Page</div> }));
vi.mock('../pages/AudioOutput', () => ({ default: () => <div>Audio Output Page</div> }));

import App from '../App';

describe('App navigation smoke', () => {
    beforeEach(() => {
        window.history.pushState({}, '', '/');
    });

    it('navigates between sidebar routes without crashing', async () => {
        const user = userEvent.setup();
        render(<App />);

        expect(await screen.findByText('Dashboard Page')).toBeInTheDocument();

        await user.click(screen.getByRole('link', { name: /model hub/i }));
        expect(await screen.findByText('Model Hub Page')).toBeInTheDocument();

        await user.click(screen.getByRole('link', { name: /edge fleet/i }));
        expect(await screen.findByText('Edge Fleet Page')).toBeInTheDocument();

        await user.click(screen.getByRole('link', { name: /audio output/i }));
        expect(await screen.findByText('Audio Output Page')).toBeInTheDocument();
    });
});
