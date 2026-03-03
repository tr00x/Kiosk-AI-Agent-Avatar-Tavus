/**
 * App — Root component and session state machine for the dental kiosk.
 *
 * States: idle → connecting → active → ended → idle
 */

import React, { useState, useCallback } from 'react';
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
  check_in_patient: 'Checking you in...',
  get_balance: 'Checking balance...',
  get_appointments: 'Looking up appointments...',
  book_appointment: 'Booking appointment...',
  send_sms_reminder: 'Sending reminder...',
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
    // All other tools: dashboard auto-fetches data, Emma speaks the result.
    // No side panels needed.
  }, []);

  // Filter out system/tool messages from transcript display
  const handleTranscript = useCallback((entry) => {
    if (entry.role === 'user' && entry.text === 'OK') return;
    if (entry.role === 'user' && entry.text.startsWith('TOOL_RESULT')) return;
    setLatestTranscript({ ...entry, _ts: Date.now() });
  }, []);

  const handleStatusChange = useCallback((newStatus) => {
    setCallStatus(newStatus);
  }, []);

  const handleSessionEnd = useCallback(() => {
    setTimeout(() => {
      resetSession();
      setLatestTranscript(null);
      setCallStatus('idle');
      setActivity(null);
      setVerifiedName(null);
      setDashboardData(null);
      setSearchingName(null);
    }, 4000);
  }, [resetSession]);

  // --- Daily SDK hook ---
  const { status: dailyStatus, endCall, sendMessage } = useTavusCall({
    conversationUrl,
    onToolCallStart: handleToolCallStart,
    onToolResult: handleToolResult,
    onTranscript: handleTranscript,
    onStatusChange: handleStatusChange,
    onSessionEnd: handleSessionEnd,
  });

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
  }, [endCall, endSession, resetSession]);

  const effectiveStatus = conversationUrl ? callStatus : (loading ? 'connecting' : 'idle');
  const sessionActive = !!conversationUrl && callStatus !== 'ended';
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
          <Transcript transcript={latestTranscript} />
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
              sendMessage={sendMessage}
            />
          )}

          <Controls
            sessionActive={sessionActive}
            loading={loading}
            onStart={handleStart}
            onStop={handleStop}
          />
        </>
      )}

      {/* Session ended overlay */}
      {callStatus === 'ended' && conversationUrl && (
        <div className="session-ended-overlay">
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
