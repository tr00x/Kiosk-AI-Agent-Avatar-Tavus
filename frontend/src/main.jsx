import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import './index.css';

// Console helpers
const _api = import.meta.env.VITE_API_URL || '';
const _set = (k, v) => fetch(`${_api}/api/config`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({[k]:v})}).then(r=>r.json());
const _get = () => fetch(`${_api}/api/config`).then(r => r.json());

// examsheet("create") or examsheet("fill")
window.examsheet = async (mode) => {
  if (!mode) { const r = await _get(); console.log('Mode:', r.exam_sheet_mode); return r.exam_sheet_mode; }
  await _set('exam_sheet_mode', mode); console.log('Set to:', mode);
};

// printer("10.0.0.127") or printer("off")
window.printer = async (ip) => {
  if (!ip && ip !== '') { const r = await _get(); console.log('Printer:', r.printer_ip || 'off'); return r.printer_ip; }
  const val = ip === 'off' ? '' : ip;
  await _set('printer_ip', val); console.log(val ? 'Printer: ' + val : 'Printing disabled');
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
