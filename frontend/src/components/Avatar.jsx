/**
 * Avatar — Full-screen container for the Tavus avatar video stream.
 *
 * While connecting: shows looped idle video (jenny-idle.mp4) behind blur.
 * When live stream arrives: blur lifts, idle video hides.
 */

import React, { useState, useEffect } from 'react';

export default function Avatar({ status }) {
  const [videoReady, setVideoReady] = useState(false);

  useEffect(() => {
    const videoEl = document.getElementById('avatar-video');
    if (!videoEl) return;

    const onPlaying = () => setVideoReady(true);
    videoEl.addEventListener('playing', onPlaying);

    if (status === 'idle' || status === 'connecting') {
      setVideoReady(false);
    }

    return () => videoEl.removeEventListener('playing', onPlaying);
  }, [status]);

  const showIdle = !videoReady && status !== 'idle' && status !== 'error';

  return (
    <div className="avatar-container">
      {/* Idle placeholder: looped replica video behind blur */}
      {showIdle && (
        <video
          className="avatar-video avatar-video-idle"
          src="/jenny-idle.mp4"
          autoPlay
          loop
          muted
          playsInline
        />
      )}

      {/* Live avatar video (filled by Daily SDK track-started event) */}
      <video
        id="avatar-video"
        className={`avatar-video ${showIdle ? 'avatar-video-hidden' : ''}`}
        autoPlay
        playsInline
        muted={false}
      />
      <audio id="avatar-audio" autoPlay />

      {/* Connecting overlay on top of blurred idle video */}
      {showIdle && (
        <div className="avatar-overlay avatar-overlay-connecting">
          <div className="loading-spinner" />
          <p className="loading-text">Connecting to Jenny...</p>
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
