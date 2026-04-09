const PAGE_LABELS = {
  dashboard: 'Dashboard',
  templates: 'Templates',
  generate: 'Generate',
  history: 'History',
};

const NAV = [
  { id: 'dashboard', icon: '🏠', label: 'Dashboard' },
  { id: 'templates', icon: '📂', label: 'Templates' },
  { id: 'generate', icon: '✨', label: 'Generate' },
  { id: 'history', icon: '🕒', label: 'History' },
];

export default function Sidebar({ activePage, onNavigate }) {
  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-icon">🎯</div>
        <span className="logo-text">SlideForge</span>
      </div>

      {/* Nav */}
      <nav className="sidebar-nav">
        <div className="nav-label">Navigation</div>
        {NAV.map((item) => (
          <button
            key={item.id}
            id={`nav-${item.id}`}
            className={`nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-api-info">
          <span style={{ fontSize: '0.8rem' }}>🔗</span>
          <span className="api-url">
            {import.meta.env.VITE_API_URL || 'http://localhost:8000'}
          </span>
        </div>
      </div>
    </aside>
  );
}
