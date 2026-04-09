import { useState } from 'react';
import Sidebar from './components/Sidebar.jsx';
import Topbar from './components/Topbar.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Templates from './pages/Templates.jsx';
import Generate from './pages/Generate.jsx';
import History from './pages/History.jsx';

const PAGES = {
  dashboard: Dashboard,
  templates: Templates,
  generate: Generate,
  history: History,
};

export default function App() {
  const [page, setPage] = useState('dashboard');
  const [generateContext, setGenerateContext] = useState(null);

  const navigate = (p, ctx = null) => {
    setGenerateContext(ctx);
    setPage(p);
  };

  const PageComponent = PAGES[page] || Dashboard;

  return (
    <div className="app-shell">
      <Sidebar activePage={page} onNavigate={navigate} />
      <Topbar pageName={page} />
      <main className="main-content">
        <PageComponent navigate={navigate} context={generateContext} />
      </main>
    </div>
  );
}
