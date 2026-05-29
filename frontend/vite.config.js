import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');
    const backendPort = env.VITE_BACKEND_PORT || '8010';
    const backendOrigin = (env.VITE_BACKEND_ORIGIN || `http://127.0.0.1:${backendPort}`).replace(/\/$/, '');
    const backendWsOrigin = backendOrigin.replace(/^http/i, 'ws');

    return {
        plugins: [react()],
        test: {
            environment: 'jsdom',
            setupFiles: './src/test/setup.js',
        },
        server: {
            port: 5173,
            proxy: {
                '/api': {
                    target: backendOrigin,
                    changeOrigin: true,
                    ws: true,
                },
                '/ws': {
                    target: backendWsOrigin,
                    ws: true,
                },
                '/v1': {
                    target: backendOrigin,
                    changeOrigin: true,
                },
            },
        },
    };
});
