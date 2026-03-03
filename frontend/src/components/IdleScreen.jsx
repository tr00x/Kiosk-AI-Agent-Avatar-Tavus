/**
 * IdleScreen — Welcome screen shown when no session is active.
 *
 * Full-screen overlay with clinic branding, animated prompt, and start button.
 */

import React from 'react';

const LANGUAGES = [
  { code: 'en', label: 'EN' },
  { code: 'es', label: 'ES' },
  { code: 'ru', label: 'RU' },
];

export default function IdleScreen({ onStart, language, onLanguageChange }) {
  return (
    <div className="idle-screen">
      {/* Animated background with floating orbs */}
      <div className="idle-bg">
        <div className="idle-orb idle-orb-1" />
        <div className="idle-orb idle-orb-2" />
        <div className="idle-orb idle-orb-3" />
        <div className="idle-orb idle-orb-4" />
        <div className="idle-orb idle-orb-5" />
        <div className="idle-bg-noise" />
      </div>

      {/* Language toggle */}
      <div className="idle-lang">
        {LANGUAGES.map((lang) => (
          <button
            key={lang.code}
            className={`lang-btn ${language === lang.code ? 'lang-active' : ''}`}
            onClick={() => onLanguageChange?.(lang.code)}
          >
            {lang.label}
          </button>
        ))}
      </div>

      {/* Center content */}
      <div className="idle-content">
        <div className="idle-logo">
          <img
            src="/clinic-logo.jpg"
            alt="All Nassau Dental"
            className="idle-logo-img"
          />
        </div>

        <div className="idle-divider" />

        <h2 className="idle-greeting">
          {language === 'es' ? '¡Bienvenido!' : language === 'ru' ? 'Добро пожаловать!' : 'Welcome!'}
        </h2>
        <p className="idle-prompt">
          {language === 'es'
            ? 'Toque para registrarse con nuestro asistente'
            : language === 'ru'
              ? 'Нажмите для регистрации с нашим ассистентом'
              : 'Tap to check in with our AI assistant'}
        </p>

        <button className="idle-start-btn" onClick={onStart}>
          <span className="idle-start-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          </span>
          {language === 'es' ? 'Empezar' : language === 'ru' ? 'Начать' : 'Start Check-in'}
        </button>

        <div className="idle-hours">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          Mon–Thu 9AM–7PM &nbsp;|&nbsp; Fri 9AM–4PM &nbsp;|&nbsp; Sun 9AM–3PM
        </div>
      </div>

      {/* Bottom info */}
      <div className="idle-footer">
        <span>91 Clinton St, Hempstead, NY</span>
        <span className="idle-footer-dot">·</span>
        <span>(929) 822-4005</span>
        <span className="idle-footer-dot">·</span>
        <span>allnassaudental.com</span>
      </div>
    </div>
  );
}
