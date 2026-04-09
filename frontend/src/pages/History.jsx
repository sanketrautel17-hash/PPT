import { useEffect, useState } from 'react';
import { downloadPresentation } from '../api.js';

const STORAGE_KEY = 'slideforge_history';

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
  catch { return []; }
}

export function saveToHistory(entry) {
  const history = loadHistory();
  history.unshift(entry);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(0, 50)));
}

export default function History({ navigate }) {
  const [history, setHistory] = useState([]);

  useEffect(() => { setHistory(loadHistory()); }, []);

  const clearHistory = () => {
    localStorage.removeItem(STORAGE_KEY);
    setHistory([]);
  };

  const humanDate = (iso) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1>🕒 Generation History</h1>
        <p>All past generation jobs tracked locally in your browser.</p>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16, gap: 12 }}>
        <button id="new-generation-btn" className="btn btn-primary btn-sm" onClick={() => navigate('generate')}>
          ✨ New Generation
        </button>
        {history.length > 0 && (
          <button id="clear-history-btn" className="btn btn-danger btn-sm" onClick={clearHistory}>
            🗑️ Clear History
          </button>
        )}
      </div>

      {history.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-icon">🕒</div>
            <div className="empty-title">No generation history yet</div>
            <div className="empty-desc">
              Start your first generation and it will appear here.
            </div>
            <button className="btn btn-primary" onClick={() => navigate('generate')}>
              ✨ Generate Now
            </button>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card-title">📋 Past Generations ({history.length})</div>
          <div className="history-list">
            {history.map((item, i) => (
              <div className="history-item" key={item.generation_id || i} id={`history-item-${i}`}>
                <div className="history-icon">
                  {item.status === 'completed' ? '✅' : item.status === 'failed' ? '❌' : '⚙️'}
                </div>
                <div className="history-info">
                  <div className="history-prompt" title={item.prompt}>{item.prompt}</div>
                  <div className="history-meta">
                    {item.templateName && <><span>📂 {item.templateName}</span> · </>}
                    <span>{humanDate(item.createdAt)}</span>
                    {item.generation_id && (
                      <span style={{ marginLeft: 6, fontFamily: 'monospace', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        #{item.generation_id.slice(-8)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="history-actions">
                  <span className={`status-badge ${item.status}`}>{item.status}</span>
                  {item.status === 'completed' && item.generation_id && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => downloadPresentation(item.generation_id)}
                    >
                      📥
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Info banner */}
      <div className="alert alert-info" style={{ marginTop: 20 }}>
        ℹ️ History is stored in your browser's local storage. Clearing cookies or browser data will remove it.
      </div>
    </div>
  );
}
