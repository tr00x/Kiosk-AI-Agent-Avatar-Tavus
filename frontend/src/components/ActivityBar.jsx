/**
 * ActivityBar — Shows what the AI is currently doing (tool operations).
 *
 * Appears at the bottom-right with a spinner and label.
 * Smoothly animates in and out.
 */

import React, { useState, useEffect } from 'react';

const TOOL_LABELS = {
  verify_patient: 'Verifying identity...',
  get_balance: 'Checking balance...',
  get_appointments: 'Looking up appointments...',
  check_in_patient: 'Checking you in...',
  find_available_slots: 'Finding available times...',
  book_appointment: 'Booking appointment...',
  register_new_patient: 'Creating your account...',
  send_sms: 'Sending confirmation...',
};

export default function ActivityBar({ activity }) {
  const [visible, setVisible] = useState(false);
  const [currentActivity, setCurrentActivity] = useState(null);

  useEffect(() => {
    if (activity) {
      setCurrentActivity(activity);
      setVisible(true);
    } else {
      setVisible(false);
      const timer = setTimeout(() => setCurrentActivity(null), 400);
      return () => clearTimeout(timer);
    }
  }, [activity]);

  if (!currentActivity) return null;

  const label = currentActivity.label || TOOL_LABELS[currentActivity.tool] || 'Working...';

  return (
    <div className={`activity-bar ${visible ? 'activity-bar-in' : 'activity-bar-out'}`}>
      <div className="activity-spinner" />
      <span className="activity-label">{label}</span>
    </div>
  );
}
