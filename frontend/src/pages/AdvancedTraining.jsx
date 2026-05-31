import React, { useState } from 'react';
import { Zap, AlertCircle, CheckCircle } from 'lucide-react';
import EnhancedTrainingSetup from '../components/EnhancedTrainingSetup';
import OperationNotice from '../components/OperationNotice';
import ActivityLogCard from '../components/ActivityLogCard';

/**
 * Advanced Training Page
 * Unified training interface with dual-source model/dataset selection
 * and optional LoRA adapter integration from CivitAI
 */
export default function AdvancedTraining() {
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState(null);
  const [recentJob, setRecentJob] = useState(null);
  const [activityLog, setActivityLog] = useState([]);

  const addLog = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    setActivityLog((prev) => [...prev.slice(-49), `${timestamp} — ${message}`]);
  };

  const handleSubmitTraining = async (config) => {
    setSubmitting(true);
    addLog(`Starting training job: ${config.jobName || 'untitled'}`);

    try {
      const formData = new FormData();
      formData.append('model_id', config.modelId);
      formData.append('model_source', config.modelSource);
      formData.append('dataset', config.datasetName);
      formData.append('dataset_source', config.datasetSource);
      
      if (config.loraId) {
        formData.append('lora_id', config.loraId);
      }

      formData.append('epochs', config.epochs);
      formData.append('batch_size', config.batchSize);
      formData.append('learning_rate', config.learningRate);
      formData.append('use_lora', config.useLora);

      if (config.useLora) {
        formData.append('lora_r', config.loraR);
        formData.append('lora_alpha', config.loraAlpha);
      }

      formData.append('job_name', config.jobName);
      formData.append('description', config.description);

      const response = await fetch('/api/finetune/start', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      const result = await response.json();
      
      setRecentJob({
        id: result.job_id || Date.now(),
        name: config.jobName,
        model: config.modelId,
        dataset: config.datasetName,
        status: 'queued',
        timestamp: new Date().toLocaleString(),
      });

      setNotice({
        tone: 'success',
        title: '✨ Training Job Submitted',
        message: `Job "${config.jobName}" has been queued for training.`,
        details: `Model: ${config.modelId}, Dataset: ${config.datasetName}, Epochs: ${config.epochs}`,
      });

      addLog(`Training job submitted: ${config.jobName} (ID: ${result.job_id})`);
    } catch (error) {
      setNotice({
        tone: 'danger',
        title: '❌ Failed to Start Training',
        message: error.message,
        details: 'Check backend logs for more information.',
      });
      addLog(`Training submission failed: ${error.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      {/* Page Header */}
      <div className="section-header" style={{ marginBottom: '24px' }}>
        <h2
          className="page-title"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontSize: '24px',
          }}
        >
          <Zap size={28} style={{ color: '#667eea' }} /> Advanced Training
        </h2>
        <p className="text-secondary">
          Multi-source fine-tuning: HuggingFace + CivitAI models, datasets, and LoRA adapters
        </p>
      </div>

      {/* Notice */}
      {notice && (
        <div style={{ marginBottom: '24px' }}>
          <OperationNotice
            tone={notice.tone}
            title={notice.title}
            message={notice.message}
            details={notice.details}
          />
        </div>
      )}

      {/* Recent Job Card */}
      {recentJob && (
        <div
          style={{
            marginBottom: '24px',
            padding: '16px',
            background: '#f0f4ff',
            border: '1px solid #667eea',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <CheckCircle size={20} style={{ color: '#667eea', flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: '600', fontSize: '13px', color: '#333' }}>
              Job Submitted: {recentJob.name}
            </div>
            <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>
              ID: {recentJob.id} • Started: {recentJob.timestamp}
            </div>
          </div>
          <div
            style={{
              padding: '4px 12px',
              background: '#e0e8ff',
              borderRadius: '4px',
              fontSize: '11px',
              fontWeight: '600',
              color: '#667eea',
            }}
          >
            {recentJob.status}
          </div>
        </div>
      )}

      {/* Main Training Setup */}
      <div
        style={{
          padding: '24px',
          background: 'white',
          borderRadius: '8px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          marginBottom: '24px',
        }}
      >
        <EnhancedTrainingSetup
          onSubmit={handleSubmitTraining}
          isLoading={submitting}
        />
      </div>

      {/* Activity Log */}
      {activityLog.length > 0 && (
        <div
          style={{
            padding: '24px',
            background: 'white',
            borderRadius: '8px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          }}
        >
          <h3 style={{ margin: '0 0 16px 0', fontSize: '14px', fontWeight: '600' }}>
            Activity Log
          </h3>
          <ActivityLogCard entries={activityLog} />
        </div>
      )}

      {/* Help Section */}
      <div
        style={{
          marginTop: '24px',
          padding: '16px',
          background: '#fafafa',
          borderRadius: '8px',
          borderLeft: '3px solid #667eea',
        }}
      >
        <h4 style={{ margin: '0 0 12px 0', fontSize: '12px', fontWeight: '600', color: '#333' }}>
          💡 Quick Tips
        </h4>
        <ul
          style={{
            margin: 0,
            paddingLeft: '20px',
            fontSize: '12px',
            color: '#666',
            lineHeight: '1.6',
          }}
        >
          <li>
            <strong>Models:</strong> Browse 500+ models from HuggingFace Hub or CivitAI
          </li>
          <li>
            <strong>Datasets:</strong> Upload local JSONL files or use HuggingFace datasets
          </li>
          <li>
            <strong>LoRA:</strong> Optional CivitAI adapters enhance base model training
          </li>
          <li>
            <strong>Parameters:</strong> Start with Epochs=3, Batch=4, LR=2e-4 for stable training
          </li>
          <li>
            <strong>LoRA Config:</strong> r=16, α=32 is a good default; increase for harder tasks
          </li>
        </ul>
      </div>
    </div>
  );
}
