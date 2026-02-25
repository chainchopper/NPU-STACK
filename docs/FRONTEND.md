# Frontend Development Guide

## Overview

React 18 SPA built with Vite, featuring 5 pages connected to the backend via REST API and WebSocket.

## Running

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173 (proxies API to localhost:8000)
```

## Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | System overview, metrics, hardware detection |
| Models | `/models` | Upload, browse, download, delete models |
| Training | `/training` | Configure & launch training, live charts |
| Conversion | `/conversion` | Convert formats, quantize for NPU |
| Benchmark | `/benchmark` | Profile inference, compare devices |

## Key Dependencies

- `react-router-dom` — Client-side routing
- `recharts` — Charts for training loss and benchmark comparison
- `lucide-react` — Icons

## API Client

`src/api/client.js` wraps all backend API calls and provides a WebSocket connection manager for real-time training updates.

## Design System

`src/index.css` defines CSS custom properties for:
- Dark theme with neon accent colors
- Card, button, badge, form, and table components
- Responsive grid layouts
- JetBrains Mono for code/metrics, Inter for UI text

## Building for Production

```bash
npm run build
# Output: dist/ (served by Nginx in Docker)
```
