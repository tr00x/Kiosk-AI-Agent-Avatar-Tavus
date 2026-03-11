/**
 * ManualCheckin — Staff sidebar with PIN protection.
 *
 * Tabs: Patients | Book | Register | Sessions
 * - Patients: search + check-in + balance + appointments
 * - Book: find slots + book appointment
 * - Register: create new patient
 * - Sessions: view/end active kiosk sessions
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Search, UserPlus, CalendarDays, Clock, User, Phone, Shield,
  CheckCircle2, XCircle, Loader2, Stethoscope, Scissors, Smile,
  Syringe, DollarSign, CalendarCheck, Monitor, Power, Lock,
  ChevronRight, ArrowLeft, X, Users, StickyNote, Send, Timer,
} from 'lucide-react';

const API = '';
const STAFF_PIN = '2580';
const AUTO_LOCK_MS = 120000; // 2 min idle → lock

const TABS = [
  { key: 'queue', label: 'Queue', icon: Users },
  { key: 'patients', label: 'Patients', icon: Search },
  { key: 'book', label: 'Book', icon: CalendarDays },
  { key: 'register', label: 'Register', icon: UserPlus },
  { key: 'sessions', label: 'Sessions', icon: Monitor },
];

const PROCEDURES = [
  { key: 'routine_exam_cleaning', label: 'Cleaning & Exam', icon: Smile },
  { key: 'cosmetic', label: 'Cosmetic', icon: Smile },
  { key: 'root_canal', label: 'Root Canal', icon: Stethoscope },
  { key: 'extraction', label: 'Extraction', icon: Scissors },
  { key: 'tooth_replacement', label: 'Implant / Consult', icon: Syringe },
];

export default function ManualCheckin() {
  const [open, setOpen] = useState(false);
  const [unlocked, setUnlocked] = useState(false);
  const [pin, setPin] = useState('');
  const [pinError, setPinError] = useState(false);
  const [tab, setTab] = useState('patients');
  const lockTimerRef = useRef(null);

  // --- Patients tab ---
  const [lastName, setLastName] = useState('');
  const [dob, setDob] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState(null);
  const [searchMsg, setSearchMsg] = useState('');
  const [patient, setPatient] = useState(null);
  const [balance, setBalance] = useState(null);
  const [balanceLoading, setBalanceLoading] = useState(false);
  const [appointments, setAppointments] = useState(null);
  const [aptsLoading, setAptsLoading] = useState(false);
  const [checkedIn, setCheckedIn] = useState({});
  const [notes, setNotes] = useState(null);
  const [notesLoading, setNotesLoading] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [noteSaving, setNoteSaving] = useState(false);

  // --- Queue tab ---
  const [queue, setQueue] = useState(null);
  const [queueLoading, setQueueLoading] = useState(false);

  // --- Book tab ---
  const [bookPatientId, setBookPatientId] = useState('');
  const [bookPatientName, setBookPatientName] = useState('');
  const [bookSearchName, setBookSearchName] = useState('');
  const [bookSearchResults, setBookSearchResults] = useState(null);
  const [bookSearching, setBookSearching] = useState(false);
  const [selectedProc, setSelectedProc] = useState(null);
  const [bookDate, setBookDate] = useState('');
  const [slots, setSlots] = useState(null);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [bookingResult, setBookingResult] = useState(null);
  const [bookingLoading, setBookingLoading] = useState(false);

  // --- Register tab ---
  const [regForm, setRegForm] = useState({ first_name: '', last_name: '', dob: '', phone: '', insurance: '' });
  const [regLoading, setRegLoading] = useState(false);
  const [regResult, setRegResult] = useState(null);

  // --- Sessions tab ---
  const [sessions, setSessions] = useState(null);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [endingAll, setEndingAll] = useState(false);

  const [error, setError] = useState('');

  const api = useCallback(async (path, body, method = 'POST') => {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(`${API}${path}`, opts);
    return resp.json();
  }, []);

  // Auto-lock on idle
  const resetLockTimer = useCallback(() => {
    if (lockTimerRef.current) clearTimeout(lockTimerRef.current);
    lockTimerRef.current = setTimeout(() => {
      setUnlocked(false);
      setPin('');
      setOpen(false);
    }, AUTO_LOCK_MS);
  }, []);

  const touch = useCallback(() => {
    if (unlocked) resetLockTimer();
  }, [unlocked, resetLockTimer]);

  useEffect(() => {
    return () => { if (lockTimerRef.current) clearTimeout(lockTimerRef.current); };
  }, []);

  // PIN submit
  const handlePinSubmit = () => {
    if (pin === STAFF_PIN) {
      setUnlocked(true);
      setPinError(false);
      resetLockTimer();
    } else {
      setPinError(true);
      setPin('');
    }
  };

  // PIN keypad
  const handlePinKey = (digit) => {
    touch();
    const next = pin + digit;
    setPin(next);
    setPinError(false);
    if (next.length === 4) {
      if (next === STAFF_PIN) {
        setUnlocked(true);
        setPinError(false);
        resetLockTimer();
      } else {
        setPinError(true);
        setTimeout(() => setPin(''), 300);
      }
    }
  };

  // --- Search ---
  const handleSearch = async () => {
    if (!lastName && !dob) return;
    touch();
    setSearching(true);
    setResults(null);
    setSearchMsg('');
    setPatient(null);
    setError('');
    try {
      let dobApi = dob;
      if (dob?.includes('-')) {
        const [y, m, d] = dob.split('-');
        dobApi = `${m}/${d}/${y}`;
      }
      const data = await api('/api/manual/search', { last_name: lastName || null, dob: dobApi || null });
      setResults(data.results || []);
      setSearchMsg(data.message || '');
    } catch {
      setError('Search failed');
    } finally {
      setSearching(false);
    }
  };

  // --- Select patient ---
  const selectPatient = async (p) => {
    touch();
    setPatient(p);
    setBalance(null);
    setAppointments(null);
    setNotes(null);
    setNoteText('');
    setBalanceLoading(true);
    setAptsLoading(true);

    fetchNotes(p.pat_num);
    api('/api/staff/balance', { patient_id: p.pat_num })
      .then(d => setBalance(d.result))
      .catch(() => setBalance({ status: 'error' }))
      .finally(() => setBalanceLoading(false));

    api('/api/staff/appointments', { patient_id: p.pat_num })
      .then(d => setAppointments(d.result))
      .catch(() => setAppointments({ status: 'error' }))
      .finally(() => setAptsLoading(false));
  };

  // --- Check-in ---
  const handleCheckin = async (aptNum) => {
    touch();
    try {
      const data = await api('/api/manual/checkin', { appointment_id: aptNum });
      if (data.status === 'ok') setCheckedIn(prev => ({ ...prev, [aptNum]: true }));
    } catch { /* */ }
  };

  // --- Notes ---
  const fetchNotes = async (patId) => {
    setNotesLoading(true);
    try {
      const data = await api('/api/staff/notes/list', { patient_id: patId });
      setNotes(data.notes || []);
    } catch {
      setNotes([]);
    } finally {
      setNotesLoading(false);
    }
  };

  const handleAddNote = async () => {
    if (!noteText.trim() || !patient) return;
    touch();
    setNoteSaving(true);
    try {
      await api('/api/staff/notes', { patient_id: patient.pat_num, text: noteText.trim() });
      setNoteText('');
      fetchNotes(patient.pat_num);
    } catch {
      setError('Failed to save note');
    } finally {
      setNoteSaving(false);
    }
  };

  // --- Queue ---
  const fetchQueue = async () => {
    touch();
    setQueueLoading(true);
    try {
      const data = await api('/api/staff/queue', null, 'GET');
      setQueue(data.queue || []);
    } catch {
      setQueue([]);
    } finally {
      setQueueLoading(false);
    }
  };

  // --- Book: patient search ---
  const handleBookSearch = async () => {
    if (!bookSearchName.trim()) return;
    touch();
    setBookSearching(true);
    setBookSearchResults(null);
    try {
      const data = await api('/api/manual/search', { last_name: bookSearchName.trim(), dob: null });
      setBookSearchResults(data.results || []);
    } catch {
      setError('Patient search failed');
    } finally {
      setBookSearching(false);
    }
  };

  const selectBookPatient = (p) => {
    touch();
    setBookPatientId(String(p.pat_num));
    setBookPatientName(`${p.first_name} ${p.last_name}`);
    setBookSearchResults(null);
    setBookSearchName('');
  };

  // --- Slots ---
  const handleFindSlots = async () => {
    if (!bookDate) return;
    touch();
    setSlotsLoading(true);
    setSlots(null);
    try {
      const data = await api('/api/staff/slots', { date: bookDate, procedure_type: selectedProc || undefined });
      setSlots(data.result);
    } catch {
      setError('Could not find slots');
    } finally {
      setSlotsLoading(false);
    }
  };

  const handleBook = async (time) => {
    touch();
    setBookingLoading(true);
    try {
      const data = await api('/api/staff/book', {
        patient_id: parseInt(bookPatientId) || patient?.pat_num,
        date: bookDate,
        time,
        procedure_type: selectedProc || 'routine_exam_cleaning',
      });
      setBookingResult(data.result);
    } catch {
      setError('Booking failed');
    } finally {
      setBookingLoading(false);
    }
  };

  // --- Register ---
  const handleRegister = async () => {
    touch();
    setRegLoading(true);
    setRegResult(null);
    try {
      const data = await api('/api/staff/register', regForm);
      setRegResult(data.result);
    } catch {
      setRegResult({ status: 'error', message: 'Registration failed' });
    } finally {
      setRegLoading(false);
    }
  };

  // --- Sessions ---
  const fetchSessions = async () => {
    touch();
    setSessionsLoading(true);
    try {
      const data = await api('/api/staff/sessions', null, 'GET');
      setSessions(data.sessions || []);
    } catch {
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  };

  const handleEndAll = async () => {
    touch();
    setEndingAll(true);
    try {
      await api('/api/staff/sessions/end-all', {});
      fetchSessions();
    } catch { /* */ }
    finally { setEndingAll(false); }
  };

  // Fetch data on tab switch
  useEffect(() => {
    if (tab === 'sessions' && unlocked) fetchSessions();
    if (tab === 'queue' && unlocked) fetchQueue();
  }, [tab, unlocked]);

  const handleOpen = () => {
    setOpen(true);
    if (!unlocked) setPin('');
  };

  return (
    <>
      {/* Toggle button */}
      <button
        className={`sidebar-toggle ${open ? 'sidebar-toggle-open' : ''}`}
        onClick={() => { if (open) { setOpen(false); setUnlocked(false); setPin(''); } else { handleOpen(); } }}
        title="Staff Panel"
      >
        <Lock size={20} />
      </button>

      {/* Sidebar */}
      <div className={`manual-sidebar ${open ? 'manual-sidebar-open' : ''}`} onClick={touch}>
        {/* Header */}
        <div className="sidebar-header">
          <div className="sidebar-header-left">
            <Shield size={20} strokeWidth={2} color="var(--accent)" />
            <h3 className="sidebar-title">Staff Panel</h3>
          </div>
          <button className="sidebar-close-btn" onClick={() => { setOpen(false); setUnlocked(false); setPin(''); }}>
            <X size={18} />
          </button>
        </div>

        {/* PIN screen */}
        {!unlocked && (
          <div className="sp-pin-screen">
            <Lock size={32} className="sp-pin-icon" />
            <p className="sp-pin-label">Enter Staff PIN</p>
            <div className="sp-pin-dots">
              {[0,1,2,3].map(i => (
                <div key={i} className={`sp-pin-dot ${pin.length > i ? 'sp-pin-dot-filled' : ''} ${pinError ? 'sp-pin-dot-error' : ''}`} />
              ))}
            </div>
            {pinError && <p className="sp-pin-error">Wrong PIN</p>}
            <div className="sp-pin-pad">
              {[1,2,3,4,5,6,7,8,9,null,0,'⌫'].map((d, i) => (
                d === null ? <div key={i} /> :
                <button
                  key={i}
                  className="sp-pin-key"
                  onClick={() => d === '⌫' ? setPin(p => p.slice(0, -1)) : handlePinKey(String(d))}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Main content */}
        {unlocked && (
          <>
            {/* Tabs */}
            <div className="sp-tabs">
              {TABS.map(t => (
                <button
                  key={t.key}
                  className={`sp-tab ${tab === t.key ? 'sp-tab-active' : ''}`}
                  onClick={() => { setTab(t.key); touch(); }}
                >
                  <t.icon size={14} />
                  {t.label}
                </button>
              ))}
            </div>

            <div className="sp-content">
              {error && (
                <div className="sp-error"><XCircle size={14} /> {error}
                  <button className="sp-error-close" onClick={() => setError('')}>×</button>
                </div>
              )}

              {/* ==================== QUEUE TAB ==================== */}
              {tab === 'queue' && (
                <div className="sp-queue-tab">
                  <button className="sp-btn-outline" onClick={fetchQueue} disabled={queueLoading}>
                    {queueLoading ? <Loader2 size={14} className="sp-spin" /> : <Users size={14} />}
                    Refresh
                  </button>

                  {queue?.length > 0 ? (
                    queue.map(q => (
                      <button
                        key={q.apt_num}
                        className="sp-queue-card"
                        onClick={() => {
                          selectPatient({
                            pat_num: q.pat_num,
                            apt_num: q.apt_num,
                            first_name: q.name.split(' ')[0],
                            last_name: q.name.split(' ').slice(1).join(' '),
                            procedure: q.procedure,
                            time: q.appointment_time,
                            provider: q.provider,
                          });
                          setTab('patients');
                        }}
                      >
                        <div className="sp-queue-row-top">
                          <span className="sp-queue-name">{q.name}</span>
                          <span className={`sp-queue-wait ${q.wait_minutes > 15 ? 'sp-queue-wait-long' : ''}`}>
                            <Timer size={12} /> {q.wait_minutes >= 60 ? `${Math.floor(q.wait_minutes / 60)}h ${q.wait_minutes % 60}m` : `${q.wait_minutes}m`}
                          </span>
                        </div>
                        <div className="sp-detail-meta">
                          <span><Clock size={11} /> Appt {q.appointment_time}</span>
                          <span>Arrived {q.arrived_at}</span>
                        </div>
                        <div className="sp-detail-meta">
                          <span>{q.procedure}</span>
                          {q.provider && <span><User size={11} /> {q.provider}</span>}
                        </div>
                      </button>
                    ))
                  ) : queue && (
                    <div className="sp-empty-small">
                      <Users size={24} strokeWidth={1.5} />
                      <p>No one waiting</p>
                    </div>
                  )}
                </div>
              )}

              {/* ==================== PATIENTS TAB ==================== */}
              {tab === 'patients' && (
                <>
                  {!patient ? (
                    <>
                      <div className="sp-search-form">
                        <div className="sp-field-row">
                          <div className="sp-field">
                            <label><User size={12} /> Last Name</label>
                            <input className="sp-input" value={lastName} onChange={e => setLastName(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} placeholder="Smith" />
                          </div>
                          <div className="sp-field">
                            <label><CalendarDays size={12} /> DOB</label>
                            <input type="date" className="sp-input" value={dob} onChange={e => setDob(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} />
                          </div>
                        </div>
                        <button className="sp-btn-primary" onClick={handleSearch} disabled={searching || (!lastName && !dob)}>
                          {searching ? <Loader2 size={14} className="sp-spin" /> : <Search size={14} />}
                          {searching ? 'Searching...' : 'Search'}
                        </button>
                      </div>

                      {searchMsg && <div className="sp-info-msg">{searchMsg}</div>}

                      {results?.map(r => (
                        <button key={r.apt_num} className="sp-list-item" onClick={() => selectPatient(r)}>
                          <div>
                            <div className="sp-list-name">{r.first_name} {r.last_name}</div>
                            <div className="sp-list-meta">
                              <span><Clock size={11} /> {r.time}</span>
                              <span>{r.procedure}</span>
                            </div>
                          </div>
                          <ChevronRight size={16} />
                        </button>
                      ))}

                      {results?.length === 0 && (
                        <div className="sp-empty-small">
                          <Search size={24} strokeWidth={1.5} />
                          <p>No appointments today</p>
                        </div>
                      )}
                    </>
                  ) : (
                    /* Patient detail */
                    <div className="sp-patient-detail">
                      <button className="sp-back-btn" onClick={() => setPatient(null)}>
                        <ArrowLeft size={14} /> Back
                      </button>

                      <div className="sp-patient-name-row">
                        <CheckCircle2 size={18} className="sp-ok" />
                        <span className="sp-name">{patient.first_name} {patient.last_name}</span>
                      </div>

                      {/* Today */}
                      <div className="sp-section">
                        <div className="sp-section-title"><CalendarCheck size={14} /> Today</div>
                        <div className="sp-section-body">
                          <div className="sp-detail-row">{patient.procedure}</div>
                          <div className="sp-detail-meta">
                            <span><Clock size={11} /> {patient.time}</span>
                            <span><User size={11} /> {patient.provider}</span>
                          </div>
                          {checkedIn[patient.apt_num] ? (
                            <div className="sp-badge-ok"><CheckCircle2 size={12} /> Checked in</div>
                          ) : (
                            <button className="sp-btn-success" onClick={() => handleCheckin(patient.apt_num)}>
                              <CalendarCheck size={14} /> Check In
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Balance */}
                      <div className="sp-section">
                        <div className="sp-section-title"><DollarSign size={14} /> Balance</div>
                        <div className="sp-section-body">
                          {balanceLoading ? <div className="sp-loading-sm"><Loader2 size={14} className="sp-spin" /></div> :
                           !balance || balance.status === 'error' ? <span className="sp-muted">Error</span> :
                           balance.balance === 0 ? <span className="sp-ok-text">No balance</span> :
                           <div className="sp-bal">
                             {balance.current_owed > 0 && <div className="sp-bal-line"><span>Owed</span><span>${balance.current_owed?.toFixed(0)}</span></div>}
                             {balance.insurance_pending > 0 && <div className="sp-bal-line sp-ok-text"><span>Insurance</span><span>-${balance.insurance_pending?.toFixed(0)}</span></div>}
                             <div className="sp-bal-line sp-bal-total"><span>Total</span><span>${balance.balance?.toFixed(0)}</span></div>
                           </div>
                          }
                        </div>
                      </div>

                      {/* Upcoming */}
                      <div className="sp-section">
                        <div className="sp-section-title"><CalendarDays size={14} /> Upcoming</div>
                        <div className="sp-section-body">
                          {aptsLoading ? <div className="sp-loading-sm"><Loader2 size={14} className="sp-spin" /></div> :
                           !appointments?.appointments?.length ? <span className="sp-muted">None</span> :
                           appointments.appointments.map((a, i) => (
                            <div key={a.id || i} className="sp-upcoming-item">
                              <div className="sp-upcoming-type">{a.type}</div>
                              <div className="sp-detail-meta"><span><Clock size={11} /> {a.date} {a.time}</span></div>
                            </div>
                           ))
                          }
                        </div>
                      </div>

                      {/* Quick book for this patient */}
                      <button className="sp-btn-outline" onClick={() => { setBookPatientId(String(patient.pat_num)); setBookPatientName(`${patient.first_name} ${patient.last_name}`); setTab('book'); }}>
                        <CalendarDays size={14} /> Book for this patient
                      </button>

                      {/* Notes */}
                      <div className="sp-section">
                        <div className="sp-section-title"><StickyNote size={14} /> Notes</div>
                        <div className="sp-section-body">
                          <div className="sp-notes-input">
                            <input
                              className="sp-input"
                              value={noteText}
                              onChange={e => setNoteText(e.target.value)}
                              onKeyDown={e => e.key === 'Enter' && handleAddNote()}
                              placeholder="Add a note..."
                            />
                            <button className="sp-btn-sm" onClick={handleAddNote} disabled={noteSaving || !noteText.trim()}>
                              {noteSaving ? <Loader2 size={14} className="sp-spin" /> : <Send size={14} />}
                            </button>
                          </div>
                          {notesLoading ? (
                            <div className="sp-loading-sm"><Loader2 size={14} className="sp-spin" /></div>
                          ) : notes?.length > 0 ? (
                            <div className="sp-notes-list">
                              {notes.map(n => (
                                <div key={n.id} className="sp-note-item">
                                  <div className="sp-note-text">{n.text}</div>
                                  <div className="sp-note-time">{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span className="sp-muted">No notes yet</span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* ==================== BOOK TAB ==================== */}
              {tab === 'book' && (
                <div className="sp-book-tab">
                  {!bookingResult ? (
                    <>
                      {/* Patient selection */}
                      {bookPatientId ? (
                        <div className="sp-book-patient-selected">
                          <div className="sp-book-patient-info">
                            <CheckCircle2 size={16} className="sp-ok" />
                            <span className="sp-name">{bookPatientName}</span>
                            <span className="sp-muted">#{bookPatientId}</span>
                          </div>
                          <button className="sp-btn-link" onClick={() => { setBookPatientId(''); setBookPatientName(''); setSlots(null); }}>
                            <X size={14} /> Change
                          </button>
                        </div>
                      ) : (
                        <div className="sp-field">
                          <label><Search size={12} /> Find Patient</label>
                          <div className="sp-search-inline">
                            <input
                              className="sp-input"
                              value={bookSearchName}
                              onChange={e => setBookSearchName(e.target.value)}
                              onKeyDown={e => e.key === 'Enter' && handleBookSearch()}
                              placeholder="Last name..."
                            />
                            <button className="sp-btn-sm" onClick={handleBookSearch} disabled={bookSearching || !bookSearchName.trim()}>
                              {bookSearching ? <Loader2 size={14} className="sp-spin" /> : <Search size={14} />}
                            </button>
                          </div>
                          {bookSearchResults?.length > 0 && (
                            <div className="sp-book-search-results">
                              {bookSearchResults.map(r => (
                                <button key={r.pat_num || r.apt_num} className="sp-list-item sp-list-item-compact" onClick={() => selectBookPatient(r)}>
                                  <div>
                                    <div className="sp-list-name">{r.first_name} {r.last_name}</div>
                                    <div className="sp-list-meta"><span>#{r.pat_num}</span></div>
                                  </div>
                                  <ChevronRight size={14} />
                                </button>
                              ))}
                            </div>
                          )}
                          {bookSearchResults?.length === 0 && (
                            <div className="sp-muted" style={{ marginTop: 6, fontSize: 12 }}>No patients found</div>
                          )}
                        </div>
                      )}

                      <div className="sp-field">
                        <label>Procedure</label>
                        <div className="sp-proc-list">
                          {PROCEDURES.map(p => (
                            <button key={p.key} className={`sp-proc-item ${selectedProc === p.key ? 'sp-proc-active' : ''}`} onClick={() => setSelectedProc(p.key)}>
                              <p.icon size={14} /> {p.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="sp-field">
                        <label>Date</label>
                        <input type="date" className="sp-input" value={bookDate} onChange={e => setBookDate(e.target.value)} min={new Date(Date.now() + 86400000).toISOString().split('T')[0]} />
                      </div>

                      <button className="sp-btn-primary" onClick={handleFindSlots} disabled={!bookDate || !bookPatientId || slotsLoading}>
                        {slotsLoading ? <Loader2 size={14} className="sp-spin" /> : <Search size={14} />}
                        Find Slots
                      </button>

                      {slots?.slots?.length > 0 && (
                        <div className="sp-slots-list">
                          <div className="sp-slots-label">{slots.slots.length} slots on {slots.date}</div>
                          <div className="sp-slots-grid">
                            {slots.slots.map(s => (
                              <button key={s.time} className="sp-slot" onClick={() => handleBook(s.time)} disabled={bookingLoading}>
                                <Clock size={12} /> {s.time}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {slots && !slots.slots?.length && (
                        <div className="sp-muted">{slots.message || 'No slots'}</div>
                      )}
                    </>
                  ) : (
                    <div className="sp-book-done">
                      {bookingResult.status === 'success' ? (
                        <>
                          <CheckCircle2 size={28} className="sp-ok" />
                          <p><strong>{bookingResult.procedure}</strong></p>
                          <p className="sp-muted">{bookingResult.date} at {bookingResult.time}</p>
                        </>
                      ) : (
                        <p className="sp-error-text">{bookingResult.message}</p>
                      )}
                      <button className="sp-btn-outline" onClick={() => { setBookingResult(null); setSlots(null); setBookPatientId(''); setBookPatientName(''); }}>Book another</button>
                    </div>
                  )}
                </div>
              )}

              {/* ==================== REGISTER TAB ==================== */}
              {tab === 'register' && (
                <div className="sp-register-tab">
                  {regResult?.status === 'success' ? (
                    <div className="sp-book-done">
                      <CheckCircle2 size={28} className="sp-ok" />
                      <p><strong>{regResult.name}</strong> registered</p>
                      <p className="sp-muted">ID: {regResult.patient_id}</p>
                      <button className="sp-btn-outline" onClick={() => { setRegResult(null); setRegForm({ first_name: '', last_name: '', dob: '', phone: '', insurance: '' }); }}>Register another</button>
                    </div>
                  ) : (
                    <>
                      <div className="sp-field"><label><User size={12} /> First Name</label><input className="sp-input" value={regForm.first_name} onChange={e => setRegForm(p => ({...p, first_name: e.target.value}))} placeholder="John" /></div>
                      <div className="sp-field"><label><User size={12} /> Last Name</label><input className="sp-input" value={regForm.last_name} onChange={e => setRegForm(p => ({...p, last_name: e.target.value}))} placeholder="Doe" /></div>
                      <div className="sp-field"><label><CalendarDays size={12} /> DOB</label><input type="date" className="sp-input" value={regForm.dob} onChange={e => setRegForm(p => ({...p, dob: e.target.value}))} /></div>
                      <div className="sp-field"><label><Phone size={12} /> Phone</label><input className="sp-input" value={regForm.phone} onChange={e => setRegForm(p => ({...p, phone: e.target.value}))} placeholder="555-123-4567" /></div>
                      <div className="sp-field"><label><Shield size={12} /> Insurance</label><input className="sp-input" value={regForm.insurance} onChange={e => setRegForm(p => ({...p, insurance: e.target.value}))} placeholder="Blue Cross" /></div>
                      {regResult?.status === 'error' && <div className="sp-error"><XCircle size={14} /> {regResult.message}</div>}
                      <button className="sp-btn-primary" onClick={handleRegister} disabled={regLoading || !regForm.first_name || !regForm.last_name || !regForm.dob}>
                        {regLoading ? <Loader2 size={14} className="sp-spin" /> : <UserPlus size={14} />}
                        {regLoading ? 'Registering...' : 'Register'}
                      </button>
                    </>
                  )}
                </div>
              )}

              {/* ==================== SESSIONS TAB ==================== */}
              {tab === 'sessions' && (
                <div className="sp-sessions-tab">
                  <button className="sp-btn-outline" onClick={fetchSessions} disabled={sessionsLoading}>
                    {sessionsLoading ? <Loader2 size={14} className="sp-spin" /> : <Monitor size={14} />}
                    Refresh
                  </button>

                  {sessions?.length > 0 ? (
                    <>
                      {sessions.map(s => (
                        <div key={s.conversation_id} className="sp-session-card">
                          <div className="sp-session-id">{s.conversation_id.slice(0, 12)}...</div>
                          <div className="sp-detail-meta">
                            <span><Clock size={11} /> {new Date(s.start_time).toLocaleTimeString()}</span>
                            <span>{s.language?.toUpperCase()}</span>
                            {s.patient_id && <span>Patient #{s.patient_id}</span>}
                          </div>
                        </div>
                      ))}
                      <button className="sp-btn-danger" onClick={handleEndAll} disabled={endingAll}>
                        {endingAll ? <Loader2 size={14} className="sp-spin" /> : <Power size={14} />}
                        End All Sessions ({sessions.length})
                      </button>
                    </>
                  ) : sessions && (
                    <div className="sp-empty-small">
                      <Monitor size={24} strokeWidth={1.5} />
                      <p>No active sessions</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
