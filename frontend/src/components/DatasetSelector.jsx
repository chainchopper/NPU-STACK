import React, { useState, useEffect } from 'react';
import { Search, Upload, AlertCircle, CheckCircle } from 'lucide-react';
import { API_BASE } from '../api/client';

/**
 * Unified Dataset Selector
 * Supports HuggingFace Hub datasets and local dataset uploads
 * Provides preview, format validation, and sizing information
 */
export const DatasetSelector = ({ 
  value, 
  onChange,
  selectedSource = 'local' // 'local', 'huggingface'
}) => {
  const [datasets, setDatasets] = useState([]);
  const [filteredDatasets, setFilteredDatasets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [source, setSource] = useState(selectedSource);
  const [error, setError] = useState(null);
  const [uploadingFile, setUploadingFile] = useState(false);

  // Fetch datasets based on source
  useEffect(() => {
    const fetchDatasets = async () => {
      setLoading(true);
      setError(null);
      try {
        if (source === 'local') {
          const response = await fetch(`${API_BASE}/datasets`);
          if (!response.ok) throw new Error('Failed to fetch local datasets');
          const data = await response.json();
          setDatasets(data.datasets || []);
          setFilteredDatasets(data.datasets || []);
        } else if (source === 'huggingface') {
          const response = await fetch(`${API_BASE}/hub/datasets/search?limit=50&sort=downloads`);
          if (!response.ok) throw new Error('Failed to fetch HuggingFace datasets');
          const data = await response.json();
          setDatasets(data.datasets || []);
          setFilteredDatasets(data.datasets || []);
        }
      } catch (err) {
        setError(err.message);
        setDatasets([]);
        setFilteredDatasets([]);
      } finally {
        setLoading(false);
      }
    };

    fetchDatasets();
  }, [source]);

  // Filter by search
  useEffect(() => {
    let filtered = datasets;
    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter(d => 
        (d.name || '').toLowerCase().includes(q) ||
        (d.id || '').toLowerCase().includes(q)
      );
    }
    setFilteredDatasets(filtered);
  }, [search, datasets]);

  // Handle file upload
  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.jsonl') && !file.name.endsWith('.json')) {
      setError('Only .jsonl or .json files are supported');
      return;
    }

    setUploadingFile(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('name', file.name.replace(/\.[^/.]+$/, ''));

      const response = await fetch(`${API_BASE}/datasets/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to upload dataset');
      }

      const data = await response.json();
      onChange(data.dataset_name);
      setSource('local');
    } catch (err) {
      setError(err.message);
    } finally {
      setUploadingFile(false);
    }
  };

  const selectedDataset = datasets.find(d => d.name === value);

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px' }}>
      <div style={{ marginBottom: '16px' }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: '600' }}>
          Dataset Source
        </h4>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => setSource('local')}
            style={{
              padding: '8px 12px',
              border: source === 'local' ? '2px solid #667eea' : '1px solid #ddd',
              borderRadius: '6px',
              background: source === 'local' ? '#f0f4ff' : 'white',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: '600',
              color: source === 'local' ? '#667eea' : '#666',
            }}
          >
            💾 Local Datasets
          </button>
          <button
            onClick={() => setSource('huggingface')}
            style={{
              padding: '8px 12px',
              border: source === 'huggingface' ? '2px solid #764ba2' : '1px solid #ddd',
              borderRadius: '6px',
              background: source === 'huggingface' ? '#f8f4ff' : 'white',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: '600',
              color: source === 'huggingface' ? '#764ba2' : '#666',
            }}
          >
            🤗 HuggingFace Hub
          </button>
        </div>
      </div>

      {/* Upload section for local */}
      {source === 'local' && (
        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '12px', color: '#666', display: 'block', marginBottom: '8px', fontWeight: '600' }}>
            Upload New Dataset
          </label>
          <label
            style={{
              display: 'block',
              padding: '24px',
              border: '2px dashed #ddd',
              borderRadius: '6px',
              textAlign: 'center',
              cursor: uploadingFile ? 'not-allowed' : 'pointer',
              background: uploadingFile ? '#f5f5f5' : 'white',
              transition: 'all 0.2s ease',
            }}
            onMouseOver={(e) => {
              if (!uploadingFile) e.currentTarget.style.borderColor = '#667eea';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.borderColor = '#ddd';
            }}
          >
            <Upload size={20} style={{ marginBottom: '8px', color: '#999' }} />
            <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px', fontWeight: '600' }}>
              {uploadingFile ? 'Uploading...' : 'Drag or click to upload .jsonl'}
            </div>
            <div style={{ fontSize: '11px', color: '#999' }}>
              Supports .jsonl (JSONL) or .json (JSON array) format
            </div>
            <input
              type="file"
              accept=".jsonl,.json"
              onChange={handleFileUpload}
              disabled={uploadingFile}
              style={{ display: 'none' }}
            />
          </label>
        </div>
      )}

      {/* Search */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ position: 'relative' }}>
          <Search size={16} style={{ position: 'absolute', left: '8px', top: '8px', color: '#999' }} />
          <input
            type="text"
            placeholder={`Search ${source} datasets...`}
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
        }}>
          <AlertCircle size={16} style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '24px', color: '#999', fontSize: '12px' }}>
          Loading datasets...
        </div>
      )}

      {/* Datasets list */}
      {!loading && filteredDatasets.length > 0 && (
        <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
          {filteredDatasets.map((dataset) => {
            const isSelected = dataset.name === value;
            const size = dataset.size || dataset.size_bytes || 0;
            const humanSize = size > 1e9 
              ? `${(size / 1e9).toFixed(1)} GB`
              : size > 1e6
              ? `${(size / 1e6).toFixed(1)} MB`
              : `${(size / 1e3).toFixed(0)} KB`;

            return (
              <button
                key={dataset.name}
                onClick={() => onChange(dataset.name)}
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
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  {isSelected && <CheckCircle size={14} style={{ color: '#667eea' }} />}
                  <div style={{ fontWeight: '600', fontSize: '13px' }}>
                    {dataset.name}
                  </div>
                </div>
                <div style={{ fontSize: '12px', color: '#666', marginBottom: '6px' }}>
                  Type: {dataset.type || 'jsonl'} • Size: {humanSize}
                </div>
                {dataset.description && (
                  <div style={{ fontSize: '11px', color: '#999' }}>
                    {dataset.description.substring(0, 80)}...
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}

      {!loading && filteredDatasets.length === 0 && datasets.length > 0 && (
        <div style={{ padding: '24px', textAlign: 'center', color: '#999', fontSize: '13px' }}>
          No datasets match your search
        </div>
      )}

      {!loading && datasets.length === 0 && source === 'local' && (
        <div style={{ padding: '24px', textAlign: 'center', color: '#999', fontSize: '13px' }}>
          No local datasets uploaded yet. Upload one above.
        </div>
      )}

      {/* Selected dataset preview */}
      {selectedDataset && (
        <div style={{
          marginTop: '16px',
          padding: '12px',
          background: '#f5f5f5',
          borderRadius: '6px',
          borderLeft: '3px solid #667eea',
          fontSize: '12px',
        }}>
          <div style={{ fontWeight: '600', marginBottom: '4px' }}>
            ✓ Selected: {selectedDataset.name}
          </div>
          <div style={{ color: '#666', fontSize: '11px' }}>
            Type: {selectedDataset.type || 'jsonl'} • Source: {source}
          </div>
        </div>
      )}
    </div>
  );
};

export default DatasetSelector;
