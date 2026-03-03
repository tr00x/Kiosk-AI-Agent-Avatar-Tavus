/**
 * useSession — Manages kiosk session lifecycle (start/end via backend API).
 */

import { useState, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '';

export function useSession() {
  const [conversationId, setConversationId] = useState(null);
  const [conversationUrl, setConversationUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const startSession = useCallback(async (language = 'en') => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_URL}/api/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }

      const data = await resp.json();
      setConversationId(data.conversation_id);
      setConversationUrl(data.conversation_url);
      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
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
    }
  }, [conversationId]);

  const resetSession = useCallback(() => {
    setConversationId(null);
    setConversationUrl(null);
    setError(null);
    setLoading(false);
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
