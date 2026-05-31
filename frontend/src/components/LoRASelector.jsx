import React, { useState, useEffect } from 'react';
import { Search, AlertCircle, Download, Star, ExternalLink } from 'lucide-react';
import { API_BASE } from '../api/client';

/**
 * LoRA/Adapter Selector
 * Browse and select LoRA adapters from CivitAI
 * Supports filtering by model compatibility and rating
 */
export const LoRASelector = ({ 
  value, 
  onChange,
  baseModelId = null,
  showExternal = true
}) => {
  const [loras, setLoras] = useState([]);
  const [filteredLoras, setFilteredLoras] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState(null);
  const [minRating, setMinRating] = useState(0);
  const [sortBy, setSortBy] = useState('trending');

  // Fetch LoRAs from CivitAI
  useEffect(() => {
    const fetchLoras = async () => {
      setLoading(true);
      setError(null);
      try {
        let url = `${API_BASE}/civitai/models/search?type=lora&limit=50`;
        
        if (sortBy === 'trending') url += '&sort=trendingDownloads';
        else if (sortBy === 'rating') url += '&sort=rating';
        else if (sortBy === 'newest') url += '&sort=newest';

        const response = await fetch(url);
        if (!response.ok) {
          throw new Error('Failed to fetch LoRAs from CivitAI');
        }

        const data = await response.json();
        const loraList = data.results || [];
        setLoras(loraList);
        setFilteredLoras(loraList);
      } catch (err) {
        setError(err.message);
        setLoras([]);
        setFilteredLoras([]);
      } finally {
        setLoading(false);
      }
    };

    fetchLoras();
  }, [sortBy]);

  // Filter by search + rating
  useEffect(() => {
    let filtered = loras;

    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter(l => 
        (l.name || '').toLowerCase().includes(q) ||
        (l.creator || '').toLowerCase().includes(q)
      );
    }

    if (minRating > 0) {
      filtered = filtered.filter(l => (l.stats?.rating || 0) >= minRating);
    }

    // Filter by base model if specified
    if (baseModelId) {
      filtered = filtered.filter(l => 
        !l.trainedWords || 
        l.trainedWords.some(w => w.toLowerCase().includes(baseModelId.toLowerCase()))
      );
    }

    setFilteredLoras(filtered);
  }, [search, minRating, loras, baseModelId]);

  const selectedLora = loras.find(l => l.id === value);

  const RatingStars = ({ rating }) => {
    const stars = Math.floor(rating || 0);
    return (
      <div style={{ display: 'flex', gap: '2px', color: '#ffc107' }}>
        {[...Array(5)].map((_, i) => (
          <Star
            key={i}
            size={12}
            fill={i < stars ? '#ffc107' : 'none'}
            stroke={i < stars ? '#ffc107' : '#ddd'}
          />
        ))}
      </div>
    );
  };

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px' }}>
      <div style={{ marginBottom: '16px' }}>
        <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: '600' }}>
          🎨 LoRA Adapters (CivitAI)
        </h4>
        <p style={{ margin: 0, fontSize: '11px', color: '#999', marginBottom: '12px' }}>
          Optional: Add a trained LoRA adapter to your model. Enhances specific domains or styles.
        </p>
      </div>

      {/* Filters */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
        {/* Search */}
        <div style={{ position: 'relative' }}>
          <Search size={14} style={{ position: 'absolute', left: '8px', top: '8px', color: '#999' }} />
          <input
            type="text"
            placeholder="Search LoRAs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: '100%',
              padding: '6px 8px 6px 28px',
              border: '1px solid #ddd',
              borderRadius: '6px',
              fontSize: '12px',
            }}
          />
        </div>

        {/* Sort */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          style={{
            padding: '6px',
            border: '1px solid #ddd',
            borderRadius: '6px',
            fontSize: '12px',
            background: 'white',
          }}
        >
          <option value="trending">Trending</option>
          <option value="rating">Top Rated</option>
          <option value="newest">Newest</option>
        </select>
      </div>

      {/* Min Rating */}
      <div style={{ marginBottom: '16px' }}>
        <label style={{ fontSize: '12px', color: '#666', display: 'block', marginBottom: '6px', fontWeight: '600' }}>
          Minimum Rating
        </label>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {[0, 3, 3.5, 4, 4.5].map((rating) => (
            <button
              key={rating}
              onClick={() => setMinRating(rating)}
              style={{
                padding: '6px 10px',
                border: minRating === rating ? '2px solid #667eea' : '1px solid #ddd',
                borderRadius: '6px',
                background: minRating === rating ? '#f0f4ff' : 'white',
                cursor: 'pointer',
                fontSize: '11px',
                fontWeight: '600',
                color: minRating === rating ? '#667eea' : '#666',
              }}
            >
              {rating === 0 ? 'Any' : `${rating}+`}
            </button>
          ))}
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
          Loading LoRAs...
        </div>
      )}

      {/* LoRAs list */}
      {!loading && filteredLoras.length > 0 && (
        <div style={{ maxHeight: '450px', overflowY: 'auto', marginBottom: '12px' }}>
          {filteredLoras.map((lora) => {
            const isSelected = lora.id === value;
            const downloads = lora.stats?.downloadCount || 0;
            const rating = lora.stats?.rating || 0;
            const thumbUrl = lora.modelVersions?.[0]?.images?.[0]?.url;

            return (
              <button
                key={lora.id}
                onClick={() => onChange(lora.id)}
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
                  display: 'flex',
                  gap: '12px',
                  alignItems: 'flex-start',
                }}
                onMouseOver={(e) => {
                  if (!isSelected) e.currentTarget.style.borderColor = '#ddd';
                }}
                onMouseOut={(e) => {
                  if (!isSelected) e.currentTarget.style.borderColor = '#eee';
                }}
              >
                {thumbUrl && (
                  <img
                    src={thumbUrl}
                    alt={lora.name}
                    style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '4px',
                      objectFit: 'cover',
                      flexShrink: 0,
                    }}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: '600', fontSize: '13px', marginBottom: '4px' }}>
                    {lora.name}
                  </div>
                  <div style={{ fontSize: '11px', color: '#666', marginBottom: '4px' }}>
                    by {lora.creator || 'Unknown'}
                  </div>
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center', fontSize: '11px', color: '#999' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <RatingStars rating={rating} />
                      <span>{rating.toFixed(1)}</span>
                    </div>
                    <span>📥 {(downloads / 1000).toFixed(0)}k</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {!loading && filteredLoras.length === 0 && loras.length > 0 && (
        <div style={{ padding: '24px', textAlign: 'center', color: '#999', fontSize: '12px', marginBottom: '12px' }}>
          No LoRAs match your filters
        </div>
      )}

      {/* Option to skip LoRA */}
      <button
        onClick={() => onChange(null)}
        style={{
          width: '100%',
          padding: '8px',
          border: !value ? '2px solid #666' : '1px solid #ddd',
          borderRadius: '6px',
          background: !value ? '#f5f5f5' : 'white',
          cursor: 'pointer',
          fontSize: '12px',
          fontWeight: '600',
          color: !value ? '#333' : '#666',
          marginBottom: '12px',
        }}
      >
        ✓ Skip LoRA (fine-tune base model only)
      </button>

      {/* Selected LoRA preview */}
      {selectedLora && (
        <div style={{
          padding: '12px',
          background: '#f5f5f5',
          borderRadius: '6px',
          borderLeft: '3px solid #667eea',
          fontSize: '12px',
        }}>
          <div style={{ fontWeight: '600', marginBottom: '4px' }}>
            ✓ Selected: {selectedLora.name}
          </div>
          <div style={{ color: '#666', fontSize: '11px', marginBottom: '6px' }}>
            by {selectedLora.creator || 'Unknown'} • {selectedLora.stats?.rating.toFixed(1)} ⭐
          </div>
          {showExternal && (
            <a
              href={`https://civitai.com/models/${selectedLora.id}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '11px',
                color: '#667eea',
                textDecoration: 'none',
              }}
            >
              View on CivitAI <ExternalLink size={10} />
            </a>
          )}
        </div>
      )}
    </div>
  );
};

export default LoRASelector;
