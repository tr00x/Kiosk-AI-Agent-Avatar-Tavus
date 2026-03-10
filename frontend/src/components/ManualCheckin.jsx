/**
 * ManualCheckin — Staff sidebar for manual patient lookup & check-in.
 *
 * Hidden by default; toggled via a button on the left edge.
 * Search by last name + DOB, shows appointment cards with check-in button.
 * Auto-closes 2.5s after successful check-in. Auto-resets after 30s idle.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '';
const AUTO_RESET_MS = 30000;
const AUTO_CLOSE_AFTER_CHECKIN_MS = 2500;

export default function ManualCheckin() {
  const [open, setOpen] = useState(false);
  const [lastName, setLastName] = useState('');
  const [dob, setDob] = useState('');
  const [results, setResults] = useState(null);
  const [status, setStatus] = useState(null);
  const [message, setMessage] = useState('');
  const [searching, setSearching] = useState(false);
  const [checkinResult, setCheckinResult] = useState(null);
  const resetTimerRef = useRef(null);
  const closeTimerRef = useRef(null);

  // Auto-reset timer
  const resetTimer = useCallback(() => {
    if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    resetTimerRef.current = setTimeout(() => {
      setLastName('');
      setDob('');
      setResults(null);
      setStatus(null);
      setMessage('');
      setCheckinResult(null);
    }, AUTO_RESET_MS);
  }, []);

  const handleInteraction = useCallback(() => {
    resetTimer();
  }, [resetTimer]);

  // Auto-close after successful check-in
  useEffect(() => {
    if (checkinResult?.status === 'ok') {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
      closeTimerRef.current = setTimeout(() => {
        setOpen(false);
        // Reset form after closing animation
        setTimeout(() => {
          setLastName('');
          setDob('');
          setResults(null);
          setStatus(null);
          setMessage('');
          setCheckinResult(null);
        }, 400);
      }, AUTO_CLOSE_AFTER_CHECKIN_MS);
    }
    return () => {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    };
  }, [checkinResult]);

  // Search
  const handleSearch = async () => {
    handleInteraction();
    setSearching(true);
    setResults(null);
    setCheckinResult(null);
    try {
      // Convert date input value (YYYY-MM-DD) to MM/DD/YYYY for the backend
      let dobForApi = dob;
      if (dob && dob.includes('-')) {
        const [y, m, d] = dob.split('-');
        dobForApi = `${m}/${d}/${y}`;
      }
      const resp = await fetch(`${API_URL}/api/manual/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ last_name: lastName || null, dob: dobForApi || null }),
      });
      const data = await resp.json();
      setResults(data.results || []);
      setStatus(data.status);
      setMessage(data.message || '');
    } catch (err) {
      setStatus('error');
      setMessage('Search failed. Please try again.');
    } finally {
      setSearching(false);
    }
  };

  // Check-in
  const handleCheckin = async (aptNum) => {
    handleInteraction();
    try {
      const resp = await fetch(`${API_URL}/api/manual/checkin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ appointment_id: aptNum }),
      });
      const data = await resp.json();
      setCheckinResult({ aptNum, ...data });
    } catch (err) {
      setCheckinResult({ aptNum, status: 'error', message: 'Check-in failed.' });
    }
  };

  // Clear all
  const handleClear = () => {
    setLastName('');
    setDob('');
    setResults(null);
    setStatus(null);
    setMessage('');
    setCheckinResult(null);
  };

  // Submit on Enter key
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (lastName || dob)) {
      handleSearch();
    }
  };

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    };
  }, []);

  return (
    <>
      {/* Toggle button on left edge */}
      <button
        className={`sidebar-toggle ${open ? 'sidebar-toggle-open' : ''}`}
        onClick={() => { setOpen(!open); handleInteraction(); }}
        title="Staff Check-in"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="8.5" cy="7" r="4" />
          <line x1="20" y1="8" x2="20" y2="14" />
          <line x1="23" y1="11" x2="17" y2="11" />
        </svg>
      </button>

      {/* Sidebar panel */}
      <div className={`manual-sidebar ${open ? 'manual-sidebar-open' : ''}`}>
        {/* Header */}
        <div className="sidebar-header">
          <div className="sidebar-header-left">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="8.5" cy="7" r="4" />
              <line x1="20" y1="8" x2="20" y2="14" />
              <line x1="23" y1="11" x2="17" y2="11" />
            </svg>
            <h3 className="sidebar-title">Manual Check-in</h3>
          </div>
          <button className="sidebar-close-btn" onClick={() => setOpen(false)}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <p className="sidebar-desc">Search for today's patients by name or date of birth.</p>

        {/* Search form */}
        <div className="sidebar-form" onChange={handleInteraction}>
          <div className="sidebar-field">
            <label className="sidebar-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              Last Name
            </label>
            <input
              type="text"
              className="sidebar-input"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. Smith"
            />
          </div>

          <div className="sidebar-field">
            <label className="sidebar-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
              Date of Birth
            </label>
            <input
              type="date"
              className="sidebar-input sidebar-input-date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>

          <div className="sidebar-btn-row">
            <button
              className="sidebar-search-btn"
              onClick={handleSearch}
              disabled={searching || (!lastName && !dob)}
            >
              {searching ? (
                <>
                  <span className="sidebar-btn-spinner" />
                  Searching…
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                  Search
                </>
              )}
            </button>
            {(lastName || dob || results) && (
              <button className="sidebar-clear-btn" onClick={handleClear}>
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Status messages */}
        {(status === 'need_dob' || status === 'need_name') && (
          <div className="sidebar-message sidebar-message-warn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{message}</span>
          </div>
        )}
        {(status === 'ambiguous' || status === 'error') && (
          <div className="sidebar-message sidebar-message-error">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <span>{message}</span>
          </div>
        )}

        {/* Results count */}
        {results && results.length > 0 && (
          <div className="sidebar-results-header">
            <span className="sidebar-results-count">{results.length}</span>
            <span>appointment{results.length !== 1 ? 's' : ''} found</span>
          </div>
        )}

        {/* Results */}
        {results && results.length > 0 && (
          <div className="sidebar-results">
            {results.map((apt) => {
              const isCheckedIn = checkinResult?.aptNum === apt.apt_num && checkinResult?.status === 'ok';
              const checkInFailed = checkinResult?.aptNum === apt.apt_num && checkinResult?.status === 'error';
              return (
                <div key={apt.apt_num} className={`sidebar-card ${isCheckedIn ? 'sidebar-card-checked' : ''}`}>
                  <div className="sidebar-card-top">
                    <div className="sidebar-card-name">
                      {apt.first_name} {apt.last_name}
                    </div>
                    {isCheckedIn && (
                      <span className="sidebar-card-badge">✓ Arrived</span>
                    )}
                  </div>
                  <div className="sidebar-card-details">
                    <div className="sidebar-card-detail">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <polyline points="12 6 12 12 16 14" />
                      </svg>
                      {apt.time}
                    </div>
                    <div className="sidebar-card-detail">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                      </svg>
                      {apt.procedure}
                    </div>
                    <div className="sidebar-card-detail">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                        <circle cx="12" cy="7" r="4" />
                      </svg>
                      {apt.provider}
                    </div>
                    {apt.room && (
                      <div className="sidebar-card-detail">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                          <polyline points="9 22 9 12 15 12 15 22" />
                        </svg>
                        Room {apt.room}
                      </div>
                    )}
                  </div>
                  {!isCheckedIn && (
                    <button
                      className="sidebar-checkin-btn"
                      onClick={() => handleCheckin(apt.apt_num)}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      Check In
                    </button>
                  )}
                  {checkInFailed && (
                    <div className="sidebar-card-error">Check-in failed. Try again.</div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {results && results.length === 0 && status === 'ok' && (
          <div className="sidebar-empty">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <p>No appointments found for today.</p>
            <p className="sidebar-empty-hint">Try a different name or date of birth.</p>
          </div>
        )}
      </div>
    </>
  );
}
