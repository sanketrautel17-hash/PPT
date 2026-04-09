import { useEffect, useRef, useState } from 'react';
import { listTemplates, reprofileTemplate, uploadTemplate } from '../api.js';

const THUMB_EMOJIS = ['🎨', '📊', '📈', '🖼️', '🗂️', '📋', '🌐', '💼'];

export default function Templates({ navigate }) {
  const [templates, setTemplates] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState(null);
  const [uploadOk,  setUploadOk]  = useState(null);
  const [dragOver,  setDragOver]  = useState(false);
  const [templateName, setTemplateName] = useState('');
  const [pendingFile,  setPendingFile]  = useState(null);
  const [reprofilingId, setReprofilingId] = useState(null);
  const fileInputRef = useRef(null);

  const load = () => {
    setLoading(true);
    listTemplates()
      .then(setTemplates)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleFilePick = (file) => {
    if (!file) return;
    if (!file.name.endsWith('.pptx')) {
      setUploadErr('Only .pptx files are supported.'); return;
    }
    setPendingFile(file);
    setUploadErr(null);
    if (!templateName) setTemplateName(file.name.replace('.pptx', ''));
  };

  const handleUpload = async () => {
    if (!pendingFile) { setUploadErr('Please select a .pptx file.'); return; }
    if (!templateName.trim()) { setUploadErr('Please enter a template name.'); return; }
    setUploading(true); setUploadErr(null); setUploadOk(null);
    try {
      await uploadTemplate(pendingFile, templateName.trim());
      setUploadOk(`"${templateName}" uploaded and analyzing…`);
      setPendingFile(null);
      setTemplateName('');
      load();
    } catch (e) {
      setUploadErr(e.message);
    } finally {
      setUploading(false);
    }
  };

  const handleReprofile = async (templateId, templateName) => {
    setReprofilingId(templateId);
    setUploadErr(null);
    setUploadOk(null);
    try {
      await reprofileTemplate(templateId);
      setUploadOk(`Re-profiling started for "${templateName}".`);
      load();
    } catch (e) {
      setUploadErr(`Re-profile failed: ${e.message}`);
    } finally {
      setReprofilingId(null);
    }
  };

  const thumbFor = (id) => THUMB_EMOJIS[parseInt(id?.slice(-2) || 0, 16) % THUMB_EMOJIS.length];

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>📂 Template Library</h1>
        <p>Upload branded .pptx templates. The AI preserves layouts, fonts, and images.</p>
      </div>

      {/* Upload Card */}
      <div className="card section">
        <div className="card-title">📤 Upload New Template</div>

        {/* Drop Zone */}
        <div
          id="upload-drop-zone"
          className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); handleFilePick(e.dataTransfer.files[0]); }}
        >
          <div className="upload-icon-wrapper">
            {pendingFile ? '✅' : '📎'}
          </div>
          <div className="upload-title">
            {pendingFile ? pendingFile.name : 'Drag & drop your .pptx file'}
          </div>
          <div className="upload-subtitle">
            {pendingFile
              ? `${(pendingFile.size / 1024 / 1024).toFixed(2)} MB — click to change`
              : 'or click to browse — .pptx only, max 50 MB'}
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pptx"
          style={{ display: 'none' }}
          onChange={e => handleFilePick(e.target.files[0])}
        />

        <div style={{ marginTop: 16, display: 'flex', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <label className="field-label" htmlFor="template-name-input">Template Name</label>
            <input
              id="template-name-input"
              type="text"
              placeholder="e.g. Q1 Sales Deck"
              value={templateName}
              onChange={e => setTemplateName(e.target.value)}
            />
          </div>
          <button
            id="upload-submit-btn"
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={uploading || !pendingFile}
            style={{ height: 44, marginBottom: 1 }}
          >
            {uploading ? <><span className="spinner" /> Uploading…</> : <><span>📤</span> Upload</>}
          </button>
        </div>

        {uploadErr && <div className="alert alert-error" style={{ marginTop: 12 }}>⚠️ {uploadErr}</div>}
        {uploadOk  && <div className="alert alert-success" style={{ marginTop: 12 }}>✅ {uploadOk}</div>}
      </div>

      {/* Template Grid */}
      <div className="section">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            All Templates {!loading && `(${templates.length})`}
          </h2>
          <button id="refresh-templates-btn" className="btn btn-secondary btn-sm" onClick={load}>
            🔄 Refresh
          </button>
        </div>

        {loading && <div className="empty-state"><div className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} /></div>}
        {error   && <div className="alert alert-error">⚠️ {error}</div>}

        {!loading && !error && templates.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">📂</div>
            <div className="empty-title">No templates yet</div>
            <div className="empty-desc">Upload your first .pptx template above to get started.</div>
          </div>
        )}

        {!loading && templates.length > 0 && (
          <div className="template-grid">
            {templates.map(t => (
              <TemplateCard
                key={t.id}
                template={t}
                emoji={thumbFor(t.id)}
                onGenerate={() => navigate('generate', { templateId: t.id, templateName: t.name })}
                onReprofile={() => handleReprofile(t.id, t.name)}
                reprofiling={reprofilingId === t.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TemplateCard({ template: t, emoji, onGenerate, onReprofile, reprofiling }) {
  const date = t.created_at ? new Date(t.created_at).toLocaleDateString() : '—';

  return (
    <div className="template-card" id={`template-card-${t.id}`}>
      <div className="template-card-thumb">
        {emoji}
        {t.total_slides && (
          <span className="slide-count">🖼 {t.total_slides} slides</span>
        )}
      </div>
      <div className="template-card-body">
        <div className="template-card-name" title={t.name}>{t.name}</div>
        <div className="template-card-meta">
          <span className={`status-badge ${t.status}`}>{t.status}</span>
          <span style={{ flex: 1 }} />
          <span>{date}</span>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <button
            id={`reprofile-${t.id}`}
            className="btn btn-secondary btn-sm"
            style={{ flex: 1 }}
            onClick={onReprofile}
            disabled={reprofiling || t.status === 'analyzing'}
          >
            {reprofiling ? '⏳ Re-profiling…' : '♻️ Re-profile'}
          </button>
          <button
            id={`generate-from-${t.id}`}
            className="btn btn-primary btn-sm"
            style={{ flex: 1 }}
            onClick={onGenerate}
            disabled={t.status !== 'ready'}
          >
            ✨ Generate
          </button>
        </div>
      </div>
    </div>
  );
}

