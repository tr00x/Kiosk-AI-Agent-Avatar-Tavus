/**
 * BookingFlow — Hybrid (voice + touch) overlay for the booking journey.
 *
 * Shows contextual panels:
 *   - Procedure type picker (tappable cards)
 *   - Available time slots (tappable grid)
 *   - New patient registration progress
 *   - Booking confirmation with confetti-style animation
 *
 * Touch interactions inject messages into the Tavus conversation via sendMessage,
 * so Jenny responds as if the patient said it out loud.
 */

import React, { useState, useEffect, useRef } from 'react';

// ─── Icons ───────────────────────────────────────────────────────
const IconClock = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const IconCalendar = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);

const IconUser = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const IconPhone = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
  </svg>
);

const IconShield = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

const IconCheck = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const IconSparkle = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

const IconTooth = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2C9.5 2 7.5 3.5 7 5.5C6.5 7.5 5 8 4 9C3 10 2.5 12 3 14C3.5 16 5 17 6 19C7 21 8 22 9 22C10 22 10.5 20 11 18C11.5 16 11.8 15 12 15C12.2 15 12.5 16 13 18C13.5 20 14 22 15 22C16 22 17 21 18 19C19 17 20.5 16 21 14C21.5 12 21 10 20 9C19 8 17.5 7.5 17 5.5C16.5 3.5 14.5 2 12 2Z" />
  </svg>
);

const IconScissors = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="6" cy="6" r="3" /><circle cx="6" cy="18" r="3" />
    <line x1="20" y1="4" x2="8.12" y2="15.88" /><line x1="14.47" y1="14.48" x2="20" y2="20" />
    <line x1="8.12" y1="8.12" x2="12" y2="12" />
  </svg>
);

const IconHeart = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20.42 4.58a5.4 5.4 0 0 0-7.65 0L12 5.36l-.77-.78a5.4 5.4 0 0 0-7.65 7.65l1.06 1.06L12 20.65l7.36-7.36 1.06-1.06a5.4 5.4 0 0 0 0-7.65z" />
  </svg>
);

const IconSearch = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const IconAlert = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const IconCheckin = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

// Procedure types for touch selection
const PROCEDURE_OPTIONS = [
  { key: 'cleaning', label: 'Cleaning & Exam', icon: <IconTooth />, message: 'I\'d like a routine cleaning and exam' },
  { key: 'cosmetic', label: 'Cosmetic', icon: <IconHeart />, message: 'I\'m interested in cosmetic services' },
  { key: 'root_canal', label: 'Root Canal', icon: <IconScissors />, message: 'I need a root canal' },
  { key: 'extraction', label: 'Extraction', icon: <IconAlert />, message: 'I need a tooth extraction' },
  { key: 'implant', label: 'Implant / Consult', icon: <IconSearch />, message: 'I need a consultation for tooth replacement' },
];

