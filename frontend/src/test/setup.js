import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
    cleanup();
});

if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: vi.fn().mockImplementation((query) => ({
            matches: false,
            media: query,
            onchange: null,
            addListener: vi.fn(),
            removeListener: vi.fn(),
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
            dispatchEvent: vi.fn(),
        })),
    });
}

if (!window.ResizeObserver) {
    window.ResizeObserver = class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
    };
}

if (!navigator.clipboard) {
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
            writeText: vi.fn().mockResolvedValue(undefined),
        },
    });
}

if (!window.localStorage) {
    const values = new Map();
    Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: {
            clear: () => values.clear(),
            getItem: (key) => values.get(key) || null,
            setItem: (key, value) => values.set(key, String(value)),
            removeItem: (key) => values.delete(key),
        },
    });
}

if (!window.HTMLElement.prototype.scrollIntoView) {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
}

global.fetch = vi.fn();
