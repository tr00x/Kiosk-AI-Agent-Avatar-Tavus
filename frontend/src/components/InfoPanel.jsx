/**
 * InfoPanel — Slide-in information panels (top-right).
 *
 * Color-coded by type with SVG icons:
 * - verified (green): Patient identity confirmed
 * - balance (blue): Account balance
 * - appointments (neutral): Upcoming appointments list
 * - confirmation (green): Booking confirmation
 * - sms (green): SMS sent
 * - error (red): Error messages
 */

import React, { useState, useEffect } from 'react';

const AUTO_HIDE_MS = {
  verified: 6000,
  today_appointment: 12000,
  checked_in: 8000,
  balance: 10000,
  appointments: 12000,
  confirmation: 10000,
  sms: 6000,
  info: 6000,
  error: 8000,
};

const PANEL_COLORS = {
  verified: '#22c55e',
  today_appointment: '#288d89',
  checked_in: '#22c55e',
  balance: '#3b82f6',
  appointments: '#94a3b8',
  confirmation: '#22c55e',
  sms: '#22c55e',
  info: '#94a3b8',
  error: '#ef4444',
};

const PANEL_TITLES = {
  verified: 'Identity Verified',
  today_appointment: "Today's Appointment",
  checked_in: 'Checked In',
  balance: 'Account Balance',
  appointments: 'Upcoming Appointments',
  confirmation: 'Booking Confirmed',
  sms: 'Reminder Sent',
  info: 'Info',
  error: 'Error',
};

let panelIdCounter = 0;

export default function InfoPanel({ panels, onDismiss }) {
  return (
    <div className="info-panel-stack">
      {panels.map((panel) => (
        <SinglePanel key={panel.id} panel={panel} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function SinglePanel({ panel, onDismiss }) {
  const [fading, setFading] = useState(false);
  const autoHide = AUTO_HIDE_MS[panel.type] || 8000;
  const borderColor = PANEL_COLORS[panel.type] || '#94a3b8';

  useEffect(() => {
    const fadeTimer = setTimeout(() => setFading(true), autoHide);
    const removeTimer = setTimeout(() => onDismiss?.(panel.id), autoHide + 600);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, [panel.id, autoHide, onDismiss]);

  return (
    <div
      className={`info-panel ${fading ? 'info-panel-fade' : ''}`}
      style={{ borderLeftColor: borderColor }}
    >
      {/* Header row */}
      <div className="info-panel-header">
        <PanelIcon type={panel.type} color={borderColor} />
        <span className="info-panel-title">{PANEL_TITLES[panel.type] || 'Info'}</span>
        <button className="info-panel-close" onClick={() => onDismiss?.(panel.id)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Auto-hide progress bar */}
      <div className="info-panel-progress" style={{ animationDuration: `${autoHide}ms` }} />

      {/* Panel body */}
      <div className="info-panel-body">
        <PanelContent panel={panel} />
      </div>
    </div>
  );
}

function PanelIcon({ type, color }) {
  const iconStyle = { color };
  switch (type) {
    case 'verified':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        </span>
      );
    case 'balance':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="1" x2="12" y2="23" />
            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
          </svg>
        </span>
      );
    case 'appointments':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
        </span>
      );
    case 'confirmation':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 11 12 14 22 4" />
            <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
          </svg>
        </span>
      );
    case 'sms':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </span>
      );
    case 'today_appointment':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
            <polyline points="9 16 11 18 15 14" />
          </svg>
        </span>
      );
    case 'checked_in':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        </span>
      );
    case 'info':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        </span>
      );
    case 'error':
      return (
        <span className="info-panel-icon" style={iconStyle}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </span>
      );
    default:
      return null;
  }
}

function PanelContent({ panel }) {
  switch (panel.type) {
    case 'verified':
      return (
        <div className="panel-verified">
          <span>Welcome, <strong>{panel.data?.name}</strong></span>
        </div>
      );

    case 'balance':
      return (
        <div className="panel-balance">
          <div className="balance-grid">
            <span>Total Charges:</span>
            <span className="balance-amount">${panel.data?.total_owed?.toFixed(2) || '0.00'}</span>
            <span>Insurance Estimate:</span>
            <span className="balance-insurance">-${panel.data?.insurance_pending?.toFixed(2) || '0.00'}</span>
          </div>
          <div className="balance-total-row">
            <span>Your Balance:</span>
            <span className="balance-final">${panel.data?.balance?.toFixed(2) || '0.00'}</span>
          </div>
        </div>
      );

    case 'appointments': {
      const apts = panel.data?.appointments || [];
      return (
        <div className="panel-appointments">
          {apts.length === 0 ? (
            <p className="panel-empty">No upcoming appointments.</p>
          ) : (
            <div className="appointment-list">
              {apts.map((apt, i) => (
                <div key={apt.id || i} className="appointment-card">
                  <div className="apt-type">{apt.type}</div>
                  <div className="apt-meta">
                    <span className="apt-datetime">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <polyline points="12 6 12 12 16 14" />
                      </svg>
                      {apt.date} at {apt.time}
                    </span>
                    <span className="apt-provider">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                        <circle cx="12" cy="7" r="4" />
                      </svg>
                      {apt.provider}
                    </span>
                  </div>
                  {apt.room && <div className="apt-room">Room {apt.room}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      );
    }

    case 'confirmation':
      return (
        <div className="panel-confirmation">
          <p className="conf-ref">Reference: <strong>{panel.data?.confirmation_number}</strong></p>
          <p className="conf-detail">{panel.data?.date} at {panel.data?.time}</p>
          <p className="panel-note">Staff will confirm your appointment shortly.</p>
        </div>
      );

    case 'sms':
      return (
        <div className="panel-sms">
          <span>Reminder sent to <strong>{panel.data?.phone}</strong></span>
        </div>
      );

    case 'today_appointment': {
      const apts = panel.data?.appointments || [];
      return (
        <div className="panel-today-appointment">
          {apts.map((apt, i) => (
            <div key={apt.appointment_id || i} className="today-apt-card">
              <div className="apt-type">{apt.type}</div>
              <div className="apt-meta">
                <span className="apt-datetime">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                  Today at {apt.time}
                </span>
                <span className="apt-provider">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                  {apt.provider}
                </span>
              </div>
              {apt.room && <div className="apt-room">Room {apt.room}</div>}
              {apt.already_checked_in && <div className="apt-checked-badge">Already checked in</div>}
            </div>
          ))}
        </div>
      );
    }

    case 'checked_in':
      return (
        <div className="panel-checked-in">
          <div className="checked-in-icon">&#10003;</div>
          <span>{panel.data?.message || "You're all set! Have a seat."}</span>
        </div>
      );

    case 'info':
      return (
        <div className="panel-info">
          <span>{panel.data?.message || ''}</span>
        </div>
      );

    case 'error':
      return (
        <div className="panel-error">
          <span>{panel.data?.message || 'Something went wrong.'}</span>
        </div>
      );

    default:
      return <div>{JSON.stringify(panel.data)}</div>;
  }
}

// Helper to create panel objects
export function createPanel(type, data) {
  return {
    id: ++panelIdCounter,
    type,
    data,
    timestamp: Date.now(),
  };
}
