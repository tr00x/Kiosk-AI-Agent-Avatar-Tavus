/**
 * useTavusCall — Core hook managing Daily.co WebRTC connection for Tavus CVI.
 *
 * Connects to the conversation URL, listens for Tavus app-message events,
 * and exposes status + transcript + tool results to the UI.
 *
 * KEY INSIGHT: Tavus does NOT feed webhook URL responses back to the LLM.
 * Tool results must be injected via conversation.respond from the client.
 * We call our backend API, get the result, update UI, and inject the result
 * into the conversation so the LLM can act on it.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import DailyIframe from '@daily-co/daily-js';

// Base URL for backend API — uses Vite proxy in dev
const API_BASE = '';

/**
 * Call our own backend tool endpoint with retry on network errors.
 */
async function fetchToolResult(toolName, conversationId, args, retries = 2) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      const res = await fetch(`${API_BASE}/tools/${toolName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          properties: args,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!res.ok) throw new Error(`Tool ${toolName} HTTP ${res.status}`);
      const data = await res.json();
      return data.result || data;
    } catch (err) {
      if (attempt === retries) throw err;
      console.warn(`[Tool] ${toolName} attempt ${attempt + 1} failed, retrying...`);
      await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
    }
  }
}

/**
 * Format a tool result into a concise text message for the LLM.
 * This message is injected via conversation.respond so the LLM sees
 * the actual tool result in the conversation context.
 */
function formatToolResultMessage(toolName, result) {
  switch (toolName) {
    case 'verify_patient':
      if (result.verified) {
        let msg = `TOOL_RESULT verify_patient: ${result.say_this || 'Patient verified.'}`;
        msg += ` [patient_id=${result.patient_id}]`;
        if (result.appointment_id) {
          msg += ` [appointment_id=${result.appointment_id}]`;
        }
        return msg;
      }
      if (result.reason === 'need_phone') {
        return `TOOL_RESULT verify_patient: NEED_PHONE. I found a few records with that name and date of birth. Ask the patient for the last four digits of their phone number, then call verify_patient again with the same name, dob, and phone_last4.`;
      }
      return `TOOL_RESULT verify_patient: NOT_FOUND. ${result.message || 'Patient not found with that name and date of birth.'}`;

    case 'get_today_appointment':
      if (result.status === 'found' && result.appointments?.length) {
        const a = result.appointments[0];
        return `TOOL_RESULT get_today_appointment: FOUND. ${a.type} at ${a.time} with ${a.provider}. Room: ${a.room || 'TBD'}. Already checked in: ${a.already_checked_in ? 'yes' : 'no'}. [appointment_id=${a.appointment_id}]`;
      }
      return `TOOL_RESULT get_today_appointment: NO_APPOINTMENT. No appointment found for today.`;

    case 'get_balance':
      if (result.status === 'success') {
        return `TOOL_RESULT get_balance: Balance is $${result.balance}. Insurance pending: $${result.insurance_pending}. ${result.message}`;
      }
      return `TOOL_RESULT get_balance: ERROR. ${result.message || 'Could not retrieve balance.'}`;

    case 'get_appointments':
      if (result.status === 'success' && result.appointments?.length) {
        const list = result.appointments
          .map((a) => `${a.type} on ${a.date} at ${a.time} with ${a.provider}`)
          .join('; ');
        return `TOOL_RESULT get_appointments: ${result.appointments.length} upcoming: ${list}`;
      }
      if (result.status === 'success') {
        return `TOOL_RESULT get_appointments: No upcoming appointments scheduled.`;
      }
      return `TOOL_RESULT get_appointments: ERROR. ${result.message || 'Could not retrieve appointments.'}`;

    case 'check_in_patient':
      if (result.status === 'checked_in') {
        return `TOOL_RESULT check_in_patient: SUCCESS. Patient checked in. Arrival time recorded. Tell them they're all set and to have a seat.`;
      }
      if (result.status === 'already_checked_in') {
        return `TOOL_RESULT check_in_patient: ALREADY_CHECKED_IN. ${result.message}`;
      }
      return `TOOL_RESULT check_in_patient: ERROR. ${result.message || 'Check-in failed.'} Direct patient to the front desk.`;

    case 'find_available_slots':
      if (result.status === 'success' && result.slots?.length) {
        const times = result.slots.map(s => s.time).join(', ');
        return `TOOL_RESULT find_available_slots: FOUND ${result.slots.length} slots on ${result.date}: ${times}. Present these times to the patient and ask which one works.`;
      }
      if (result.status === 'no_slots') {
        return `TOOL_RESULT find_available_slots: NO_SLOTS. ${result.message} Ask patient to try another date.`;
      }
      return `TOOL_RESULT find_available_slots: ERROR. ${result.message || 'Could not check availability.'} Suggest patient ask the front desk.`;

    case 'book_appointment':
      if (result.status === 'success') {
        return `TOOL_RESULT book_appointment: SUCCESS. Booked ${result.procedure} on ${result.date} at ${result.time}. Appointment ID: ${result.appointment_id}. Tell patient they're booked and the front desk will confirm their doctor.`;
      }
      return `TOOL_RESULT book_appointment: ERROR. ${result.message || 'Booking failed.'} Direct patient to the front desk.`;

    case 'create_patient':
      if (result.status === 'success') {
        const ins = result.insurance && result.insurance.toLowerCase() !== 'none' ? ` Insurance: ${result.insurance}.` : ' No insurance.';
        return `TOOL_RESULT create_patient: SUCCESS. New patient created. [patient_id=${result.patient_id}] Name: ${result.name}.${ins} Insurance already collected — do NOT ask again. Now proceed with booking using this patient_id.`;
      }
      return `TOOL_RESULT create_patient: ERROR. ${result.message || 'Could not create patient record.'} Direct patient to the front desk.`;

    default:
      return `TOOL_RESULT ${toolName}: This feature is not available. The front desk will help with that.`;
  }
}


