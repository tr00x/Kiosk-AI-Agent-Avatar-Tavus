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

const TOOL_LABELS = {
  verify_patient: 'Verifying identity...',
  get_today_appointment: 'Finding your appointment...',
  get_balance: 'Checking balance...',
  get_appointments: 'Looking up appointments...',
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

  // Stable refs for endCall/sendMessage (defined later by useTavusCall)
  const endCallRef = useRef(() => {});
  const sendMessageRef = useRef(() => {});

  // Listen for avatar video 'playing' event
  useEffect(() => {
    const el = document.getElementById('avatar-video');
    if (!el) return;
    const onPlaying = () => setVideoReady(true);
    el.addEventListener('playing', onPlaying);
    return () => el.removeEventListener('playing', onPlaying);
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
  }, []);

  // --- Tool result handler ---
  const handleToolResult = useCallback((toolName, result) => {
    setActivity(null); // clear activity indicator

    if (toolName === 'verify_patient') {
      setSearchingName(null); // hide pill-banner
      if (result?.verified) {
        setVerifiedName(result.name);
        setDashboardData(result); // renders PatientDashboard
      }
    }
    // All other tools: dashboard auto-fetches data, Jenny speaks the result.
    // No side panels needed.
  }, []);

  // Filter out system/tool messages from transcript display
  const handleTranscript = useCallback((entry) => {
    if (entry.role === 'user' && entry.text === 'OK') return;
    if (entry.role === 'user' && entry.text.startsWith('TOOL_RESULT')) return;
    setLatestTranscript({ ...entry, _ts: Date.now() });

    // Auto-end when Jenny says goodbye
    if (entry.role === 'assistant') {
      const lower = entry.text.toLowerCase();
      const goodbyePhrases = ['have a great day', 'have a wonderful day', 'have a good day', 'take care', 'goodbye', 'see you next time', 'see you soon', 'до свидания', 'хорошего дня', 'buen día', 'que tenga'];
      const isGoodbye = goodbyePhrases.some((p) => lower.includes(p));
      if (isGoodbye) {
        console.log('[Session] Goodbye detected, auto-ending in 4s');
        setTimeout(() => { endCallRef.current(); }, 4000);
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
    setVideoReady(false);
  }, [resetSession]);

  const handleSessionEnd = useCallback(() => {
    setTimeout(clearSession, 2500);
  }, [clearSession]);

  // --- Daily SDK hook ---
  const { endCall, sendMessage } = useTavusCall({
    conversationUrl,
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
    setVideoReady(false);
  }, [endCall, endSession, resetSession]);

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
            <Transcript transcript={latestTranscript} raised={!!dashboardData} />
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
            />
          )}

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
