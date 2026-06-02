import React, { useEffect, useMemo, useState } from 'react';
import {
  BookOpen,
  RefreshCw,
  Search,
  DownloadCloud,
  FileText,
  Database,
  ExternalLink,
} from 'lucide-react';
import {
  getDocsIndexStatus,
  getGitbookRegistry,
  rebuildDocsIndex,
  searchDocsIndex,
  listGitbookDocs,
  readGitbookDoc,
  syncExternalDocsToGitbook,
  syncProjectDocsToGitbook,
} from '../api/client';

function scoreTone(score) {
  if (score >= 10) return 'badge-success';
  if (score >= 6) return 'badge-info';
  return 'badge-warning';
}

export default function Documentation() {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const [docsStatus, setDocsStatus] = useState(null);
  const [gitbookRegistry, setGitbookRegistry] = useState(null);
  const [activeProjectId, setActiveProjectId] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);

  const [gitbookDocs, setGitbookDocs] = useState([]);
  const [selectedPath, setSelectedPath] = useState('');
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [autoSyncedProjects, setAutoSyncedProjects] = useState({});

  const activeProject = useMemo(
    () => (gitbookRegistry?.projects || []).find((project) => project.id === activeProjectId) || null,
    [gitbookRegistry, activeProjectId]
  );

  const visibleDoc = useMemo(
    () => gitbookDocs.find((doc) => doc.path === selectedPath) || null,
    [gitbookDocs, selectedPath]
  );

  const loadOverview = async () => {
    setBusy(true);
    setError('');
    try {
      const [statusRes, registryRes] = await Promise.all([
        getDocsIndexStatus(),
        getGitbookRegistry(),
      ]);
      setDocsStatus(statusRes?.status || null);
      setGitbookRegistry(registryRes || null);

      const nextProjectId = activeProjectId || registryRes?.current_project || registryRes?.projects?.[0]?.id || '';
      if (nextProjectId) {
        setActiveProjectId(nextProjectId);
      }
    } catch (e) {
      setError(e.message || 'Failed to load documentation overview');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    loadOverview();
  }, []);

  useEffect(() => {
    const loadProjectDocs = async () => {
      if (!activeProjectId) {
        setGitbookDocs([]);
        setSelectedPath('');
        setSelectedDoc(null);
        return;
      }

      try {
        const docsRes = await listGitbookDocs(activeProjectId);
        let docs = docsRes?.docs || [];

        if (docs.length === 0 && !autoSyncedProjects[activeProjectId]) {
          setAutoSyncedProjects((prev) => ({ ...prev, [activeProjectId]: true }));
          const syncRes = await syncProjectDocsToGitbook(activeProjectId);
          if (syncRes?.status === 'success' && (syncRes?.count || 0) > 0) {
            const retryRes = await listGitbookDocs(activeProjectId);
            docs = retryRes?.docs || [];
            setNotice(`Bootstrapped ${syncRes.count} project docs into the local mirror for ${activeProjectId}.`);
            await loadOverview();
          }
        }

        setGitbookDocs(docs);
        setSelectedPath((current) => {
          if (current && docs.some((doc) => doc.path === current)) {
            return current;
          }
          return docs[0]?.path || '';
        });
      } catch (e) {
        setGitbookDocs([]);
        setSelectedPath('');
        setSelectedDoc(null);
        setError(e.message || 'Failed to load project GitBook docs');
      }
    };

    loadProjectDocs();
  }, [activeProjectId]);

  useEffect(() => {
    const loadDoc = async () => {
      if (!selectedPath) {
        setSelectedDoc(null);
        return;
      }
      try {
        const res = await readGitbookDoc(selectedPath, activeProjectId || null);
        if (res?.ok) {
          setSelectedDoc(res);
        } else {
          setSelectedDoc(null);
        }
      } catch {
        setSelectedDoc(null);
      }
    };
    loadDoc();
  }, [selectedPath, activeProjectId]);

  const handleRebuild = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await rebuildDocsIndex({ force: true, include_external: true });
      setDocsStatus(res?.status || null);
      setNotice(`Index rebuilt with ${res?.status?.stats?.chunks || 0} chunks.`);
    } catch (e) {
      setError(e.message || 'Failed to rebuild docs index');
    } finally {
      setBusy(false);
    }
  };

  const handleSyncExternal = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await syncExternalDocsToGitbook(activeProjectId || null);
      if (res?.status !== 'success') {
        throw new Error(res?.error || 'Sync failed');
      }
      setNotice(`Synced ${res?.count || 0} external compatibility sources into the local mirror (stored separately under runtime-compatibility; project docs are not renamed).`);
      await loadOverview();
      await handleRebuild();
    } catch (e) {
      setError(e.message || 'Failed to sync external docs');
    } finally {
      setBusy(false);
    }
  };

  const handleSyncProjectDocs = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await syncProjectDocsToGitbook(activeProjectId || null);
      if (res?.status !== 'success') {
        throw new Error(res?.error || 'Project docs sync failed');
      }
      setNotice(`Synced ${res?.count || 0} project documents into the local GitBook mirror.`);
      await loadOverview();
      await handleRebuild();
    } catch (e) {
      setError(e.message || 'Failed to sync project docs');
    } finally {
      setBusy(false);
    }
  };

  const handleSearch = async () => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await searchDocsIndex(q, 8);
      setResults(res?.results || []);
    } catch (e) {
      setError(e.message || 'Search failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>Documentation</h2>
        <p>
          Shared GitBook host for multiple projects, plus local mirror search and runtime doc sync.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <BookOpen size={18} /> Shared GitBook Host
          </h3>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginBottom: 16 }}>
          <div className="badge badge-info" style={{ justifyContent: 'center' }}>
            mode: {gitbookRegistry?.integration_mode || 'shared-renderer'}
          </div>
          <div className="badge badge-info" style={{ justifyContent: 'center' }}>
            host: {gitbookRegistry?.base_url || 'n/a'}
          </div>
          <div className={`badge ${activeProject?.configured ? 'badge-success' : 'badge-warning'}`} style={{ justifyContent: 'center' }}>
            project: {activeProject?.title || 'unselected'}
          </div>
          <div className={`badge ${activeProject?.local_root_exists ? 'badge-success' : 'badge-warning'}`} style={{ justifyContent: 'center' }}>
            local mirror: {activeProject?.local_root_exists ? 'available' : 'not configured'}
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Project space</label>
          <select
            className="form-select"
            value={activeProjectId}
            onChange={(e) => setActiveProjectId(e.target.value)}
          >
            {(gitbookRegistry?.projects || []).map((project) => (
              <option key={project.id} value={project.id}>
                {project.title} — {project.id}
              </option>
            ))}
          </select>
        </div>

        {activeProject && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {activeProject.description && (
              <div className="text-secondary" style={{ fontSize: 14 }}>
                {activeProject.description}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
              <div className="card" style={{ margin: 0, padding: 16 }}>
                <div className="text-muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 6 }}>
                  Published target
                </div>
                <div className="text-mono" style={{ fontSize: 13, wordBreak: 'break-all' }}>
                  {activeProject.published_url || 'Set NPU_STACK_GITBOOK_* config to bind this project to a published GitBook space.'}
                </div>
              </div>

              <div className="card" style={{ margin: 0, padding: 16 }}>
                <div className="text-muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 6 }}>
                  Renderer URL
                </div>
                <div className="text-mono" style={{ fontSize: 13, wordBreak: 'break-all' }}>
                  {activeProject.renderer_url || 'Unavailable until a published target is configured.'}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" onClick={loadOverview} disabled={busy}>
                <RefreshCw size={14} className={busy ? 'animate-spin' : ''} /> Refresh Host Config
              </button>
              <button className="btn btn-secondary" onClick={handleSyncProjectDocs} disabled={busy}>
                <FileText size={14} /> Sync Project Docs
              </button>
              {activeProject?.renderer_url && (
                <a
                  className="btn btn-primary"
                  href={activeProject.renderer_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={14} /> Open Hosted Docs
                </a>
              )}
            </div>

            <div className="card" style={{ margin: 0, padding: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Docs operations, clearly separated</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10, fontSize: 12 }}>
                <div>
                  <div style={{ fontWeight: 700 }}>Refresh host config</div>
                  <div className="text-muted">Reloads `.env`-driven GitBook host/project registry values only.</div>
                </div>
                <div>
                  <div style={{ fontWeight: 700 }}>Sync project docs</div>
                  <div className="text-muted">Mirrors your NPU-STACK docs/README into `resources/project-docs` for this project.</div>
                </div>
                <div>
                  <div style={{ fontWeight: 700 }}>Sync external URLs</div>
                  <div className="text-muted">Imports compatibility references into `resources/runtime-compatibility` without rebranding project docs.</div>
                </div>
                <div>
                  <div style={{ fontWeight: 700 }}>Rebuild index</div>
                  <div className="text-muted">Re-chunks all local/external docs and writes the unified search index file.</div>
                </div>
              </div>
            </div>

            {activeProject?.renderer_url ? (
              <div
                style={{
                  borderRadius: 16,
                  border: '1px solid var(--border-color)',
                  overflow: 'hidden',
                  background: 'var(--bg-secondary)',
                  minHeight: 680,
                }}
              >
                <iframe
                  title={`${activeProject.title} hosted docs`}
                  src={activeProject.renderer_url}
                  style={{ width: '100%', height: 680, border: 0, background: 'transparent' }}
                />
              </div>
            ) : (
              <div className="card" style={{ margin: 0, borderColor: 'var(--accent-amber)', padding: 16 }}>
                <div style={{ color: 'var(--accent-amber)', fontSize: 13 }}>
                  This project is not yet mapped to a published GitBook site. Configure the shared host and the project published URL, then this page will render through the single hosted GitBook instance.
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {notice && (
        <div className="card" style={{ marginBottom: 12, borderColor: 'var(--accent-green)' }}>
          <div style={{ color: 'var(--accent-green)', fontSize: 13 }}>{notice}</div>
        </div>
      )}
      {error && (
        <div className="card" style={{ marginBottom: 12, borderColor: 'var(--accent-red)' }}>
          <div style={{ color: 'var(--accent-red)', fontSize: 13 }}>{error}</div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Database size={18} /> Unified Docs Index
          </h3>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 8, marginBottom: 12 }}>
          <div className="badge badge-info" style={{ justifyContent: 'center' }}>
            ready: {docsStatus?.ready ? 'yes' : 'no'}
          </div>
          <div className="badge badge-info" style={{ justifyContent: 'center' }}>
            chunks: {docsStatus?.stats?.chunks ?? 0}
          </div>
          <div className="badge badge-info" style={{ justifyContent: 'center' }}>
            sources: {docsStatus?.stats?.sources ?? 0}
          </div>
          <div className="badge badge-info" style={{ justifyContent: 'center' }}>
            built: {docsStatus?.built_at ? new Date(docsStatus.built_at).toLocaleString() : 'n/a'}
          </div>
        </div>

        <div className="card" style={{ margin: '0 0 12px 0', padding: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Index artifacts</div>
          <div className="text-muted" style={{ fontSize: 12 }}>
            Index file: <code>{docsStatus?.index_file || 'backend/data/docs_index.json'}</code>
          </div>
          <div className="text-muted" style={{ fontSize: 12 }}>
            Project docs sync: {docsStatus?.sync?.project?.status || 'n/a'}
            {docsStatus?.sync?.project?.recorded_at ? ` · ${new Date(docsStatus.sync.project.recorded_at).toLocaleString()}` : ''}
            {typeof docsStatus?.sync?.project?.count === 'number' ? ` · ${docsStatus.sync.project.count} files` : ''}
          </div>
          <div className="text-muted" style={{ fontSize: 12 }}>
            External sync: {docsStatus?.sync?.external?.status || 'n/a'}
            {docsStatus?.sync?.external?.recorded_at ? ` · ${new Date(docsStatus.sync.external.recorded_at).toLocaleString()}` : ''}
            {typeof docsStatus?.sync?.external?.count === 'number' ? ` · ${docsStatus.sync.external.count} files` : ''}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <button className="btn btn-secondary" onClick={loadOverview} disabled={busy}>
            <RefreshCw size={14} className={busy ? 'animate-spin' : ''} /> Refresh
          </button>
          <button className="btn btn-secondary" onClick={handleSyncProjectDocs} disabled={busy}>
            <FileText size={14} /> Sync Project Docs
          </button>
          <button className="btn btn-secondary" onClick={handleRebuild} disabled={busy}>
            <Database size={14} /> Rebuild Index
          </button>
          <button className="btn btn-primary" onClick={handleSyncExternal} disabled={busy}>
            <DownloadCloud size={14} /> Sync External Compatibility URLs
          </button>
        </div>

        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Search indexed docs</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="form-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
              placeholder="Search compatibility docs and project docs"
            />
            <button className="btn btn-primary" onClick={handleSearch} disabled={busy || !query.trim()}>
              <Search size={14} /> Search
            </button>
          </div>
        </div>

        {results.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {results.map((hit) => (
              <div key={hit.id} className="card" style={{ margin: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <div style={{ fontWeight: 700 }}>{hit.title || hit.source}</div>
                  <span className={`badge ${scoreTone(Number(hit.score || 0))}`}>score {hit.score}</span>
                </div>
                <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {hit.source_type} · {hit.source}
                </div>
                <div
                  style={{ marginTop: 8, fontSize: 12, whiteSpace: 'pre-wrap' }}
                  dangerouslySetInnerHTML={{ __html: hit.snippet_highlighted || hit.snippet || '' }}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <div className="card">
          <div className="card-header">
            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <BookOpen size={18} /> Local GitBook Mirror
            </h3>
          </div>

          <div className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
            Local markdown mirror for indexed search, sync jobs, and offline inspection.
          </div>

          <div className="form-group">
            <label className="form-label">Document</label>
            <select
              className="form-select"
              value={selectedPath}
              onChange={(e) => setSelectedPath(e.target.value)}
            >
              {gitbookDocs.map((doc) => (
                <option key={doc.path} value={doc.path}>
                  {doc.title} — {doc.path}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 480, overflowY: 'auto' }}>
            {gitbookDocs.map((doc) => (
              <button
                key={doc.path}
                className="btn btn-secondary"
                onClick={() => setSelectedPath(doc.path)}
                style={{
                  justifyContent: 'flex-start',
                  background: doc.path === selectedPath ? 'var(--bg-secondary)' : undefined,
                }}
              >
                <FileText size={14} />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.title}
                </span>
              </button>
            ))}
            {gitbookDocs.length === 0 && (
              <div className="text-muted" style={{ fontSize: 12 }}>No GitBook entries found in `SUMMARY.md`.</div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <ExternalLink size={18} /> Mirror Preview
            </h3>
          </div>

          {selectedDoc ? (
            <>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
                {visibleDoc?.title || selectedDoc.title} · {selectedDoc.path}
              </div>
              <pre
                style={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  lineHeight: 1.5,
                  maxHeight: 560,
                  overflowY: 'auto',
                  background: 'var(--bg-secondary)',
                  borderRadius: 8,
                  border: '1px solid var(--border-color)',
                  padding: 12,
                }}
              >
                {selectedDoc.content}
              </pre>
            </>
          ) : (
            <div className="text-muted" style={{ fontSize: 12 }}>Select a GitBook page to preview.</div>
          )}
        </div>
      </div>
    </div>
  );
}
