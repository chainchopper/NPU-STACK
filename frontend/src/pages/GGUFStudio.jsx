import React, { useState, useEffect } from 'react';
import { Cpu, RefreshCw, Box, CheckCircle, AlertTriangle } from 'lucide-react';

export default function GGUFStudio() {
    const [status, setStatus] = useState(null);

    useEffect(() => {
        fetch('http://localhost:8000/api/gguf/pipeline/status')
            .then(res => res.json())
            .then(data => setStatus(data))
            .catch(err => console.error(err));
    }, []);

    return (
        <div className="page-container">
            <header className="page-header">
                <h1><Cpu className="icon-lg" /> GGUF Studio</h1>
                <p>Convert, quantize, and edit GGUF models for edge deployment.</p>
            </header>

            <div className="card">
                <h3>Pipeline Status</h3>
                {status ? (
                    <pre className="code-block" style={{ maxHeight: '400px', overflowY: 'auto' }}>{JSON.stringify(status, null, 2)}</pre>
                ) : (
                    <p>Loading...</p>
                )}
            </div>

            <div className="card">
                <h3>Tools</h3>
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                    <button className="btn btn-primary">Convert HF to GGUF</button>
                    <button className="btn btn-outline">Quantize Model</button>
                    <button className="btn btn-outline">Merge LoRA</button>
                    <button className="btn btn-outline">Split/Join</button>
                </div>
                <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
                    Interactive UI components for pipeline actions are under development. Use the API endpoints directly for full functionality.
                </p>
            </div>
        </div>
    );
}
