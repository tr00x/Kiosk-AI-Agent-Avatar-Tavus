/**
 * Controls — End session button during active session.
 * Language toggle is only on IdleScreen (before session starts).
 */

import React from 'react';

export default function Controls({ sessionActive, loading, onStop }) {
  return (
    <div className="controls-bar">
      {/* Connecting indicator */}
      {loading && !sessionActive && (
        <div className="connecting-indicator">
          <div className="connecting-spinner" />
          <span>Connecting to Emma...</span>
        </div>
      )}

      {/* End session button */}
      {sessionActive && (
        <button className="btn-end-session" onClick={onStop}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
          End Session
        </button>
      )}
    </div>
  );
}
