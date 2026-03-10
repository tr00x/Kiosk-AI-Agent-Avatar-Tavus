/**
 * Transcript — Live speech transcript overlay.
 *
 * User utterances appear in green italic, bot in white.
 * Each line auto-fades after 5 seconds.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';

const FADE_TIMEOUT = 5000; // ms before a line starts fading
const MAX_LINES = 4;

let lineIdCounter = 0;

export default function Transcript({ transcript, raised }) {
  const [lines, setLines] = useState([]);
  const prevTranscriptRef = useRef(null);

  // Add new transcript entries
  useEffect(() => {
    if (!transcript || transcript === prevTranscriptRef.current) return;
    prevTranscriptRef.current = transcript;

    const id = ++lineIdCounter;
    const newLine = { id, ...transcript, fading: false };

    setLines((prev) => [...prev.slice(-(MAX_LINES - 1)), newLine]);

    // Start fade after timeout
    const fadeTimer = setTimeout(() => {
      setLines((prev) => prev.map((l) => (l.id === id ? { ...l, fading: true } : l)));
    }, FADE_TIMEOUT);

    // Remove after fade animation
    const removeTimer = setTimeout(() => {
      setLines((prev) => prev.filter((l) => l.id !== id));
    }, FADE_TIMEOUT + 800);

    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(removeTimer);
    };
  }, [transcript]);

  if (lines.length === 0) return null;

  return (
    <div className={`transcript-container ${raised ? 'transcript-raised' : ''}`}>
      {lines.map((line) => (
        <div
          key={line.id}
          className={`transcript-line ${line.role === 'user' ? 'transcript-user' : 'transcript-bot'} ${line.fading ? 'transcript-fade' : ''}`}
        >
          {line.text}
        </div>
      ))}
    </div>
  );
}
