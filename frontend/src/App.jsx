/**
 * App — Root component and session state machine for the dental kiosk.
 *
 * States: idle → connecting → active → ended → idle
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useSession } from './hooks/useSession';
import { useTavusCall } from './hooks/useTavusCall';
import Avatar from './components/Avatar';
import StatusDot from './components/StatusDot';
import Transcript from './components/Transcript';
import Controls from './components/Controls';
import ManualCheckin from './components/ManualCheckin';
import ActivityBar from './components/ActivityBar';
import IdleScreen from './components/IdleScreen';
import PatientDashboard from './components/PatientDashboard';
import BookingFlow from './components/BookingFlow';

const TOOL_LABELS = {
  verify_patient: 'Verifying identity...',
  get_today_appointment: 'Finding your appointment...',
  get_balance: 'Checking balance...',
  get_appointments: 'Looking up appointments...',
  check_in_patient: 'Checking you in...',
  find_available_slots: 'Finding available times...',
  book_appointment: 'Booking your appointment...',
  create_patient: 'Setting up your account...',
};

export default function App() {
  const {
    conversationId,
    conversationUrl,
    loading,
    error: sessionError,
    startSession,
    endSession,
    resetSession,
  } = useSession();

  const [language, setLanguage] = useState('en');
  const [latestTranscript, setLatestTranscript] = useState(null);
  const [callStatus, setCallStatus] = useState('idle');
  const [activity, setActivity] = useState(null); // {tool, label}
  const [verifiedName, setVerifiedName] = useState(null);
  const [dashboardData, setDashboardData] = useState(null); // verify_patient result
  const [searchingName, setSearchingName] = useState(null); // pill-banner during verify
  const [videoReady, setVideoReady] = useState(false);
  const [checkedIn, setCheckedIn] = useState(null); // {appointmentId, time}
  const [bookedAppointment, setBookedAppointment] = useState(null); // {date, time, type}
  const [availableSlots, setAvailableSlots] = useState(null); // {date, slots, message}
  const [newPatientInfo, setNewPatientInfo] = useState(null); // partial patient data as collected
  const [showProcedurePicker, setShowProcedurePicker] = useState(false);
  const [showCheckinOffer, setShowCheckinOffer] = useState(false);
  const [showNotFound, setShowNotFound] = useState(false); // show "not found" card on 1st verify fail
  const [panelBottom, setPanelBottom] = useState(0); // top of visible panel in px from bottom
  const verifyFailCountRef = useRef(0); // track verify failures for progressive new-patient flow

  // Stable refs for endCall/sendMessage (defined later by useTavusCall)
  const endCallRef = useRef(() => {});
  const sendMessageRef = useRef(() => {});
  const videoReadyRef = useRef(false);

  // Listen for avatar video 'playing' event
  useEffect(() => {
    const el = document.getElementById('avatar-video');
    if (!el) return;
    const onPlaying = () => { setVideoReady(true); videoReadyRef.current = true; };
    el.addEventListener('playing', onPlaying);
    return () => el.removeEventListener('playing', onPlaying);
  }, []);

  // Track the top edge of whichever panel is visible (pd-card or bf-panel)
  useEffect(() => {
    const measure = () => {
      const panel = document.querySelector('.pd-card:not(.pd-pill-min)') || document.querySelector('.bf-panel');
      if (panel) {
        const rect = panel.getBoundingClientRect();
        setPanelBottom(window.innerHeight - rect.top);
      } else {
        setPanelBottom(0);
      }
    };
    const observer = new ResizeObserver(measure);
    const mutObserver = new MutationObserver(measure);
    mutObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    // Also measure on interval as fallback for animations
    const interval = setInterval(measure, 500);
    return () => { observer.disconnect(); mutObserver.disconnect(); clearInterval(interval); };
  }, []);

  // --- Tool call started (from hook) ---
  const handleToolCallStart = useCallback((toolName, args) => {
    setActivity({
      tool: toolName,
      label: TOOL_LABELS[toolName] || 'Working...',
    });

    // Show pill-banner with searched name during verification
    if (toolName === 'verify_patient' && args?.name) {
      setSearchingName(args.name);
    }

    // Capture new patient info as it's being collected
    if (toolName === 'create_patient') {
      setNewPatientInfo(prev => ({
        ...(prev || {}),
        first_name: args?.first_name || prev?.first_name,
        last_name: args?.last_name || prev?.last_name,
        dob: args?.dob || prev?.dob,
        phone: args?.phone || prev?.phone,
        insurance: args?.insurance || prev?.insurance,
      }));
    }
  }, []);

  // --- Tool result handler ---
  const handleToolResult = useCallback((toolName, result) => {
    setActivity(null); // clear activity indicator

    if (toolName === 'verify_patient') {
      setSearchingName(null); // hide pill-banner
      if (result?.verified) {
        verifyFailCountRef.current = 0;
        setVerifiedName(result.name);
        setDashboardData(result); // renders PatientDashboard
        if (result.appointment_id && result.result === 'VERIFIED_HAS_APPOINTMENT') {
          setShowCheckinOffer(true);
          setTimeout(() => sendMessageRef.current('SYSTEM_NOTE: Screen now shows patient dashboard with today\'s appointment and a "Check me in" button. Patient can tap it or say yes.'), 2000);
        }
        if (result.result === 'VERIFIED_NO_APPOINTMENT') {
          setShowProcedurePicker(true);
          setTimeout(() => sendMessageRef.current('SYSTEM_NOTE: Screen shows procedure type buttons (cleaning, cosmetic, root canal, extraction, implant). Patient can tap one or say it.'), 2000);
        }
      } else {
        verifyFailCountRef.current += 1;
        if (verifyFailCountRef.current === 1) {
          // 1st failure — show "not found" indicator, Jenny will ask to spell name
          setShowNotFound(true);
        } else if (verifyFailCountRef.current >= 2) {
          // 2nd failure — show new patient registration card with pre-filled name+DOB
          setShowNotFound(false);
          const nameParts = (result?.searched_name || '').trim().split(/\s+/);
          const firstName = nameParts[0] || '';
          const lastName = nameParts.slice(1).join(' ') || '';
          setNewPatientInfo(prev => ({
            ...(prev || {}),
            first_name: firstName,
            last_name: lastName,
            dob: result?.searched_dob || '',
          }));
          setTimeout(() => sendMessageRef.current('SYSTEM_NOTE: Screen now shows new patient registration card with name and DOB pre-filled. Phone and insurance fields are empty, waiting for patient to provide them.'), 2000);
        }
        // Do NOT show procedure picker on NOT_FOUND — Jenny handles retry/new-patient flow
      }
    }
    if (toolName === 'check_in_patient') {
      setShowCheckinOffer(false);
      if (result?.status === 'checked_in' || result?.status === 'already_checked_in') {
        setCheckedIn({
          appointmentId: result.appointment_id,
          time: result.checked_in_time || 'Earlier',
        });
        setTimeout(() => sendMessageRef.current('SYSTEM_NOTE: Screen shows green check-in badge. Patient is checked in.'), 2000);
      }
    }
    if (toolName === 'find_available_slots') {
      setShowProcedurePicker(false);
      if (result?.status === 'success') {
        const slots = result.slots || [];
        setAvailableSlots({ date: result.date, slots, message: result.message });
        const times = slots.map(s => s.time).join(', ');
        setTimeout(() => sendMessageRef.current(`SYSTEM_NOTE: Screen now shows ${slots.length} tappable time slots for ${result.date}: ${times}. Patient can tap a slot or say the time.`), 2000);
      } else if (result?.status === 'no_slots') {
        setAvailableSlots({ date: result.date || '', slots: [], message: result.message });
      }
    }
    if (toolName === 'create_patient') {
      if (result?.status === 'success') {
        setNewPatientInfo(prev => ({
          ...(prev || {}),
          patient_id: result.patient_id,
          name: result.name,
          insurance: result.insurance || prev?.insurance,
        }));
        // After account created, show procedure picker for booking
        setShowProcedurePicker(true);
        setTimeout(() => sendMessageRef.current('SYSTEM_NOTE: Patient account created. Screen shows procedure type buttons (cleaning, cosmetic, root canal, extraction, implant). Patient can tap one or say it.'), 2000);
      }
    }
    if (toolName === 'book_appointment') {
      if (result?.status === 'success') {
        setAvailableSlots(null);
        setNewPatientInfo(null);
        setBookedAppointment({
          date: result.date,
          time: result.time,
          type: result.procedure,
        });
        setTimeout(() => sendMessageRef.current(`SYSTEM_NOTE: Screen shows booking confirmation card: ${result.procedure} on ${result.date} at ${result.time}.`), 2000);
      }
    }
  }, []);

  // Mute avatar audio until video is playing, then unmute
  useEffect(() => {
    const audioEl = document.getElementById('avatar-audio');
    if (audioEl) audioEl.muted = !videoReady;
  }, [videoReady]);

  // Filter out system/tool messages from transcript display
  const handleTranscript = useCallback((entry) => {
    if (entry.role === 'user' && entry.text === 'OK') return;
    if (entry.role === 'user' && entry.text.startsWith('TOOL_RESULT')) return;
    if (entry.role === 'user' && entry.text.startsWith('SYSTEM_NOTE')) return;
    if (!videoReadyRef.current) return; // suppress transcript until avatar is visible
    setLatestTranscript({ ...entry, _ts: Date.now() });

    // Auto-end when Jenny says goodbye
    if (entry.role === 'assistant') {
      const lower = entry.text.toLowerCase();
      const goodbyePhrases = ['have a great day', 'have a wonderful day', 'have a good day', 'take care', 'goodbye', 'see you next time', 'see you soon', 'до свидания', 'хорошего дня', 'buen día', 'que tenga'];
      const isGoodbye = goodbyePhrases.some((p) => lower.includes(p));
      if (isGoodbye) {
        console.log('[Session] Goodbye detected, auto-ending in 10s');
        setTimeout(() => { endCallRef.current(); }, 10000);
      }
    }
  }, []);

  const handleStatusChange = useCallback((newStatus) => {
    setCallStatus(newStatus);
  }, []);

  const clearSession = useCallback(() => {
    resetSession();
    setLatestTranscript(null);
    setCallStatus('idle');
    setActivity(null);
    setVerifiedName(null);
    setDashboardData(null);
    setSearchingName(null);
    setVideoReady(false); videoReadyRef.current = false;
    setCheckedIn(null);
    setBookedAppointment(null);
    setAvailableSlots(null);
    setNewPatientInfo(null);
    setShowProcedurePicker(false);
    setShowCheckinOffer(false);
    setShowNotFound(false);
    verifyFailCountRef.current = 0;
  }, [resetSession]);

  const handleSessionEnd = useCallback(() => {
    setTimeout(clearSession, 2500);
  }, [clearSession]);

  // --- Daily SDK hook ---
  const { endCall, sendMessage } = useTavusCall({
    conversationUrl,
    dashboardData,
    onToolCallStart: handleToolCallStart,
    onToolResult: handleToolResult,
    onTranscript: handleTranscript,
    onStatusChange: handleStatusChange,
    onSessionEnd: handleSessionEnd,
  });

  // Keep refs in sync
  endCallRef.current = endCall;
  sendMessageRef.current = sendMessage;

  const sessionActive = !!conversationUrl && callStatus !== 'ended';

  // --- Inactivity guard: nudge after 15s, auto-end after 30s ---
  const lastActivityRef = useRef(Date.now());
  const nudgedRef = useRef(false);
  const inactivityRef = useRef(null);

  useEffect(() => {
    if (latestTranscript) {
      lastActivityRef.current = Date.now();
      nudgedRef.current = false;
    }
  }, [latestTranscript]);

  // Track touch/click as activity (not just transcript)
  useEffect(() => {
    const onInteraction = () => {
      lastActivityRef.current = Date.now();
      nudgedRef.current = false;
    };
    window.addEventListener('pointerdown', onInteraction);
    return () => window.removeEventListener('pointerdown', onInteraction);
  }, []);

  useEffect(() => {
    if (!sessionActive) {
      if (inactivityRef.current) clearInterval(inactivityRef.current);
      return;
    }
    lastActivityRef.current = Date.now();
    nudgedRef.current = false;

    inactivityRef.current = setInterval(() => {
      const idle = Date.now() - lastActivityRef.current;
      if (idle >= 30000) { endCallRef.current(); return; }
      if (idle >= 15000 && !nudgedRef.current) {
        nudgedRef.current = true;
        sendMessageRef.current('SYSTEM_NOTE: Patient is quiet. Ask if they need anything else, otherwise say goodbye.');
      }
    }, 5000);

    return () => clearInterval(inactivityRef.current);
  }, [sessionActive]);

  // --- Controls ---
  const handleStart = useCallback(async () => {
    try {
      await startSession(language);
    } catch (err) {
      console.error('Failed to start session:', err);
    }
  }, [startSession, language]);

  const handleStop = useCallback(async () => {
    endCall();
    await endSession();
    resetSession();
    setLatestTranscript(null);
    setCallStatus('idle');
    setActivity(null);
    setVerifiedName(null);
    setDashboardData(null);
    setSearchingName(null);
    setVideoReady(false); videoReadyRef.current = false;
    setCheckedIn(null);
    setBookedAppointment(null);
    setAvailableSlots(null);
    setNewPatientInfo(null);
    setShowProcedurePicker(false);
    setShowCheckinOffer(false);
    setShowNotFound(false);
    verifyFailCountRef.current = 0;
  }, [endCall, endSession, resetSession]);

  // Determine if BookingFlow has active content that should take over the screen
  const bookingFlowActive = !!availableSlots
    || (showProcedurePicker && !bookedAppointment)
    || (!!newPatientInfo && !newPatientInfo.patient_id)
    || (showNotFound && !dashboardData);

  const effectiveStatus = conversationUrl ? callStatus : (loading ? 'connecting' : 'idle');
  const showIdleScreen = !conversationUrl && !loading;

  return (
    <div className="kiosk-root">
      {/* Avatar video background */}
      <Avatar status={effectiveStatus} />

      {/* Idle/Welcome screen (shown when no session) */}
      {showIdleScreen && (
        <IdleScreen
          onStart={handleStart}
          language={language}
          onLanguageChange={setLanguage}
        />
      )}

      {/* Active session overlay */}
      {(sessionActive || loading) && (
        <>
          <StatusDot status={effectiveStatus} verifiedName={verifiedName} />
          {videoReady && (
            <Transcript
              transcript={latestTranscript}
              raised={
                (!!dashboardData && !bookingFlowActive) ||
                !!availableSlots ||
                !!newPatientInfo ||
                !!bookedAppointment ||
                showProcedurePicker ||
                showCheckinOffer ||
                showNotFound
              }
              panelBottom={panelBottom}
            />
          )}
          <ActivityBar activity={activity} />

          {/* Pill-banner: shows searched name during verify_patient */}
          {searchingName && (
            <div className="pd-pill-search">
              <span className="pd-pill-search-icon">&#128269;</span>
              Searching: "{searchingName}"...
            </div>
          )}

          {/* Patient Dashboard: centered card with all info */}
          {dashboardData && (
            <PatientDashboard
              data={dashboardData}
              conversationId={conversationId}
              checkedIn={checkedIn}
              bookedAppointment={bookedAppointment}
              showCheckinOffer={showCheckinOffer && !checkedIn}
              sendMessage={sendMessage}
              autoMinimize={bookingFlowActive}
            />
          )}

          {/* Booking flow: slots, registration, confirmation (hybrid voice+touch) */}
          <BookingFlow
            availableSlots={availableSlots}
            newPatientInfo={newPatientInfo}
            bookedAppointment={dashboardData ? null : bookedAppointment}
            showProcedurePicker={showProcedurePicker && !bookedAppointment}
            showCheckinOffer={showCheckinOffer && !checkedIn && !dashboardData}
            showNotFound={showNotFound && !newPatientInfo && !dashboardData}
            hasPatientDashboard={false}
            sendMessage={sendMessage}
          />

          <Controls
            sessionActive={sessionActive}
            loading={loading}
            onStop={handleStop}
          />
        </>
      )}

      {/* Session ended overlay — tap to dismiss */}
      {callStatus === 'ended' && conversationUrl && (
        <div className="session-ended-overlay" onClick={clearSession}>
          <div className="ended-icon">&#10003;</div>
          <h2>Thank you!</h2>
          <p>Have a great day at All Nassau Dental</p>
        </div>
      )}

      {/* Manual check-in sidebar (always available) */}
      <ManualCheckin />

      {/* Error toast */}
      {sessionError && (
        <div className="session-error-toast">
          <span className="error-toast-icon">&#9888;</span>
          {sessionError}
        </div>
      )}
    </div>
  );
}
