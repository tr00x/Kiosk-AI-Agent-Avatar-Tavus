/**
 * StatusDot — Connection status bar (top center).
 *
 * Shows connection state with colored dot + label.
 * When patient is verified, shows their name as a badge.
 */

import React from 'react';

const STATUS_CONFIG = {
  idle: { color: '#6b7280', label: 'Ready', icon: '○' },
  connecting: { color: '#f59e0b', label: 'Connecting…', pulse: true, icon: '◌' },
  listening: { color: '#22c55e', label: 'Listening', pulse: true, icon: '●' },
  processing: { color: '#3b82f6', label: 'Processing', pulse: true, icon: '◉' },
  error: { color: '#ef4444', label: 'Error', icon: '✕' },
  ended: { color: '#6b7280', label: 'Session Ended', icon: '○' },
};

export default function StatusDot({ status, verifiedName }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.idle;

  return (
    <div className="status-bar">
      <div className="status-bar-left">
        <div
          className={`status-dot ${config.pulse ? 'pulse' : ''}`}
          style={{ backgroundColor: config.color }}
        />
        <span className="status-label">{config.label}</span>
      </div>

      {verifiedName && (
        <div className="status-verified-badge">
          <svg className="status-verified-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <span>{verifiedName}</span>
        </div>
      )}
    </div>
  );
}
