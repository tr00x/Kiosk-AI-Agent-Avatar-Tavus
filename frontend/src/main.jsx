import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import './index.css';

// Console helpers: examsheet("create") or examsheet("fill")
const _api = import.meta.env.VITE_API_URL || '';
window.examsheet = async (mode) => {
  if (!mode) {
    const r = await fetch(`${_api}/api/config`).then(r => r.json());
    console.log('Current mode:', r.exam_sheet_mode);
    return r.exam_sheet_mode;
  }
  const r = await fetch(`${_api}/api/config`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({exam_sheet_mode:mode})}).then(r=>r.json());
  console.log('Set to:', mode);
  return r;
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
