/**
 * Controls — End session button during active session.
 * Requires confirmation tap to prevent accidental session termination.
 */

import React, { useState, useEffect, useRef } from 'react';

const CONFIRM_TIMEOUT = 3000; // ms before confirmation resets

export default function Controls({ sessionActive, loading, onStop }) {
  const [confirming, setConfirming] = useState(false);
  const timerRef = useRef(null);

  const handleClick = () => {
    if (confirming) {
      setConfirming(false);
      onStop();
    } else {
      setConfirming(true);
      timerRef.current = setTimeout(() => setConfirming(false), CONFIRM_TIMEOUT);
    }
  };

  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, []);

  return (
    <div className="controls-bar">
      {sessionActive && (
        <button
          className={`btn-end-session ${confirming ? 'btn-end-confirm' : ''}`}
          onClick={handleClick}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
          {confirming ? 'Tap again to end' : 'End Session'}
        </button>
      )}
    </div>
  );
}
