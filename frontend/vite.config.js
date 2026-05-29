import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    test: {
        environment: 'jsdom',
        setupFiles: './src/test/setup.js',
    },
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                ws: true,
            },
            '/ws': {
                target: 'ws://localhost:8000',
                ws: true,
            },
            '/v1': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },
});
