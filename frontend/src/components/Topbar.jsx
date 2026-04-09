import { useEffect, useState } from 'react';
import { getHealth } from '../api.js';

const PAGE_LABELS = {
  dashboard: 'Overview',
  templates: 'Template Library',
  generate: 'Generate Presentation',
  history: 'Generation History',
};

export default function Topbar({ pageName }) {
  const [healthy, setHealthy] = useState(null);

  useEffect(() => {
    getHealth()
      .then(() => setHealthy(true))
      .catch(() => setHealthy(false));
  }, []);

  return (
    <header className="topbar">
      <span className="topbar-title">{PAGE_LABELS[pageName] || pageName}</span>
      <span className="topbar-badge">
        {healthy === null && <><span className="dot" style={{ background: '#fbbf24' }} /> Connecting</>}
        {healthy === true  && <><span className="dot" /> API Online</>}
        {healthy === false && <><span className="dot" style={{ background: '#f87171' }} /> API Offline</>}
      </span>
    </header>
  );
}
