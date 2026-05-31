import React, { useState, useEffect } from 'react';
import { Search, Loader, Download, Heart, AlertCircle } from 'lucide-react';
import { API_BASE } from '../api/client';

/**
 * Unified Model Selector
 * Supports both HuggingFace Hub and CivitAI model sourcing
 * Allows filtering, search, and dual-source comparison
 */
export const ModelSelector = ({ 
  value, 
  onChange, 
  selectedSource = 'huggingface' // 'huggingface' or 'civitai'
}) => {
  const [models, setModels] = useState([]);
  const [filteredModels, setFilteredModels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [source, setSource] = useState(selectedSource);
  const [error, setError] = useState(null);
  const [modelTypes, setModelTypes] = useState([]);
  const [selectedType, setSelectedType] = useState('');

  // Fetch models based on source
  useEffect(() => {
    const fetchModels = async () => {
      setLoading(true);
      setError(null);
      try {
        let endpoint = '';
        if (source === 'huggingface') {
          endpoint = '/hub/models/search?limit=50&sort_by=downloads';
        } else if (source === 'civitai') {
          endpoint = '/civitai/models/search?limit=50&type=checkpoint';
        }

        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) {
          throw new Error(`Failed to fetch ${source} models`);
        }

        const data = await response.json();
        const modelList = source === 'huggingface' 
          ? (data.models || [])
          : (data.results || []);

        setModels(modelList);
        setFilteredModels(modelList);

        // Extract unique model types
        const types = [...new Set(
          modelList.map(m => m.type || m.modelType || 'unknown').filter(Boolean)
        )];
        setModelTypes(types);
      } catch (err) {
        setError(err.message);
        setModels([]);
        setFilteredModels([]);
      } finally {
        setLoading(false);
      }
    };

    fetchModels();
  }, [source]);

  // Filter models by search + type
  useEffect(() => {
    let filtered = models;

    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter(m => 
        (m.name || m.modelName || '').toLowerCase().includes(q) ||
        (m.id || '').toLowerCase().includes(q)
      );
    }

    if (selectedType) {
      filtered = filtered.filter(m => 
        (m.type || m.modelType || 'unknown') === selectedType
      );
    }

    setFilteredModels(filtered);
  }, [search, selectedType, models]);

  const selectedModel = models.find(m => m.id === value);

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px' }}>
      <div style={{ marginBottom: '16px' }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: '600' }}>
          Model Source
        </h4>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => { setSource('huggingface'); setSelectedType(''); }}
            style={{
              padding: '8px 12px',
              border: source === 'huggingface' ? '2px solid #667eea' : '1px solid #ddd',
              borderRadius: '6px',
              background: source === 'huggingface' ? '#f0f4ff' : 'white',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: '600',
              color: source === 'huggingface' ? '#667eea' : '#666',
            }}
          >
            🤗 HuggingFace Hub
          </button>
          <button
            onClick={() => { setSource('civitai'); setSelectedType(''); }}
            style={{
              padding: '8px 12px',
              border: source === 'civitai' ? '2px solid #764ba2' : '1px solid #ddd',
              borderRadius: '6px',
              background: source === 'civitai' ? '#f8f4ff' : 'white',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: '600',
              color: source === 'civitai' ? '#764ba2' : '#666',
            }}
          >
            🎨 CivitAI
          </button>
        </div>
      </div>

      {/* Search and filters */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '8px', top: '8px', color: '#999' }} />
            <input
              type="text"
              placeholder={`Search ${source} models...`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 8px 8px 32px',
                border: '1px solid #ddd',
                borderRadius: '6px',
                fontSize: '13px',
              }}
            />
          </div>
        </div>

        {modelTypes.length > 0 && (
          <div>
            <label style={{ fontSize: '12px', color: '#666', display: 'block', marginBottom: '6px' }}>
              Type
            </label>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              style={{
                width: '100%',
                padding: '6px',
                border: '1px solid #ddd',
                borderRadius: '6px',
                fontSize: '12px',
                background: 'white',
              }}
            >
              <option value="">All types</option>
              {modelTypes.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div style={{
          padding: '12px',
          background: '#fee',
          border: '1px solid #fcc',
          borderRadius: '6px',
          color: '#c00',
          fontSize: '12px',
          marginBottom: '12px',
          display: 'flex',
          gap: '8px',
          alignItems: 'flex-start'
        }}>
          <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
          <span>{error}</span>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '24px', color: '#999' }}>
          <Loader size={20} style={{ animation: 'spin 1s linear infinite', marginRight: '8px' }} />
          Loading {source} models...
        </div>
      )}

      {/* Models list */}
      {!loading && filteredModels.length > 0 && (
        <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
          {filteredModels.map((model) => {
            const isSelected = model.id === value;
            const name = model.name || model.modelName || model.id;
            const desc = model.description || model.summary || '';
            const downloads = model.downloads || model.stats?.downloadCount || 0;
            const rating = model.rating || 0;

            return (
              <button
                key={model.id}
                onClick={() => onChange(model.id)}
                style={{
                  width: '100%',
                  padding: '12px',
                  textAlign: 'left',
                  border: isSelected ? '2px solid #667eea' : '1px solid #eee',
                  borderRadius: '6px',
                  background: isSelected ? '#f9faff' : 'white',
                  cursor: 'pointer',
                  marginBottom: '8px',
                  transition: 'all 0.2s ease',
                }}
                onMouseOver={(e) => {
                  if (!isSelected) e.currentTarget.style.borderColor = '#ddd';
                }}
                onMouseOut={(e) => {
                  if (!isSelected) e.currentTarget.style.borderColor = '#eee';
                }}
              >
                <div style={{ fontWeight: '600', fontSize: '13px', marginBottom: '4px' }}>
                  {name}
                </div>
                {desc && (
                  <div style={{ fontSize: '12px', color: '#666', marginBottom: '6px', lineHeight: '1.4' }}>
                    {desc.substring(0, 100)}...
                  </div>
                )}
                <div style={{ display: 'flex', gap: '16px', fontSize: '11px', color: '#999' }}>
                  {downloads > 0 && <span>📥 {(downloads / 1000).toFixed(1)}k</span>}
                  {rating > 0 && <span>⭐ {rating.toFixed(1)}</span>}
                  {model.type && <span>🏷️ {model.type}</span>}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {!loading && filteredModels.length === 0 && models.length > 0 && (
        <div style={{ padding: '24px', textAlign: 'center', color: '#999', fontSize: '13px' }}>
          No models match your search
        </div>
      )}

      {/* Selected model preview */}
      {selectedModel && (
        <div style={{
          marginTop: '16px',
          padding: '12px',
          background: '#f5f5f5',
          borderRadius: '6px',
          borderLeft: '3px solid #667eea',
          fontSize: '12px',
        }}>
          <div style={{ fontWeight: '600', marginBottom: '4px' }}>
            ✓ Selected: {selectedModel.name || selectedModel.modelName}
          </div>
          <div style={{ color: '#666', fontSize: '11px' }}>
            Source: {source === 'huggingface' ? 'HuggingFace Hub' : 'CivitAI'}
          </div>
        </div>
      )}
    </div>
  );
};

export default ModelSelector;
