const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, options);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const j = await res.json(); msg = j.detail || JSON.stringify(j); } catch {}
    throw new Error(msg);
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res;
}

// ── Health ────────────────────────────────────────────────────────────────
export const getHealth = () => request('/api/health');

// ── Templates ─────────────────────────────────────────────────────────────
export const listTemplates = () => request('/api/templates');

export const getTemplate = (id) => request(`/api/templates/${id}`);

export const uploadTemplate = (file, name) => {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('name', name);
  return request('/api/templates/upload', { method: 'POST', body: fd });
};

export const reprofileTemplate = (id) =>
  request(`/api/templates/${id}/re-profile`, { method: 'POST' });

// ── Generate ──────────────────────────────────────────────────────────────
export const startGeneration = (templateId, prompt) =>
  request('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template_id: templateId, prompt }),
  });

export const getGenerationStatus = (id) => request(`/api/generate/${id}/status`);

export const getDownloadUrl = (id) => `${BASE_URL}/api/generate/${id}/download`;

export async function downloadPresentation(id) {
  const res = await fetch(`${BASE_URL}/api/generate/${id}/download`);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const j = await res.json(); msg = j.detail || JSON.stringify(j); } catch {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `presentation_${id}.pptx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── SSE stream for generation status ─────────────────────────────────────
export function subscribeToGeneration(id, onMessage, onError) {
  const es = new EventSource(`${BASE_URL}/api/generate/${id}/status`);

  es.addEventListener('progress', (e) => {
    try { onMessage(JSON.parse(e.data)); } catch {}
  });

  es.addEventListener('error', (e) => {
    try { onError?.(JSON.parse(e.data)); } catch { onError?.(null); }
  });

  es.onerror = () => { es.close(); onError?.(null); };

  return () => es.close();
}
