import { useState, useEffect } from 'react';
import { apiUrl } from '../api/client';

export default function NirvanaCron() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(apiUrl('/nirvana/cron'))
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <div className="loading-overlay"><div className="spinner"/><span>Loading cron...</span></div>;
  if (error) return <div className="page-card" style={{color:'var(--text-secondary)'}}>Error: {error}</div>;

  return (
    <div style={{ padding: 24, maxWidth: 800 }}>
      <h2 style={{ marginBottom: 4 }}>Scheduled Tasks</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 24 }}>
        {data?.count || 0} cron jobs — output directory: <code style={{fontSize:11}}>{data?.output_dir || 'n/a'}</code>
      </p>

      {(!data?.jobs || data.jobs.length === 0) && (
        <div style={{
          padding: '40px 20px', textAlign: 'center',
          color: 'var(--text-muted)', fontSize: 13,
          background: 'var(--bg-card)', borderRadius: 10,
          border: '1px dashed var(--border-color)',
        }}>
          No cron jobs have been configured yet.
          <br/>
          <span style={{ fontSize: 12, marginTop: 8, display: 'inline-block' }}>
            Nirvana can schedule recurring tasks — ask it in the chat to set one up.
          </span>
        </div>
      )}

      {data?.jobs?.map((job, i) => (
        <div key={i} style={{
          padding: 14, marginBottom: 8, borderRadius: 10,
          background: 'var(--bg-card)', border: '1px solid var(--border-color)',
        }}>
          <div style={{fontSize:13,fontWeight:500,color:'var(--text-primary)'}}>
            {job.name || job._file || `Job #${i + 1}`}
          </div>
          {job.schedule && <div style={{fontSize:11,color:'var(--text-muted)',marginTop:4}}>Schedule: {job.schedule}</div>}
          {job.last_run && <div style={{fontSize:11,color:'var(--text-muted)'}}>Last run: {job.last_run}</div>}
          {job.error && <div style={{fontSize:11,color:'#f87171',marginTop:4}}>{job.error}</div>}
        </div>
      ))}
    </div>
  );
}
