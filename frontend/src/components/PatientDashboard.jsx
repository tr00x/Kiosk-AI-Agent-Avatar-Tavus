/**
 * PatientDashboard — Centered card showing all patient info after verification.
 *
 * Auto-fetches balance + appointments on mount (read-only).
 * Can minimize to a small pill bar with patient name.
 */

import React, { useState, useEffect, useRef } from 'react';

const API_BASE = '';

// --- SVG Icons ---
const IconVerified = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

const IconCalendar = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);

const IconClock = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const IconDoctor = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const IconDollar = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="1" x2="12" y2="23" />
    <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
  </svg>
);

const IconList = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="8" y1="6" x2="21" y2="6" />
    <line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" />
    <line x1="3" y1="6" x2="3.01" y2="6" />
    <line x1="3" y1="12" x2="3.01" y2="12" />
    <line x1="3" y1="18" x2="3.01" y2="18" />
  </svg>
);

export default function PatientDashboard({ data, conversationId, checkedIn, bookedAppointment, showCheckinOffer, sendMessage, autoMinimize }) {
  const [minimized, setMinimized] = useState(false);
  const [userExpanded, setUserExpanded] = useState(false);

  // Auto-minimize when BookingFlow takes over, unless user manually expanded
  useEffect(() => {
    if (autoMinimize && !userExpanded) {
      setMinimized(true);
    } else if (!autoMinimize) {
      setMinimized(false);
      setUserExpanded(false);
    }
  }, [autoMinimize]);
  const [balance, setBalance] = useState(null);
  const [balanceError, setBalanceError] = useState(false);
  const [appointments, setAppointments] = useState(null);
  const [appointmentsError, setAppointmentsError] = useState(false);
  const [checkinTapped, setCheckinTapped] = useState(false);

  const patientId = data?.patient_id;
  const patientName = data?.name || 'Patient';
  const searchedName = data?.searched_name;
  const matchMethod = data?.match_method || 'exact';
  const todayApt = data?.result === 'VERIFIED_HAS_APPOINTMENT' ? {
    id: data.appointment_id,
    type: data.appointment_type,
    time: data.appointment_time,
    provider: data.appointment_provider,
  } : null;

  const lastTapRef = useRef(0);
  const handleCheckinTap = () => {
    if (checkinTapped) return;
    const now = Date.now();
    if (now - lastTapRef.current < 800) return;
    lastTapRef.current = now;
    setCheckinTapped(true);
    sendMessage?.('Yes, please check me in');
  };

  // Auto-fetch balance on mount
  useEffect(() => {
    if (!patientId || !conversationId) return;
    fetch(`${API_BASE}/tools/get_balance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: conversationId,
        properties: { patient_id: patientId },
      }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res.result) setBalance(res.result);
        else setBalanceError(true);
      })
      .catch(() => setBalanceError(true));
  }, [patientId, conversationId]);

  // Auto-fetch upcoming appointments on mount
  useEffect(() => {
    if (!patientId || !conversationId) return;
    fetch(`${API_BASE}/tools/get_appointments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: conversationId,
        properties: { patient_id: patientId },
      }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res.result) setAppointments(res.result);
        else setAppointmentsError(true);
      })
      .catch(() => setAppointmentsError(true));
  }, [patientId, conversationId]);

  const showFuzzyHint = matchMethod !== 'exact' && searchedName &&
    searchedName.toLowerCase() !== patientName.toLowerCase();

  // --- Minimized pill ---
  if (minimized) {
    return (
      <div className="pd-pill-min" onClick={() => { setMinimized(false); setUserExpanded(true); }}>
        <span className="pd-pill-badge"><IconVerified /></span>
        <span className="pd-pill-name">{patientName}</span>
      </div>
    );
  }

  return (
    <div className="pd-card">
      {/* Header: Name + minimize */}
      <div className="pd-header">
        <div className="pd-name-block">
          <div className="pd-name-row">
            <span className="pd-verified-badge"><IconVerified /></span>
            <span className="pd-name">{patientName}</span>
          </div>
          {showFuzzyHint && (
            <div className="pd-fuzzy-hint">searched as "{searchedName}"</div>
          )}
        </div>
        <button className="pd-minimize" onClick={() => { setMinimized(true); setUserExpanded(false); }} title="Minimize">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12" /></svg>
        </button>
      </div>

      {/* Today's appointment */}
      {todayApt && (
        <div className="pd-section">
          <div className="pd-section-header">
            <IconCalendar />
            <span className="pd-section-title">Today's Appointment</span>
          </div>
          <div className={`pd-today-card ${checkedIn ? 'pd-today-card-checked' : ''}`}>
            {checkedIn && (
              <div className="pd-checkedin-badge">
                <IconVerified /> Checked in at {checkedIn.time}
              </div>
            )}
            <div className="pd-today-type">{todayApt.type}</div>
            <div className="pd-today-details">
              <span className="pd-today-detail"><IconClock /> {todayApt.time}</span>
              <span className="pd-today-detail"><IconDoctor /> {todayApt.provider}</span>
            </div>
            {showCheckinOffer && !checkedIn && !checkinTapped && (
              <button className="pd-checkin-btn" onClick={handleCheckinTap}>
                <IconVerified /> Check me in
              </button>
            )}
          </div>
        </div>
      )}

      {!todayApt && (
        <div className="pd-section">
          <div className="pd-section-header">
            <IconCalendar />
            <span className="pd-section-title">Today</span>
          </div>
          <div className="pd-empty">No appointment scheduled for today</div>
        </div>
      )}

      {/* Balance */}
      <div className="pd-section">
        <div className="pd-section-header">
          <IconDollar />
          <span className="pd-section-title">Balance</span>
        </div>
        {balanceError ? (
          <div className="pd-empty">Could not load balance</div>
        ) : balance === null ? (
          <div className="pd-loading">Loading...</div>
        ) : balance.balance === 0 ? (
          <div className="pd-balance-zero">No outstanding balance</div>
        ) : (
          <div className="pd-balance-grid">
            {balance.current_owed > 0 && (
              <div className="pd-bal-row">
                <span>Outstanding</span>
                <span>${balance.current_owed.toFixed(0)}</span>
              </div>
            )}
            {balance.estimated_upcoming > 0 && balance.estimated_upcoming !== balance.current_owed && (
              <div className="pd-bal-row">
                <span>Estimated charges</span>
                <span>${balance.estimated_upcoming.toFixed(0)}</span>
              </div>
            )}
            {balance.insurance_pending > 0 && (
              <div className="pd-bal-row pd-insurance">
                <span>Insurance est.</span>
                <span>-${balance.insurance_pending.toFixed(0)}</span>
              </div>
            )}
            <div className="pd-bal-row pd-bal-total">
              <span>Total</span>
              <span>${balance.balance.toFixed(0)}</span>
            </div>
          </div>
        )}
      </div>

      {/* Upcoming appointments */}
      <div className={`pd-section ${!bookedAppointment ? 'pd-section-last' : ''}`}>
        <div className="pd-section-header">
          <IconList />
          <span className="pd-section-title">Upcoming Appointments</span>
        </div>
        {appointmentsError ? (
          <div className="pd-empty">Could not load appointments</div>
        ) : appointments === null ? (
          <div className="pd-loading">Loading...</div>
        ) : !appointments.appointments?.length ? (
          <div className="pd-empty">No upcoming appointments</div>
        ) : (
          <div className="pd-apt-list">
            {appointments.appointments.map((apt, i) => (
              <div key={apt.id || i} className="pd-apt-item">
                <div className="pd-apt-item-type">{apt.type}</div>
                <div className="pd-apt-item-meta">
                  <span><IconClock /> {apt.date} at {apt.time}</span>
                  <span><IconDoctor /> {apt.provider}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {bookedAppointment && (
        <div className="pd-section pd-section-last">
          <div className="pd-section-header">
            <IconCalendar />
            <span className="pd-section-title">New Booking</span>
          </div>
          <div className="pd-today-card pd-today-card-checked">
            <div className="pd-checkedin-badge">
              <IconVerified /> Appointment Booked
            </div>
            <div className="pd-today-type">{bookedAppointment.type}</div>
            <div className="pd-today-details">
              <span className="pd-today-detail"><IconClock /> {bookedAppointment.date} at {bookedAppointment.time}</span>
            </div>
            <div className="pd-booking-note">Front desk will confirm your doctor</div>
          </div>
        </div>
      )}
    </div>
  );
}