// ─── Component ───────────────────────────────────────────────────
export default function BookingFlow({
  availableSlots,      // { date, slots: [{time}], message } or null
  newPatientInfo,      // { first_name, last_name, dob, phone, insurance, patient_id } — partial
  bookedAppointment,   // { date, time, type, appointment_id } or null
  showProcedurePicker, // boolean — show procedure type cards
  showCheckinOffer,    // boolean — show "Check me in" button
  showNotFound,        // boolean — show "not found" card on 1st verify fail
  hasPatientDashboard, // whether main dashboard is showing (affects position)
  sendMessage,         // (text) => void — inject into Tavus conversation
  onCheckinTap,        // () => void — trigger check-in from touch
}) {
  const [minimized, setMinimized] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [tappedProcedure, setTappedProcedure] = useState(null);
  const [tappedCheckin, setTappedCheckin] = useState(false);
  const prevSlotsRef = useRef(null);

  // Reset on new slots
  useEffect(() => {
    if (availableSlots !== prevSlotsRef.current) {
      setSelectedSlot(null);
      setMinimized(false);
      prevSlotsRef.current = availableSlots;
    }
  }, [availableSlots]);

  // Expand on booking confirmed
  useEffect(() => {
    if (bookedAppointment) setMinimized(false);
  }, [bookedAppointment]);

  // Reset procedure picker when it hides
  useEffect(() => {
    if (!showProcedurePicker) setTappedProcedure(null);
  }, [showProcedurePicker]);

  // ─── Tap Handlers (debounced — prevent double-taps) ──────────
  const lastTapRef = useRef(0);
  const DEBOUNCE_MS = 800;

  const handleSlotTap = (time) => {
    if (selectedSlot) return; // already selected
    const now = Date.now();
    if (now - lastTapRef.current < DEBOUNCE_MS) return;
    lastTapRef.current = now;
    setSelectedSlot(time);
    sendMessage?.(`I'll take the ${time} slot`);
  };

  const handleProcedureTap = (proc) => {
    if (tappedProcedure) return; // already selected
    const now = Date.now();
    if (now - lastTapRef.current < DEBOUNCE_MS) return;
    lastTapRef.current = now;
    setTappedProcedure(proc.key);
    sendMessage?.(proc.message);
  };

  const handleCheckinTap = () => {
    if (tappedCheckin) return; // already tapped
    const now = Date.now();
    if (now - lastTapRef.current < DEBOUNCE_MS) return;
    lastTapRef.current = now;
    setTappedCheckin(true);
    sendMessage?.('Yes, please check me in');
  };

  // Nothing to show
  const hasContent = availableSlots || newPatientInfo || bookedAppointment || showProcedurePicker || showCheckinOffer || showNotFound;
  if (!hasContent) return null;

  const panelClass = `bf-panel ${hasPatientDashboard ? 'bf-panel-left' : 'bf-panel-center'}`;

  // ─── Booking Confirmation ──────────────────────────────────────
  if (bookedAppointment) {
    return (
      <div className={panelClass}>
        <div className="bf-card bf-confirmed">
          <div className="bf-confirmed-glow" />
          <div className="bf-confirmed-particles">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="bf-particle" style={{
                '--angle': `${i * 45}deg`,
                '--delay': `${i * 0.08}s`,
                '--distance': `${40 + (i % 3) * 15}px`,
              }} />
            ))}
          </div>
          <div className="bf-confirmed-icon">
            <IconCheck />
          </div>
          <div className="bf-confirmed-title">Appointment Booked</div>
          <div className="bf-confirmed-details">
            <div className="bf-confirmed-type">{bookedAppointment.type}</div>
            <div className="bf-confirmed-meta">
              <span><IconCalendar /> {bookedAppointment.date}</span>
              <span><IconClock /> {bookedAppointment.time}</span>
            </div>
          </div>
          <div className="bf-confirmed-note">Front desk will confirm your doctor</div>
        </div>
      </div>
    );
  }

  // ─── New Patient Registration ──────────────────────────────────
  // Show registration panel only if patient isn't created yet OR no other panels are active
  if (newPatientInfo && (!newPatientInfo.patient_id || (!availableSlots && !showProcedurePicker))) {
    const steps = [
      { key: 'name', label: 'Name', icon: <IconUser />, value: newPatientInfo.first_name ? `${newPatientInfo.first_name} ${newPatientInfo.last_name || ''}`.trim() : null },
      { key: 'dob', label: 'Date of Birth', icon: <IconCalendar />, value: newPatientInfo.dob },
      { key: 'phone', label: 'Phone', icon: <IconPhone />, value: newPatientInfo.phone },
      { key: 'insurance', label: 'Insurance', icon: <IconShield />, value: newPatientInfo.insurance },
    ];
    const completed = steps.filter(s => s.value).length;
    const isCreated = !!newPatientInfo.patient_id;

    return (
      <div className={panelClass}>
        <div className="bf-card bf-registration">
          <div className="bf-reg-header">
            <IconSparkle />
            <span className="bf-reg-title">New Patient</span>
            <span className="bf-reg-progress">{completed}/4</span>
          </div>

          <div className="bf-reg-bar">
            <div className="bf-reg-bar-fill" style={{ width: `${(completed / 4) * 100}%` }} />
          </div>

          <div className="bf-reg-steps">
            {steps.map((step, i) => (
              <div
                key={step.key}
                className={`bf-reg-step ${step.value ? 'bf-reg-step-done' : ''} ${!step.value && i === completed ? 'bf-reg-step-active' : ''}`}
                style={{ animationDelay: `${i * 0.08}s` }}
              >
                <div className="bf-reg-step-icon">
                  {step.value ? <IconCheck /> : step.icon}
                </div>
                <div className="bf-reg-step-content">
                  <div className="bf-reg-step-label">{step.label}</div>
                  {step.value && (
                    <div className="bf-reg-step-value">{step.value}</div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {isCreated && (
            <div className="bf-reg-created">
              <IconCheck /> Account created
            </div>
          )}
        </div>
      </div>
    );
  }

  // ─── Available Slots (tappable) ────────────────────────────────
  if (availableSlots) {
    if (minimized) {
      return (
        <div className="bf-pill" onClick={() => setMinimized(false)}>
          <IconClock />
          <span>{availableSlots.slots?.length || 0} available times</span>
        </div>
      );
    }

    return (
      <div className={panelClass}>
        <div className="bf-card bf-slots">
          <div className="bf-slots-header">
            <div className="bf-slots-title-row">
              <IconCalendar />
              <span className="bf-slots-title">Available Times</span>
              <button className="bf-minimize" onClick={() => setMinimized(true)} title="Minimize">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12" /></svg>
              </button>
            </div>
            <div className="bf-slots-date">{availableSlots.date}</div>
          </div>

          <div className="bf-slots-grid">
            {(availableSlots.slots || []).map((slot, i) => (
              <button
                key={slot.time}
                className={`bf-slot ${selectedSlot === slot.time ? 'bf-slot-selected' : ''}`}
                style={{ animationDelay: `${i * 0.06}s` }}
                onClick={() => handleSlotTap(slot.time)}
                disabled={!!selectedSlot}
              >
                <IconClock />
                <span>{slot.time}</span>
                {selectedSlot === slot.time && (
                  <div className="bf-slot-check"><IconCheck /></div>
                )}
              </button>
            ))}
          </div>

          {availableSlots.slots?.length === 0 && (
            <div className="bf-slots-empty">No openings on this day</div>
          )}

          <div className="bf-slots-hint">
            {selectedSlot
              ? `Selected ${selectedSlot}`
              : 'Tap a time or tell Jenny'}
          </div>
        </div>
      </div>
    );
  }

  // ─── Procedure Type Picker (tappable) ──────────────────────────
  if (showProcedurePicker) {
    return (
      <div className={panelClass}>
        <div className="bf-card bf-procedures">
          <div className="bf-proc-header">
            <IconCalendar />
            <span className="bf-proc-title">What type of appointment?</span>
          </div>
          <div className="bf-proc-grid">
            {PROCEDURE_OPTIONS.map((proc, i) => (
              <button
                key={proc.key}
                className={`bf-proc-btn ${tappedProcedure === proc.key ? 'bf-proc-btn-selected' : ''}`}
                style={{ animationDelay: `${i * 0.06}s` }}
                onClick={() => handleProcedureTap(proc)}
                disabled={!!tappedProcedure}
              >
                <div className="bf-proc-icon">{proc.icon}</div>
                <span className="bf-proc-label">{proc.label}</span>
                {tappedProcedure === proc.key && (
                  <div className="bf-proc-check"><IconCheck /></div>
                )}
              </button>
            ))}
          </div>
          <div className="bf-slots-hint">
            {tappedProcedure ? 'Got it!' : 'Tap or tell Jenny'}
          </div>
        </div>
      </div>
    );
  }

  // ─── Check-in Offer Button ─────────────────────────────────────
  if (showCheckinOffer && !tappedCheckin) {
    return (
      <div className={panelClass}>
        <button className="bf-checkin-btn" onClick={handleCheckinTap}>
          <div className="bf-checkin-icon"><IconCheckin /></div>
          <div className="bf-checkin-text">
            <span className="bf-checkin-label">Check me in</span>
            <span className="bf-checkin-sub">Tap or tell Jenny</span>
          </div>
          <div className="bf-checkin-ripple" />
        </button>
      </div>
    );
  }

  // ─── Not Found Card ──────────────────────────────────────────────
  if (showNotFound) {
    return (
      <div className={panelClass}>
        <div className="bf-card bf-not-found">
          <div className="bf-nf-icon">
            <IconSearch />
          </div>
          <div className="bf-nf-title">No record found</div>
          <div className="bf-nf-sub">Let's try once more — please spell your last name</div>
          <div className="bf-nf-dots">
            <span className="bf-nf-dot" style={{ animationDelay: '0s' }} />
            <span className="bf-nf-dot" style={{ animationDelay: '0.2s' }} />
            <span className="bf-nf-dot" style={{ animationDelay: '0.4s' }} />
          </div>
        </div>
      </div>
    );
  }

  return null;
}
