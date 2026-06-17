import React, { lazy, Suspense, useState } from 'react';
import { GraduationCap, Zap, Wrench, CloudUpload } from 'lucide-react';

const BasicTraining = lazy(() => import('./Training'));
const AdvancedTraining = lazy(() => import('./AdvancedTraining'));
const FineTuning = lazy(() => import('./FineTuning'));
const HubPublisher = lazy(() => import('./HubPublisher'));

const TABS = [
  { id: 'basic', label: 'Basic Training', icon: GraduationCap, desc: 'Classic PyTorch training with CIFAR-10/MNIST' },
  { id: 'advanced', label: 'Advanced', icon: Zap, desc: 'Multi-source fine-tuning with LoRA adapters' },
  { id: 'finetune', label: 'Fine-Tuning', icon: Wrench, desc: 'Domain-specific model fine-tuning with dataset upload' },
  { id: 'publish', label: 'HF Publisher', icon: CloudUpload, desc: 'Publish models, GGUF files, & model cards to HuggingFace' },
];

export default function TrainingCenter() {
  const [activeTab, setActiveTab] = useState('basic');

  const renderTab = () => {
    switch (activeTab) {
      case 'basic': return <BasicTraining />;
      case 'advanced': return <AdvancedTraining />;
      case 'finetune': return <FineTuning />;
      case 'publish': return <HubPublisher />;
      default: return null;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, maxWidth: '100%' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-secondary)' }}>
        <h2 style={{ margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <GraduationCap size={22} color="#667eea" />
          Training Center
        </h2>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)' }}>
          Basic training · Advanced fine-tuning · LoRA adapters · HuggingFace publishing — unified workflow
        </p>
      </div>

      {/* Tab Bar */}
      <div style={{
        display: 'flex', gap: 0, borderBottom: '1px solid var(--border-color)',
        padding: '0 16px', background: 'var(--bg-card)', flexWrap: 'wrap',
      }}>
        {TABS.map(tab => (
          <button key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
              padding: '10px 18px', border: 'none', borderBottom: activeTab === tab.id ? '2px solid #667eea' : '2px solid transparent',
              background: 'transparent', cursor: 'pointer',
              color: activeTab === tab.id ? '#667eea' : 'var(--text-muted)',
              fontSize: 12, fontWeight: 500, transition: 'color 0.15s',
              minWidth: 100,
            }}>
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={{ overflow: 'auto' }}>
        <Suspense fallback={<div className="loading-overlay"><div className="spinner"/><span>Loading...</span></div>}>
          {renderTab()}
        </Suspense>
      </div>
    </div>
  );
}
