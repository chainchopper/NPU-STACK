import React, { useState, useEffect } from 'react';
import { CloudUpload, Share2, Tag } from 'lucide-react';

export default function HubPublisher() {
    const [status, setStatus] = useState(null);

    useEffect(() => {
        fetch('http://localhost:8000/api/finetune/status')
            .then(res => res.json())
            .then(data => setStatus(data))
            .catch(err => console.error(err));
    }, []);

    return (
        <div className="page-container">
            <header className="page-header">
                <h1><CloudUpload className="icon-lg" /> HuggingFace Publisher</h1>
                <p>Fine-tune with Unsloth and publish models, datasets, and GGUF files to the Hub.</p>
            </header>

            <div className="card">
                <h3>Ecosystem Status</h3>
                {status ? (
                    <pre className="code-block" style={{ maxHeight: '400px', overflowY: 'auto' }}>{JSON.stringify(status, null, 2)}</pre>
                ) : (
                    <p>Loading...</p>
                )}
            </div>

            <div className="card">
                <h3>Actions</h3>
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                    <button className="btn btn-primary">Start QLoRA Training</button>
                    <button className="btn btn-outline">Publish Model</button>
                    <button className="btn btn-outline">Upload GGUF</button>
                    <button className="btn btn-outline">Generate Model Card</button>
                </div>
                <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
                    Full interactive UI forms for training and publishing are coming soon. The backend APIs are fully operational.
                </p>
            </div>
        </div>
    );
}
