import { useEffect, useState } from 'react';
import { listTemplates, getHealth } from '../api.js';

export default function Dashboard({ navigate }) {
  const [templates, setTemplates]   = useState([]);
  const [health, setHealth]         = useState(null);
  const [loading, setLoading]       = useState(true);

  useEffect(() => {
    Promise.all([listTemplates(), getHealth()])
      .then(([t, h]) => { setTemplates(t); setHealth(h); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const readyCount      = templates.filter(t => t.status === 'ready').length;
  const analyzingCount  = templates.filter(t => t.status === 'analyzing').length;

  const stats = [
    { icon: '📁', value: templates.length, label: 'Templates', gradient: 'linear-gradient(90deg,#6c63ff,#a78bfa)' },
    { icon: '✅', value: readyCount,        label: 'Ready',     gradient: 'linear-gradient(90deg,#34d399,#06b6d4)' },
    { icon: '⚙️', value: analyzingCount,   label: 'Analyzing', gradient: 'linear-gradient(90deg,#fbbf24,#f97316)' },
    { icon: '🤖', value: health ? health.llm_model || '—' : '—', label: 'LLM Model', gradient: 'linear-gradient(90deg,#f472b6,#e879f9)' },
  ];

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>Welcome to SlideForge 🎯</h1>
        <p>AI-powered presentation generation — upload a template, write a prompt, get a PPTX.</p>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        {stats.map((s, i) => (
          <div className="stat-card" key={i} style={{ '--accent-gradient': s.gradient }}>
            <span className="stat-icon">{s.icon}</span>
            <span className="stat-value">{loading ? '…' : s.value}</span>
            <span className="stat-label">{s.label}</span>
          </div>
        ))}
      </div>

      <div className="grid-2">
        {/* Quick Actions */}
        <div className="card">
          <div className="card-title">⚡ Quick Actions</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <button
              id="quick-generate"
              className="btn btn-primary btn-lg"
              style={{ justifyContent: 'flex-start' }}
              onClick={() => navigate('generate')}
            >
              <span>✨</span> New Generation
            </button>
            <button
              id="quick-upload"
              className="btn btn-secondary"
              style={{ justifyContent: 'flex-start' }}
              onClick={() => navigate('templates')}
            >
              <span>📤</span> Upload Template
            </button>
            <button
              id="quick-history"
              className="btn btn-secondary"
              style={{ justifyContent: 'flex-start' }}
              onClick={() => navigate('history')}
            >
              <span>🕒</span> View History
            </button>
          </div>
        </div>

        {/* API Status */}
        <div className="card">
          <div className="card-title">🔌 API Status</div>
          {health ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <StatusRow label="Database" value={health.db || 'connected'} ok />
              <StatusRow label="LLM Model" value={health.llm_model || 'configured'} ok />
              <StatusRow label="Guidance Model" value={health.guidance_model || 'configured'} ok />
              <StatusRow label="Max Upload" value={`${health.max_template_size_mb || 50} MB`} ok />
              <StatusRow label="Max Prompt" value={`${health.max_prompt_chars || 8000} chars`} ok />
              <StatusRow label="Slide Concurrency" value={health.slide_generation_concurrency || 4} ok />
            </div>
          ) : loading ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>Checking health…</div>
          ) : (
            <div className="alert alert-error">⚠️ Cannot reach backend at {import.meta.env.VITE_API_URL || 'http://localhost:8000'}</div>
          )}
        </div>
      </div>

      {/* How it works */}
      <div className="card" style={{ marginTop: 24 }}>
        <div className="card-title">📖 How It Works</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(175px, 1fr))', gap: 16 }}>
          {[
            { step: '1', icon: '📤', title: 'Upload Template', desc: 'Upload your branded .pptx as the design source of truth.' },
            { step: '2', icon: '✍️', title: 'Write a Prompt', desc: 'Describe the presentation you want in plain English.' },
            { step: '3', icon: '🤖', title: 'AI Plans Slides', desc: 'LangGraph pipeline plans content for each slide.' },
            { step: '4', icon: '📊', title: 'Download PPTX', desc: 'Receive a brand-consistent, editable .pptx file.' },
          ].map(s => (
            <div key={s.step} style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '16px', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 22, height: 22, borderRadius: '50%', background: 'var(--accent-1)', color: '#fff', fontSize: '0.7rem', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{s.step}</span>
                <span style={{ fontSize: '1.2rem' }}>{s.icon}</span>
              </div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.875rem' }}>{s.title}</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatusRow({ label, value, ok }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: '0.825rem', color: 'var(--text-secondary)' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: ok ? 'var(--success)' : 'var(--error)', display: 'inline-block' }} />
        <span style={{ fontSize: '0.78rem', fontFamily: 'monospace', color: 'var(--text-primary)' }}>{value}</span>
      </div>
    </div>
  );
}
