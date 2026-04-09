import { useEffect, useRef, useState } from 'react';
import { listTemplates, startGeneration, subscribeToGeneration, downloadPresentation } from '../api.js';

const PIPELINE_STEPS = [
  { key: 'load_profile', name: 'Loading Template', desc: 'Fetching template profile and binary' },
  { key: 'plan_outline', name: 'Planning Outline', desc: 'Creating presentation structure' },
  { key: 'plan_single_slide', name: 'Planning Slides', desc: 'Generating and validating each slide' },
  { key: 'aggregate', name: 'Aggregating', desc: 'Combining slide outputs in order' },
  { key: 'aggregate_validation', name: 'Validating Deck', desc: 'Checking final deck-level constraints' },
  { key: 'render', name: 'Rendering PPTX', desc: 'Injecting content into template' },
  { key: 'store', name: 'Storing Result', desc: 'Saving file to GridFS' },
];

const STAGE_ORDER = ['queued', ...PIPELINE_STEPS.map((s) => s.key)];

function getCompletedSteps(stage) {
  if (!stage) return [];
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx <= 1) return [];
  return STAGE_ORDER.slice(1, idx);
}

export default function Generate({ navigate, context }) {
  const [templates, setTemplates] = useState([]);
  const [selectedId, setSelectedId] = useState(context?.templateId || '');
  const [prompt, setPrompt] = useState('');
  const [step, setStep] = useState(1); // 1=select, 2=prompt, 3=generating, 4=done

  const [genId, setGenId] = useState(null);
  const [genStatus, setGenStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const unsubRef = useRef(null);

  useEffect(() => {
    listTemplates()
      .then((ts) => setTemplates(ts.filter((t) => t.status === 'ready')))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (context?.templateId) {
      setSelectedId(context.templateId);
      setStep(2);
    }
  }, [context]);

  const handleStart = async () => {
    if (!selectedId) {
      setError('Please select a template.');
      return;
    }
    if (!prompt.trim()) {
      setError('Please enter a prompt.');
      return;
    }
    setError(null);
    setLoading(true);

    try {
      const { generation_id } = await startGeneration(selectedId, prompt.trim());
      setGenId(generation_id);
      setStep(3);
      setLoading(false);

      unsubRef.current = subscribeToGeneration(
        generation_id,
        (data) => {
          setGenStatus(data);
          if (data.status === 'completed' || data.status === 'failed') {
            unsubRef.current?.();
            setStep(4);
          }
        },
        () => {
          setStep(4);
        }
      );
    } catch (e) {
      setError(e.message);
      setLoading(false);
    }
  };

  // Cleanup SSE on unmount
  useEffect(() => () => unsubRef.current?.(), []);

  const handleReset = () => {
    unsubRef.current?.();
    setStep(1);
    setGenId(null);
    setGenStatus(null);
    setSelectedId('');
    setPrompt('');
    setError(null);
  };

  const selectedTemplate = templates.find((t) => t.id === selectedId);
  const currentStage = genStatus?.stage || genStatus?.current_step || '';
  const completedSteps = genStatus?.completed_steps || getCompletedSteps(currentStage);

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>✨ Generate Presentation</h1>
        <p>Choose a template, write your prompt, and let the AI build your deck.</p>
      </div>

      {/* Stepper */}
      <div className="stepper">
        {[
          { n: 1, label: 'Select Template' },
          { n: 2, label: 'Write Prompt' },
          { n: 3, label: 'Generating' },
          { n: 4, label: 'Download' },
        ].map((s, i, arr) => (
          <>
            <div key={s.n} className="step">
              <div className={`step-circle ${step === s.n ? 'active' : step > s.n ? 'done' : ''}`}>
                {step > s.n ? '✓' : s.n}
              </div>
              <span className={`step-label ${step === s.n ? 'active' : ''}`}>{s.label}</span>
            </div>
            {i < arr.length - 1 && <div key={`conn-${s.n}`} className="step-connector" />}
          </>
        ))}
      </div>

      {/* Step 1 — Select Template */}
      {step === 1 && (
        <div className="fade-in">
          <div className="card">
            <div className="card-title">📂 Select a Template</div>
            {templates.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📂</div>
                <div className="empty-title">No ready templates</div>
                <div className="empty-desc">Upload and analyze a template first.</div>
                <button className="btn btn-primary" onClick={() => navigate('templates')}>Go to Templates</button>
              </div>
            ) : (
              <div className="template-grid" style={{ marginTop: 4 }}>
                {templates.map((t) => (
                  <div
                    key={t.id}
                    id={`select-template-${t.id}`}
                    className={`template-card ${selectedId === t.id ? 'selected' : ''}`}
                    onClick={() => setSelectedId(t.id)}
                  >
                    <div className="template-card-thumb">
                      🎨
                      {selectedId === t.id && <span className="template-card-check">✓</span>}
                      {t.total_slides && <span className="slide-count">🖼 {t.total_slides}</span>}
                    </div>
                    <div className="template-card-body">
                      <div className="template-card-name">{t.name}</div>
                      <div className="template-card-meta">
                        <span className="status-badge ready">ready</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {templates.length > 0 && (
              <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  id="next-to-prompt-btn"
                  className="btn btn-primary"
                  disabled={!selectedId}
                  onClick={() => setStep(2)}
                >
                  Next →
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 2 — Prompt */}
      {step === 2 && (
        <div className="fade-in">
          <div className="card">
            <div className="card-title">✍️ Describe Your Presentation</div>

            {selectedTemplate && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  marginBottom: 20,
                  padding: '10px 14px',
                  background: 'rgba(108,99,255,0.08)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid rgba(108,99,255,0.2)',
                }}
              >
                <span style={{ fontSize: '1.2rem' }}>📂</span>
                <div>
                  <div
                    style={{
                      fontSize: '0.8rem',
                      color: 'var(--text-muted)',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                    }}
                  >
                    Template
                  </div>
                  <div style={{ fontSize: '0.875rem', fontWeight: 600 }}>{selectedTemplate.name}</div>
                </div>
                <button className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto' }} onClick={() => setStep(1)}>
                  Change
                </button>
              </div>
            )}

            <label className="field-label" htmlFor="prompt-input">Your Prompt</label>
            <textarea
              id="prompt-input"
              placeholder="e.g. Q1 business review for Good Sam RV Insurance highlighting revenue growth, top performing regions, and key initiatives for next quarter..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              style={{ minHeight: 160 }}
            />
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 6 }}>
              {prompt.length} / 8000 chars
            </div>

            {/* Example prompts */}
            <div style={{ marginTop: 16 }}>
              <div
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  color: 'var(--text-muted)',
                  marginBottom: 8,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                💡 Examples
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {[
                  'Q1 sales review with revenue trends and KPIs',
                  'Product launch deck for the new outdoor gear line',
                  'Annual investor update with financials and roadmap',
                ].map((ex) => (
                  <button
                    key={ex}
                    className="btn btn-secondary btn-sm"
                    onClick={() => setPrompt(ex)}
                    style={{ fontSize: '0.75rem' }}
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>

            {error && <div className="alert alert-error" style={{ marginTop: 16 }}>⚠️ {error}</div>}

            <div style={{ marginTop: 20, display: 'flex', gap: 12, justifyContent: 'space-between' }}>
              <button className="btn btn-secondary" onClick={() => setStep(1)}>← Back</button>
              <button
                id="generate-btn"
                className="btn btn-primary btn-lg"
                onClick={handleStart}
                disabled={loading || !prompt.trim()}
              >
                {loading ? (
                  <>
                    <span className="spinner" /> Starting…
                  </>
                ) : (
                  <>
                    <span>✨</span> Generate Presentation
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3 — Generating */}
      {step === 3 && (
        <div className="fade-in">
          <div className="card">
            <div className="card-title">⚙️ Generation In Progress</div>
            <div
              style={{
                fontSize: '0.8rem',
                fontFamily: 'monospace',
                color: 'var(--text-muted)',
                marginBottom: 20,
                wordBreak: 'break-all',
              }}
            >
              ID: {genId}
            </div>

            {genStatus && (
              <>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 8,
                  }}
                >
                  <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    {(currentStage || 'processing').replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>{genStatus.progress ?? '—'}%</span>
                </div>
                <div className="progress-track" style={{ marginBottom: 24 }}>
                  <div className="progress-fill" style={{ width: `${genStatus.progress ?? 0}%` }} />
                </div>
              </>
            )}

            {/* Pipeline steps */}
            <div className="pipeline-steps">
              {PIPELINE_STEPS.map((s) => {
                const isDone = completedSteps.includes(s.key);
                const isActive = currentStage === s.key;
                const isError = genStatus?.status === 'failed' && (isActive || currentStage === 'pipeline_error');

                return (
                  <div key={s.key} className="pipeline-step">
                    <div className={`step-dot ${isError ? 'error' : isDone ? 'done' : isActive ? 'active' : ''}`}>
                      {isError ? '✗' : isDone ? '✓' : isActive ? '●' : '○'}
                    </div>
                    <div className="pipeline-step-text">
                      <div
                        className="pipeline-step-name"
                        style={{
                          color: isActive ? 'var(--text-primary)' : isDone ? 'var(--success)' : 'var(--text-muted)',
                        }}
                      >
                        {s.name}
                      </div>
                      <div className="pipeline-step-desc">{s.desc}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            {!genStatus && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '16px',
                  color: 'var(--text-secondary)',
                  fontSize: '0.875rem',
                }}
              >
                <span
                  className="spinner"
                  style={{ borderTopColor: 'var(--accent-3)', borderColor: 'rgba(56,189,248,0.2)' }}
                />
                Connecting to event stream…
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 4 — Done */}
      {step === 4 && (
        <div className="fade-in">
          <div className="card" style={{ textAlign: 'center' }}>
            {genStatus?.status === 'completed' ? (
              <>
                <div style={{ fontSize: '4rem', marginBottom: 16 }}>🎉</div>
                <div
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: '1.5rem',
                    fontWeight: 700,
                    marginBottom: 8,
                  }}
                >
                  Presentation Ready!
                </div>
                <div style={{ color: 'var(--text-secondary)', marginBottom: 28 }}>
                  Your AI-generated .pptx is ready to download.
                </div>
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                  <button id="download-pptx-btn" className="btn btn-primary btn-lg" onClick={() => downloadPresentation(genId)}>
                    📥 Download PPTX
                  </button>
                  <button className="btn btn-secondary" onClick={handleReset}>
                    ✨ New Generation
                  </button>
                  <button className="btn btn-secondary" onClick={() => navigate('history')}>
                    🕒 View History
                  </button>
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: '3rem', marginBottom: 12 }}>❌</div>
                <div
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: '1.25rem',
                    fontWeight: 600,
                    marginBottom: 8,
                    color: 'var(--error)',
                  }}
                >
                  Generation Failed
                </div>
                <div style={{ color: 'var(--text-secondary)', marginBottom: 20 }}>
                  {genStatus?.error || 'An unexpected error occurred. Please try again.'}
                </div>
                <button className="btn btn-primary" onClick={handleReset}>Try Again</button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
