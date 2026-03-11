/**
 * useSession — Manages kiosk session lifecycle (start/end via backend API).
 */

import { useState, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '';
const SESSION_KEY = 'kiosk_session';

function loadSaved() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    // Expire saved sessions older than 10 minutes
    if (data.ts && Date.now() - data.ts > 10 * 60 * 1000) {
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
    return data;
  } catch { return null; }
}

function saveSession(id, url) {
  try {
    if (id && url) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ id, url, ts: Date.now() }));
    } else {
      sessionStorage.removeItem(SESSION_KEY);
    }
  } catch {}
}

export function useSession() {
  const saved = loadSaved();
  const [conversationId, setConversationId] = useState(saved?.id || null);
  const [conversationUrl, setConversationUrl] = useState(saved?.url || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const startSession = useCallback(async (language = 'en') => {
    // Prevent double-click: if already loading or have active session, bail
    if (loading) {
      console.warn('[Session] Start already in progress, ignoring');
      return;
    }
    if (conversationUrl) {
      console.warn('[Session] Session already active, ignoring');
      return;
    }

    setLoading(true);
    setError(null);

    const maxRetries = 2;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10000);
        const resp = await fetch(`${API_URL}/api/session/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ language }),
          signal: controller.signal,
        });
        clearTimeout(timeout);

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
          throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const data = await resp.json();
        setConversationId(data.conversation_id);
        setConversationUrl(data.conversation_url);
        saveSession(data.conversation_id, data.conversation_url);
        setLoading(false);
        return data;
      } catch (err) {
        if (attempt === maxRetries) {
          setError(err.message);
          setLoading(false);
          throw err;
        }
        console.warn(`[Session] Start attempt ${attempt + 1} failed, retrying...`);
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
  }, []);

  const endSession = useCallback(async () => {
    if (!conversationId) return;
    try {
      await fetch(`${API_URL}/api/session/end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: conversationId }),
      });
    } catch (err) {
      console.error('Failed to end session:', err);
    } finally {
      setConversationId(null);
      setConversationUrl(null);
      saveSession(null, null);
    }
  }, [conversationId]);

  const resetSession = useCallback(() => {
    setConversationId(null);
    setConversationUrl(null);
    setError(null);
    setLoading(false);
    saveSession(null, null);
  }, []);

  return {
    conversationId,
    conversationUrl,
    loading,
    error,
    startSession,
    endSession,
    resetSession,
  };
}
