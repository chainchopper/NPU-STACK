import React, { useState } from 'react';
import { Zap, Play, Loader } from 'lucide-react';
import ModelSelector from './ModelSelector';
import DatasetSelector from './DatasetSelector';
import LoRASelector from './LoRASelector';

/**
 * Enhanced Training Setup Component
 * Unified interface for:
 * - Selecting base models (HF + CivitAI)
 * - Selecting training datasets (Local + HF)
 * - Optional LoRA adapter selection (CivitAI)
 * - Training hyperparameter configuration
 */
export const EnhancedTrainingSetup = ({ onSubmit, isLoading = false }) => {
  // Model selection
  const [selectedModel, setSelectedModel] = useState('');
  const [modelSource, setModelSource] = useState('huggingface');

  // Dataset selection
  const [selectedDataset, setSelectedDataset] = useState('');
  const [datasetSource, setDatasetSource] = useState('local');

  // LoRA selection (optional)
  const [selectedLora, setSelectedLora] = useState(null);

  // Hyperparameters
  const [epochs, setEpochs] = useState(3);
  const [batchSize, setBatchSize] = useState(4);
  const [lr, setLr] = useState(0.0002);
  const [useLora, setUseLora] = useState(true);
  const [loraR, setLoraR] = useState(16);
  const [loraAlpha, setLoraAlpha] = useState(32);

  // Job metadata
  const [jobName, setJobName] = useState('');
  const [description, setDescription] = useState('');

  // UI state
  const [expandedSection, setExpandedSection] = useState('model'); // 'model', 'dataset', 'lora', 'params', 'metadata'
  const [activeTab, setActiveTab] = useState('config'); // 'config', 'preview'

  const isComplete = selectedModel && selectedDataset && epochs && batchSize && lr;

  const handleSubmit = async () => {
    if (!isComplete) {
      alert('Please select a model and dataset');
      return;
    }

    await onSubmit({
      modelId: selectedModel,
      modelSource,
      datasetName: selectedDataset,
      datasetSource,
      loraId: selectedLora,
      epochs,
      batchSize,
      learningRate: lr,
      useLora,
      loraR,
      loraAlpha,
      jobName: jobName || `training_${Date.now()}`,
      description,
    });
  };

  const SectionHeader = ({ title, icon, section }) => (
    <button
      onClick={() => setExpandedSection(expandedSection === section ? null : section)}
      style={{
        width: '100%',
        padding: '12px 16px',
        background: expandedSection === section ? '#f0f4ff' : '#f9f9f9',
        border: expandedSection === section ? '1px solid #667eea' : '1px solid #e0e0e0',
        borderRadius: '8px',
        textAlign: 'left',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontWeight: '600',
        fontSize: '13px',
        color: expandedSection === section ? '#667eea' : '#333',
        transition: 'all 0.2s ease',
      }}
    >
      <span>{icon}</span>
      <span>{title}</span>
      <span style={{ marginLeft: 'auto', fontSize: '11px', color: '#999' }}>
        {expandedSection === section ? '▼' : '▶'}
      </span>
    </button>
  );

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Zap size={20} style={{ color: '#667eea' }} />
          Advanced Training Setup
        </h2>
        <p style={{ margin: 0, fontSize: '13px', color: '#666' }}>
          Configure and launch fine-tuning jobs with models and datasets from multiple sources
        </p>
      </div>

      {/* Tab Navigation */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', borderBottom: '1px solid #e0e0e0' }}>
        <button
          onClick={() => setActiveTab('config')}
          style={{
            padding: '12px 16px',
            border: 'none',
            borderBottom: activeTab === 'config' ? '2px solid #667eea' : 'none',
            background: 'transparent',
            cursor: 'pointer',
            fontSize: '13px',
            fontWeight: activeTab === 'config' ? '600' : '400',
            color: activeTab === 'config' ? '#667eea' : '#666',
          }}
        >
          ⚙️ Configuration
        </button>
        <button
          onClick={() => setActiveTab('preview')}
          style={{
            padding: '12px 16px',
            border: 'none',
            borderBottom: activeTab === 'preview' ? '2px solid #667eea' : 'none',
            background: 'transparent',
            cursor: 'pointer',
            fontSize: '13px',
            fontWeight: activeTab === 'preview' ? '600' : '400',
            color: activeTab === 'preview' ? '#667eea' : '#666',
          }}
        >
          👁️ Preview
        </button>
      </div>

      {/* Configuration Tab */}
      {activeTab === 'config' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
          {/* Left Column: Selectors */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Model Selection */}
            <div>
              <SectionHeader title="Base Model Selection" icon="🤖" section="model" />
              {expandedSection === 'model' && (
                <div style={{ marginTop: '12px' }}>
                  <ModelSelector
                    value={selectedModel}
                    onChange={setSelectedModel}
                    selectedSource={modelSource}
                  />
                </div>
              )}
            </div>

            {/* Dataset Selection */}
            <div>
              <SectionHeader title="Training Dataset" icon="📚" section="dataset" />
              {expandedSection === 'dataset' && (
                <div style={{ marginTop: '12px' }}>
                  <DatasetSelector
                    value={selectedDataset}
                    onChange={setSelectedDataset}
                    selectedSource={datasetSource}
                  />
                </div>
              )}
            </div>

            {/* LoRA Selection */}
            <div>
              <SectionHeader title="Optional: LoRA Adapter" icon="🎨" section="lora" />
              {expandedSection === 'lora' && (
                <div style={{ marginTop: '12px' }}>
                  <LoRASelector
                    value={selectedLora}
                    onChange={setSelectedLora}
                    baseModelId={selectedModel}
                    showExternal={true}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Hyperparameters */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Hyperparameters Section */}
            <div>
              <SectionHeader title="Training Hyperparameters" icon="🔧" section="params" />
              {expandedSection === 'params' && (
                <div style={{ marginTop: '12px', padding: '16px', background: '#f9f9f9', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: '600', color: '#666', display: 'block', marginBottom: '6px' }}>
                      Epochs
                    </label>
                    <input
                      type="number"
                      value={epochs}
                      onChange={(e) => setEpochs(Number(e.target.value))}
                      min={1}
                      max={100}
                      style={{
                        width: '100%',
                        padding: '8px',
                        border: '1px solid #ddd',
                        borderRadius: '6px',
                        fontSize: '13px',
                      }}
                    />
                    <div style={{ fontSize: '11px', color: '#999', marginTop: '4px' }}>
                      Typically 3-10 for fine-tuning
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div>
                      <label style={{ fontSize: '12px', fontWeight: '600', color: '#666', display: 'block', marginBottom: '6px' }}>
                        Batch Size
                      </label>
                      <input
                        type="number"
                        value={batchSize}
                        onChange={(e) => setBatchSize(Number(e.target.value))}
                        min={1}
                        max={128}
                        style={{
                          width: '100%',
                          padding: '8px',
                          border: '1px solid #ddd',
                          borderRadius: '6px',
                          fontSize: '13px',
                        }}
                      />
                    </div>
                    <div>
                      <label style={{ fontSize: '12px', fontWeight: '600', color: '#666', display: 'block', marginBottom: '6px' }}>
                        Learning Rate
                      </label>
                      <input
                        type="number"
                        value={lr}
                        onChange={(e) => setLr(Number(e.target.value))}
                        step={0.0001}
                        style={{
                          width: '100%',
                          padding: '8px',
                          border: '1px solid #ddd',
                          borderRadius: '6px',
                          fontSize: '13px',
                        }}
                      />
                    </div>
                  </div>

                  {/* LoRA Config */}
                  <div style={{ padding: '12px', background: 'white', borderRadius: '6px', border: '1px solid #e0e0e0' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginBottom: '12px' }}>
                      <input
                        type="checkbox"
                        checked={useLora}
                        onChange={(e) => setUseLora(e.target.checked)}
                        style={{ cursor: 'pointer' }}
                      />
                      <span style={{ fontSize: '12px', fontWeight: '600', color: '#333' }}>Use LoRA Training</span>
                    </label>

                    {useLora && (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                        <div>
                          <label style={{ fontSize: '11px', color: '#666', display: 'block', marginBottom: '4px' }}>
                            LoRA Rank (r)
                          </label>
                          <input
                            type="number"
                            value={loraR}
                            onChange={(e) => setLoraR(Number(e.target.value))}
                            min={1}
                            max={256}
                            style={{
                              width: '100%',
                              padding: '6px',
                              border: '1px solid #ddd',
                              borderRadius: '4px',
                              fontSize: '12px',
                            }}
                          />
                          <div style={{ fontSize: '10px', color: '#999', marginTop: '2px' }}>8-64 typical</div>
                        </div>
                        <div>
                          <label style={{ fontSize: '11px', color: '#666', display: 'block', marginBottom: '4px' }}>
                            LoRA Alpha (α)
                          </label>
                          <input
                            type="number"
                            value={loraAlpha}
                            onChange={(e) => setLoraAlpha(Number(e.target.value))}
                            min={1}
                            max={256}
                            style={{
                              width: '100%',
                              padding: '6px',
                              border: '1px solid #ddd',
                              borderRadius: '4px',
                              fontSize: '12px',
                            }}
                          />
                          <div style={{ fontSize: '10px', color: '#999', marginTop: '2px' }}>Usually 2×r</div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Metadata Section */}
            <div>
              <SectionHeader title="Job Information" icon="📝" section="metadata" />
              {expandedSection === 'metadata' && (
                <div style={{ marginTop: '12px', padding: '16px', background: '#f9f9f9', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: '600', color: '#666', display: 'block', marginBottom: '6px' }}>
                      Job Name
                    </label>
                    <input
                      type="text"
                      value={jobName}
                      onChange={(e) => setJobName(e.target.value)}
                      placeholder="Auto-generated if empty"
                      style={{
                        width: '100%',
                        padding: '8px',
                        border: '1px solid #ddd',
                        borderRadius: '6px',
                        fontSize: '13px',
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: '600', color: '#666', display: 'block', marginBottom: '6px' }}>
                      Description
                    </label>
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="Optional notes about this training run..."
                      rows={3}
                      style={{
                        width: '100%',
                        padding: '8px',
                        border: '1px solid #ddd',
                        borderRadius: '6px',
                        fontSize: '13px',
                        fontFamily: 'inherit',
                        resize: 'vertical',
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Preview Tab */}
      {activeTab === 'preview' && (
        <div style={{ padding: '16px', background: '#f9f9f9', borderRadius: '8px', marginBottom: '24px' }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '14px', fontWeight: '600' }}>Configuration Preview</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div style={{ padding: '12px', background: 'white', borderRadius: '6px' }}>
              <div style={{ fontSize: '11px', color: '#999', marginBottom: '4px', fontWeight: '600' }}>BASE MODEL</div>
              <div style={{ fontSize: '13px', fontWeight: '600' }}>
                {selectedModel ? `Model #${selectedModel}` : '—'}
              </div>
              <div style={{ fontSize: '11px', color: '#666', marginTop: '4px' }}>
                Source: {modelSource}
              </div>
            </div>

            <div style={{ padding: '12px', background: 'white', borderRadius: '6px' }}>
              <div style={{ fontSize: '11px', color: '#999', marginBottom: '4px', fontWeight: '600' }}>DATASET</div>
              <div style={{ fontSize: '13px', fontWeight: '600' }}>
                {selectedDataset || '—'}
              </div>
              <div style={{ fontSize: '11px', color: '#666', marginTop: '4px' }}>
                Source: {datasetSource}
              </div>
            </div>

            <div style={{ padding: '12px', background: 'white', borderRadius: '6px' }}>
              <div style={{ fontSize: '11px', color: '#999', marginBottom: '4px', fontWeight: '600' }}>HYPERPARAMETERS</div>
              <div style={{ fontSize: '12px', color: '#333', lineHeight: '1.6' }}>
                Epochs: {epochs} • Batch: {batchSize} • LR: {lr}
                <br />
                {useLora ? `LoRA (r=${loraR}, α=${loraAlpha})` : 'Full Fine-tune'}
              </div>
            </div>

            <div style={{ padding: '12px', background: 'white', borderRadius: '6px' }}>
              <div style={{ fontSize: '11px', color: '#999', marginBottom: '4px', fontWeight: '600' }}>LORA ADAPTER</div>
              <div style={{ fontSize: '13px', fontWeight: '600' }}>
                {selectedLora ? `Adapter #${selectedLora}` : 'None (base model)'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '12px', borderTop: '1px solid #e0e0e0', paddingTop: '24px' }}>
        <button
          onClick={handleSubmit}
          disabled={!isComplete || isLoading}
          style={{
            padding: '12px 24px',
            background: isComplete ? '#667eea' : '#ddd',
            color: isComplete ? 'white' : '#999',
            border: 'none',
            borderRadius: '8px',
            cursor: isComplete ? 'pointer' : 'not-allowed',
            fontSize: '13px',
            fontWeight: '600',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s ease',
          }}
          onMouseOver={(e) => {
            if (isComplete) e.currentTarget.style.background = '#5568d3';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.background = '#667eea';
          }}
        >
          {isLoading ? (
            <>
              <Loader size={14} style={{ animation: 'spin 1s linear infinite' }} />
              Starting...
            </>
          ) : (
            <>
              <Play size={14} />
              Start Training Job
            </>
          )}
        </button>

        {!isComplete && (
          <div style={{ padding: '12px', color: '#c00', fontSize: '12px', display: 'flex', alignItems: 'center' }}>
            ⚠️ Select model and dataset to enable training
          </div>
        )}
      </div>
    </div>
  );
};

export default EnhancedTrainingSetup;
