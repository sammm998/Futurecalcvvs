// Server communication. Every call returns parsed JSON and throws on failure
// so callers can surface one consistent error path.

async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `${res.status} ${res.statusText}`);
  }
  return data;
}

export const api = {
  async progress() {
    const r = await fetch('/api/progress');
    return r.json();
  },

  /** Returns null while the pipeline is still extracting. */
  async document() {
    const r = await fetch('/api/document');
    if (r.status === 202) return null;
    if (!r.ok) throw new Error(`document: ${r.status}`);
    return r.json();
  },

  mergeRings:(rings) => post('/api/geometry/merge', { rings }),
  autoMerge: (rings) => post('/api/geometry/automerge', { rings }),
  ocrLabel:  (rect) => post('/api/ocr/label', { rect }),
  save:      (doc) => post('/api/save', doc),
  autosave:  (doc) => post('/api/autosave', doc),
  reassign:  (doc) => post('/api/reassign', doc),
  exportJSON:(doc) => post('/api/export/json', doc),
  exportPNG: (doc) => post('/api/export/png', doc),
  reset:     ()    => post('/api/reset', {}),
};
