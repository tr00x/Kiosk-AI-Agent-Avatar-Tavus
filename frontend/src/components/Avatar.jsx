/**
 * Avatar — Full-screen container for the Tavus avatar video stream.
 *
 * The actual video is attached by useTavusCall via document.getElementById('avatar-video').
 * This component provides the container, loading state, and error overlay.
 */

import React from 'react';

export default function Avatar({ status }) {
  return (
    <div className="avatar-container">
      {/* Remote avatar video (filled by Daily SDK track-started event) */}
      <video
        id="avatar-video"
        className="avatar-video"
        autoPlay
        playsInline
        muted={false}
      />
      {/* Hidden audio element for avatar speech */}
      <audio id="avatar-audio" autoPlay />

      {/* Loading overlay while connecting */}
      {status === 'connecting' && (
        <div className="avatar-overlay">
          <div className="loading-spinner" />
          <p className="loading-text">Connecting to Emma...</p>
        </div>
      )}

      {/* Error overlay */}
      {status === 'error' && (
        <div className="avatar-overlay avatar-overlay-error">
          <div className="error-icon">!</div>
          <p className="loading-text">Connection lost. Please try again.</p>
        </div>
      )}
    </div>
  );
}
