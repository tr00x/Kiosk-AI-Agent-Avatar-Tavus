/**
 * ActivityBar — Shows what the AI is currently doing (tool operations).
 *
 * Appears at the bottom-right with a spinner and label.
 * Auto-hides when activity is cleared.
 */

import React from 'react';

const TOOL_LABELS = {
  verify_patient: 'Verifying identity...',
  get_balance: 'Checking balance...',
  get_appointments: 'Looking up appointments...',
  book_appointment: 'Booking appointment...',
  send_sms_reminder: 'Sending reminder...',
};

export default function ActivityBar({ activity }) {
  if (!activity) return null;

  const label = activity.label || TOOL_LABELS[activity.tool] || 'Working...';

  return (
    <div className="activity-bar">
      <div className="activity-spinner" />
      <span className="activity-label">{label}</span>
    </div>
  );
}