export function useTavusCall({
  conversationUrl,
  dashboardData,
  onToolCallStart,
  onToolResult,
  onTranscript,
  onStatusChange,
  onSessionEnd,
}) {
  const callRef = useRef(null);
  const dashboardDataRef = useRef(dashboardData);
  dashboardDataRef.current = dashboardData;
  const [status, setStatus] = useState('idle');

  // Deduplicate events — Tavus/Daily can send same event up to 4x
  const seenEventsRef = useRef(new Set());
  // Track in-flight tool calls (prevent concurrent duplicate calls)
  const inflightToolsRef = useRef(new Set());
  // Cooldown: tool name → timestamp. Prevents immediate re-calls (10s window).
  const toolCooldownRef = useRef(new Map());
  // Track Jenny's speaking state to avoid interrupting her
  const speakingRef = useRef(false);
  // Queue of messages to inject after Jenny stops speaking
  const pendingInjectionsRef = useRef([]);
  // Track intentional leave to prevent reconnect attempts
  const intentionalLeaveRef = useRef(false);

  const updateStatus = useCallback((newStatus) => {
    setStatus(newStatus);
    onStatusChange?.(newStatus);
  }, [onStatusChange]);

  // Inject a message into the conversation, queuing if Jenny is speaking
  const injectOrQueue = useCallback((call, msg) => {
    if (speakingRef.current) {
      console.log('[Tavus] Jenny speaking, queuing injection:', msg.substring(0, 60));
      pendingInjectionsRef.current.push({ call, msg });
    } else {
      console.log('[Tavus] Injecting immediately:', msg.substring(0, 60));
      call.sendAppMessage({
        message_type: 'conversation',
        event_type: 'conversation.respond',
        properties: { text: msg },
      }, '*');
    }
  }, []);

  // Flush queued injections when Jenny stops speaking (with delay to avoid
  // interrupting her next sentence — stopped_speaking fires between sentences too)
  const flushTimerRef = useRef(null);
  const flushPendingInjections = useCallback((call) => {
    if (pendingInjectionsRef.current.length === 0) return;
    // Cancel any pending flush — Jenny might start speaking again
    if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    flushTimerRef.current = setTimeout(() => {
      // Double-check Jenny isn't speaking again
      if (speakingRef.current) return;
      const pending = [...pendingInjectionsRef.current];
      pendingInjectionsRef.current = [];
      for (const item of pending) {
        console.log('[Tavus] Flushing queued injection:', item.msg.substring(0, 60));
        item.call.sendAppMessage({
          message_type: 'conversation',
          event_type: 'conversation.respond',
          properties: { text: item.msg },
        }, '*');
      }
    }, 1500);
  }, []);

  useEffect(() => {
    if (!conversationUrl) return;

    let destroyed = false;
    seenEventsRef.current.clear();
    inflightToolsRef.current.clear();
    toolCooldownRef.current.clear();

    const setupCall = async () => {
      try {
        updateStatus('connecting');

        const call = DailyIframe.createCallObject({
          videoSource: false,
        });

        callRef.current = call;

        call.on('joined-meeting', () => {
          if (!destroyed) updateStatus('listening');
        });

        // left-meeting is handled above with reconnection logic

        call.on('error', (event) => {
          console.error('[Daily] Error:', event);
          if (!destroyed) updateStatus('error');
        });

        // Network quality — warn on degradation
        call.on('network-quality-change', (event) => {
          const quality = event?.threshold;
          console.log('[Daily] Network quality:', quality);
          if (quality === 'very-low' && !destroyed) {
            console.warn('[Daily] Very low network quality detected');
          }
        });

        // WebRTC reconnection — Daily fires these on network blips
        call.on('nonfatal-error', (event) => {
          console.warn('[Daily] Non-fatal error:', event?.type, event?.errorMsg);
        });

        let reconnectAttempts = 0;
        const MAX_RECONNECT = 3;

        call.on('network-connection', (event) => {
          const type = event?.type;
          console.log('[Daily] Network connection:', type);
          if (type === 'interrupted' && !destroyed) {
            updateStatus('connecting'); // show reconnecting state
          }
          if (type === 'connected' && !destroyed) {
            reconnectAttempts = 0;
            updateStatus('listening');
          }
        });

        // If Daily fully disconnects, attempt rejoin
        call.on('left-meeting', async () => {
          if (destroyed || intentionalLeaveRef.current) {
            updateStatus('ended');
            onSessionEnd?.();
            return;
          }
          // Accidental disconnect — try to rejoin
          if (reconnectAttempts < MAX_RECONNECT) {
            reconnectAttempts++;
            console.log(`[Daily] Unexpected disconnect, reconnect attempt ${reconnectAttempts}/${MAX_RECONNECT}`);
            updateStatus('connecting');
            try {
              await new Promise(r => setTimeout(r, 1000 * reconnectAttempts));
              if (!destroyed) {
                await call.join({ url: conversationUrl });
                console.log('[Daily] Reconnected successfully');
                reconnectAttempts = 0;
              }
            } catch (err) {
              console.error('[Daily] Reconnect failed:', err);
              if (reconnectAttempts >= MAX_RECONNECT && !destroyed) {
                updateStatus('error');
                onSessionEnd?.();
              }
            }
          } else {
            updateStatus('ended');
            onSessionEnd?.();
          }
        });

        // Remote participant left (Tavus replica disconnected)
        call.on('participant-left', (event) => {
          if (event.participant?.local) return;
          console.warn('[Daily] Remote participant left');
          if (!destroyed) {
            updateStatus('ended');
            onSessionEnd?.();
          }
        });

        // Track remote video (the Tavus avatar)
        call.on('track-started', (event) => {
          if (event.participant?.local) return;
          const { track, type } = event;
          if (type === 'video') {
            const videoEl = document.getElementById('avatar-video');
            if (videoEl && track) {
              videoEl.srcObject = new MediaStream([track]);
              videoEl.play().catch(() => {});
            }
          }
          if (type === 'audio') {
            const audioEl = document.getElementById('avatar-audio');
            if (audioEl && track) {
              audioEl.srcObject = new MediaStream([track]);
              audioEl.play().catch(() => {});
            }
          }
        });

        // --- Tavus app-message events ---
        call.on('app-message', (event) => {
          if (destroyed) return;

          const data = event?.data;
          if (!data) return;

          const eventType = data.event_type || data.type || '';
          const inferenceId = data.inference_id || '';
          const properties = data.properties || data;

          // --- Deduplication ---
          const role = properties.role || '';
          const dedupKey = `${eventType}:${inferenceId || properties.attempt || ''}:${role}`;
          if (seenEventsRef.current.has(dedupKey)) return;
          seenEventsRef.current.add(dedupKey);
          if (seenEventsRef.current.size > 500) {
            const entries = [...seenEventsRef.current];
            seenEventsRef.current = new Set(entries.slice(-200));
          }

          // Skip noisy pings
          if (eventType === 'system.replica_present') return;

          console.log('[Tavus]', eventType, inferenceId ? `(${inferenceId.slice(0, 8)})` : '');

          // ===============================================================
          // TOOL CALL HANDLING
          // ===============================================================
          if (eventType === 'conversation.tool_call') {
            const toolName = properties.tool_name || properties.name || '';
            let args = {};
            try {
              args = typeof properties.arguments === 'string'
                ? JSON.parse(properties.arguments)
                : (properties.arguments || {});
            } catch (e) {
              console.warn('[Tavus] Failed to parse tool args:', e);
            }

            const conversationId = data.conversation_id || '';

            if (!toolName) {
              console.warn('[Tavus] Received tool_call without tool name, skipping');
              return;
            }

            console.log('[Tavus] Tool call:', toolName, JSON.stringify(args));

            // Guard: skip if in-flight (concurrent duplicate)
            if (inflightToolsRef.current.has(toolName)) {
              console.log('[Tavus] Skipping duplicate tool call:', toolName, '(in-flight)');
              return;
            }

            // Guard: cooldown — prevent immediate re-calls within 10s after success
            const lastCall = toolCooldownRef.current.get(toolName);
            if (lastCall && Date.now() - lastCall < 10000) {
              console.log('[Tavus] Skipping tool call:', toolName, '(cooldown, last called', Date.now() - lastCall, 'ms ago)');
              return;
            }

            // Override LLM-hallucinated IDs with real ones from verify_patient
            if (dashboardDataRef.current?.appointment_id && toolName === 'check_in_patient') {
              args.appointment_id = dashboardDataRef.current.appointment_id;
              console.log('[Tavus] Overriding appointment_id to', args.appointment_id);
            }
            if (dashboardDataRef.current?.patient_id && (toolName === 'book_appointment' || toolName === 'check_in_patient' || toolName === 'get_balance' || toolName === 'get_appointments')) {
              args.patient_id = dashboardDataRef.current.patient_id;
              console.log('[Tavus] Overriding patient_id to', args.patient_id);
            }

            inflightToolsRef.current.add(toolName);
            onToolCallStart?.(toolName, args);

            // Tool call timeout — if backend doesn't respond in 15s, unblock
            const TOOL_TIMEOUT = 15000;
            let toolTimedOut = false;
            const toolTimer = setTimeout(() => {
              toolTimedOut = true;
              if (inflightToolsRef.current.has(toolName)) {
                console.error(`[Tavus] Tool ${toolName} timed out after ${TOOL_TIMEOUT}ms`);
                inflightToolsRef.current.delete(toolName);
                onToolResult?.(toolName, { status: 'error', message: 'Request timed out' });
                injectOrQueue(call, `TOOL_RESULT ${toolName}: ERROR. The request timed out. Tell the patient to try again or direct them to the front desk.`);
              }
            }, TOOL_TIMEOUT);

            // Fetch result from our backend API
            fetchToolResult(toolName, conversationId, args)
              .then((result) => {
                clearTimeout(toolTimer);
                if (toolTimedOut || destroyed) return;
                console.log('[Tavus] Tool result:', toolName, result);

                inflightToolsRef.current.delete(toolName);

                // Set cooldown to prevent immediate re-calls
                toolCooldownRef.current.set(toolName, Date.now());

                // Update UI panels
                onToolResult?.(toolName, result);

                // CRITICAL: Inject tool result into the conversation.
                // Tavus webhook URL responses do NOT go back to the LLM.
                // We send the result as conversation.respond so the LLM sees it
                // in the conversation context and can respond accordingly.
                // If Jenny is still speaking (e.g. "Let me check..."), queue
                // the injection until she finishes to avoid self-interruption.
                const resultMsg = formatToolResultMessage(toolName, result);
                injectOrQueue(call, resultMsg);
              })
              .catch((err) => {
                clearTimeout(toolTimer);
                if (toolTimedOut || destroyed) return;
                console.error('[Tavus] Tool API error:', toolName, err);

                inflightToolsRef.current.delete(toolName);
                onToolResult?.(toolName, { status: 'error', message: `Tool call failed: ${err.message}` });

                // Inject error so the LLM can respond to the patient
                injectOrQueue(call, `TOOL_RESULT ${toolName}: ERROR. Something went wrong. Tell the patient the system is having trouble and direct them to the front desk.`);
              });
          }

          // ===============================================================
          // TRANSCRIPT
          // ===============================================================
          if (eventType === 'conversation.utterance') {
            const text = properties.speech || properties.text || properties.content || '';
            const uttRole = properties.role === 'user' ? 'user' : 'assistant';
            if (text) {
              console.log('[Tavus] Utterance:', uttRole, text.substring(0, 80));
              onTranscript?.({ role: uttRole, text });
            }
          }

          // ===============================================================
          // STATUS
          // ===============================================================
          if (eventType === 'conversation.replica.started_speaking' ||
              eventType === 'conversation.replica_started_speaking') {
            speakingRef.current = true;
            updateStatus('processing');
          }
          if (eventType === 'conversation.replica.stopped_speaking' ||
              eventType === 'conversation.replica_stopped_speaking') {
            speakingRef.current = false;
            updateStatus('listening');
            // Flush any tool results queued while Jenny was speaking
            flushPendingInjections(call);
          }

          // ===============================================================
          // SESSION END
          // ===============================================================
          if (eventType === 'conversation.ended' || eventType === 'system.shutdown') {
            updateStatus('ended');
            onSessionEnd?.();
          }
        });

        // Join with timeout — don't hang forever on slow networks
        const joinTimeout = new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Join timed out (20s)')), 20000)
        );
        await Promise.race([
          call.join({ url: conversationUrl }),
          joinTimeout,
        ]);

      } catch (err) {
        console.error('[useTavusCall] Failed to join:', err);
        if (!destroyed) updateStatus('error');
        // Cleanup failed call object
        if (callRef.current) {
          callRef.current.destroy().catch(() => {});
          callRef.current = null;
        }
      }
    };

    setupCall();

    return () => {
      destroyed = true;
      inflightToolsRef.current.clear();
      toolCooldownRef.current.clear();
      pendingInjectionsRef.current = [];
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
      if (callRef.current) {
        callRef.current.leave().catch(() => {});
        callRef.current.destroy().catch(() => {});
        callRef.current = null;
      }
    };
  }, [conversationUrl]);

  const endCall = useCallback(() => {
    intentionalLeaveRef.current = true;
    if (callRef.current) {
      callRef.current.leave().catch(() => {});
    }
  }, []);

  const sendMessage = useCallback((text) => {
    if (!callRef.current || !text) return;
    console.log('[Tavus] Sending text:', text);
    // Route through injectOrQueue so we don't interrupt Jenny mid-sentence
    injectOrQueue(callRef.current, text);
  }, [injectOrQueue]);

  return { status, endCall, sendMessage };
}
