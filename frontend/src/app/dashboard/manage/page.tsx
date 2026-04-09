'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Gauge,
  Globe2,
  Languages,
  RefreshCw,
  Settings2,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Wand2,
} from 'lucide-react';
import { alertsAPI, dashboardAPI, eventsAPI, organizationsAPI, riskAPI } from '@/lib/api';
import {
  buildGoogleNewsUrl,
  buildTranslateUrl,
  classifyLiveNewsAuthenticity,
  formatDateTime,
  getEventSourceLabel,
  inferInterestCategories,
  isOfficialSource,
  sanitizeStoredText,
} from '@/lib/event-utils';
import { getLiveUiPreferences, saveLiveUiPreferences, type LiveUiPreferences } from '@/lib/live-ui-preferences';

type NewsRecord = {
  id: string;
  title: string;
  description?: string | null;
  event_type?: string | null;
  source?: string | null;
  source_url?: string | null;
  source_status?: string | null;
  source_status_reason?: string | null;
  source_domain?: string | null;
  confidence?: number | null;
  raw_data?: unknown;
  created_at?: string | null;
  event_date?: string | null;
};

const LANGUAGE_OPTIONS = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'ar', label: 'Arabic' },
  { code: 'zh-CN', label: 'Chinese (Simplified)' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'ru', label: 'Russian' },
  { code: 'ja', label: 'Japanese' },
];

const INTEREST_OPTIONS = [
  { key: 'geopolitics', label: 'Geopolitics' },
  { key: 'cybersecurity', label: 'Cybersecurity' },
  { key: 'technology', label: 'Technology' },
  { key: 'innovation', label: 'Innovation' },
  { key: 'economy', label: 'Economy' },
  { key: 'health', label: 'Health' },
  { key: 'climate', label: 'Climate' },
  { key: 'supply_chain', label: 'Supply Chain' },
  { key: 'defense', label: 'Defense' },
  { key: 'energy', label: 'Energy' },
  { key: 'other', label: 'Other' },
];

const TYPEWRITER_LINES = [
  'Customize trusted live intelligence for every client workflow.',
  'Detect possible misinformation with evidence-first labels.',
  'Deliver updates in preferred language and category interests.',
];

function HeroTypewriter({ lines }: { lines: string[] }) {
  const [lineIndex, setLineIndex] = useState(0);
  const [charIndex, setCharIndex] = useState(0);
  const activeLine = lines[lineIndex] || lines[0] || '';

  useEffect(() => {
    const complete = charIndex >= activeLine.length;
    const delay = complete ? 1400 : 55;

    const timer = window.setTimeout(() => {
      if (complete) {
        setLineIndex((current) => (current + 1) % Math.max(lines.length, 1));
        setCharIndex(0);
      } else {
        setCharIndex((current) => current + 1);
      }
    }, delay);

    return () => window.clearTimeout(timer);
  }, [activeLine, charIndex, lines.length]);

  return (
    <p style={{ marginTop: 8, marginBottom: 0, minHeight: 20, fontSize: 13, color: 'var(--text-secondary)' }}>
      {activeLine.slice(0, charIndex)}
      <span style={{ opacity: 0.75 }}>|</span>
    </p>
  );
}

function getTimelineValue(record: NewsRecord): string {
  return record.event_date || record.created_at || '';
}

function getTimelineMs(record: NewsRecord): number {
  const value = getTimelineValue(record);
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

export default function ManagePage() {
  const [preferences, setPreferences] = useState<LiveUiPreferences>(() => getLiveUiPreferences());
  const [stats, setStats] = useState<any>(null);
  const [newsRecords, setNewsRecords] = useState<NewsRecord[]>([]);
  const [message, setMessage] = useState('');
  const [lastActionAt, setLastActionAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [computing, setComputing] = useState(false);
  const [clearingAlerts, setClearingAlerts] = useState(false);
  const [clearingWorkspace, setClearingWorkspace] = useState(false);
  const pollingInFlightRef = useRef(false);

  const applyPreferences = (patch: Partial<LiveUiPreferences>) => {
    const next = saveLiveUiPreferences(patch);
    setPreferences(next);
    setMessage('Live UI preferences updated.');
    setLastActionAt(new Date().toISOString());
  };

  const loadPanel = useCallback(async () => {
    if (pollingInFlightRef.current) {
      return;
    }

    pollingInFlightRef.current = true;
    try {
      const [statsRes, eventsRes] = await Promise.allSettled([
        dashboardAPI.getStats(),
        eventsAPI.list({ page: 1, page_size: 80 }),
      ]);

      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value.data);
      }

      if (eventsRes.status === 'fulfilled') {
        const records = (eventsRes.value.data?.events || []) as NewsRecord[];
        const recent = records
          .sort((a, b) => getTimelineMs(b) - getTimelineMs(a))
          .filter((record) => !preferences.trustedSourcesOnly || isOfficialSource(record as any))
          .filter((record) => {
            if (preferences.selectedCategories.length === 0) return true;
            const categories = inferInterestCategories(record as any);
            return preferences.selectedCategories.some((selected) => categories.includes(selected as any));
          })
          .slice(0, 12);
        setNewsRecords(recent);
      }
    } catch (err) {
      console.error('manage_panel_load_error', err);
    } finally {
      pollingInFlightRef.current = false;
      setLoading(false);
    }
  }, [preferences.selectedCategories, preferences.trustedSourcesOnly]);

  useEffect(() => {
    setPreferences(getLiveUiPreferences());
    void loadPanel();
  }, [loadPanel]);

  useEffect(() => {
    if (!preferences.autoRefresh) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadPanel();
    }, preferences.refreshSeconds * 1000);

    return () => window.clearInterval(interval);
  }, [loadPanel, preferences.autoRefresh, preferences.refreshSeconds]);

  const handleLiveSync = async () => {
    setSyncing(true);
    try {
      const syncRes = await eventsAPI.liveSync({ force: true });
      setMessage(syncRes.data?.message || 'Live sync completed.');
      setLastActionAt(syncRes.data?.synced_at || new Date().toISOString());
      await loadPanel();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setMessage(typeof detail === 'string' ? `Live sync failed: ${detail}` : 'Live sync failed. Please retry.');
    } finally {
      setSyncing(false);
    }
  };

  const handleComputeRisk = async () => {
    setComputing(true);
    try {
      const res = await riskAPI.compute({});
      setMessage(res.data?.message || 'Risk scores recomputed from stored events.');
      setLastActionAt(new Date().toISOString());
      await loadPanel();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setMessage(typeof detail === 'string' ? `Risk compute failed: ${detail}` : 'Risk compute failed.');
    } finally {
      setComputing(false);
    }
  };

  const handleClearAlerts = async () => {
    if (!window.confirm('Delete all alerts from this workspace?')) {
      return;
    }

    setClearingAlerts(true);
    try {
      await alertsAPI.clearAll();
      setMessage('All alerts cleared.');
      setLastActionAt(new Date().toISOString());
      await loadPanel();
    } catch (err) {
      console.error('clear_alerts_error', err);
      setMessage('Failed to clear alerts.');
    } finally {
      setClearingAlerts(false);
    }
  };

  const handleClearWorkspace = async () => {
    if (!window.confirm('Clear ALL workspace data (events, analytics, alerts, watchlists)?')) {
      return;
    }

    setClearingWorkspace(true);
    try {
      const res = await organizationsAPI.clearAllData();
      const deleted = res.data?.deleted || {};
      setMessage(
        `Workspace cleared: events ${deleted.events || 0}, risk scores ${deleted.risk_scores || 0}, alerts ${deleted.alerts || 0}, watchlists ${deleted.watchlists || 0}.`
      );
      setLastActionAt(new Date().toISOString());
      await loadPanel();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setMessage(typeof detail === 'string' ? detail : 'Failed to clear workspace data.');
    } finally {
      setClearingWorkspace(false);
    }
  };

  const statusItems = useMemo(() => ([
    { label: 'Official Records', value: stats?.official_events || 0, icon: CheckCircle2, color: 'var(--accent-emerald)' },
    { label: 'Active Alerts', value: stats?.active_alerts || 0, icon: Bell, color: 'var(--accent-rose)' },
    { label: 'Source Linked', value: stats?.source_linked_events || 0, icon: ExternalLink, color: 'var(--accent-cyan)' },
    { label: 'Detail Ready', value: stats?.detail_ready_events || 0, icon: Gauge, color: 'var(--accent-amber)' },
  ]), [stats]);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Live Manage Center</h1>
          <p className="page-subtitle">Client control panel for live updates, operations, and quick governance actions.</p>
        </div>
        <button className="btn btn-ghost" onClick={() => void loadPanel()}>
          <RefreshCw size={16} /> Refresh Now
        </button>
      </div>

      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          marginBottom: 20,
          border: '1px solid rgba(6, 182, 212, 0.45)',
          background: 'linear-gradient(130deg, rgba(6,182,212,0.16), rgba(99,102,241,0.12) 60%, rgba(16,185,129,0.1))',
          boxShadow: '0 22px 44px rgba(2, 132, 199, 0.18)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Wand2 size={18} style={{ color: 'var(--accent-cyan)' }} />
              Start Live, Your Way
            </h3>
            <HeroTypewriter lines={TYPEWRITER_LINES} />
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span className="badge badge-low">No false certainty</span>
            <span className="badge badge-medium">Source-first</span>
            <span className="badge badge-high">User-customized</span>
          </div>
        </div>
      </motion.div>

      {(message || lastActionAt) && (
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ marginBottom: 20, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {message || 'No recent operation message.'}
          {lastActionAt ? ` Last action ${formatDateTime(lastActionAt)}.` : ''}
        </motion.div>
      )}

      <div className="grid-4" style={{ marginBottom: 24 }}>
        {statusItems.map((item, i) => (
          <motion.div
            key={item.label}
            className="metric-card"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="metric-label">{item.label}</span>
              <item.icon size={18} style={{ color: item.color }} />
            </div>
            <span className="metric-value" style={{ color: item.color }}>{item.value}</span>
          </motion.div>
        ))}
      </div>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <h3 style={{ fontSize: 16, fontWeight: 800, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <SlidersHorizontal size={18} style={{ color: 'var(--accent-indigo)' }} />
            Live Preferences and Personalization
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>Auto Refresh</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Keep dashboards updating without manual refresh.</div>
              </div>
              <input
                type="checkbox"
                checked={preferences.autoRefresh}
                onChange={(e) => applyPreferences({ autoRefresh: e.target.checked })}
                style={{ width: 18, height: 18 }}
              />
            </label>

            <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 700 }}>Refresh Interval</span>
              <select
                className="input"
                value={preferences.refreshSeconds}
                onChange={(e) => applyPreferences({ refreshSeconds: Number(e.target.value) })}
                disabled={!preferences.autoRefresh}
              >
                {[10, 15, 30, 60].map((seconds) => (
                  <option key={seconds} value={seconds}>{seconds} seconds</option>
                ))}
              </select>
            </label>

            <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>Show Instructions by Default</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Users can still toggle instructions from the info icon.</div>
              </div>
              <input
                type="checkbox"
                checked={preferences.showInstructions}
                onChange={(e) => applyPreferences({ showInstructions: e.target.checked })}
                style={{ width: 18, height: 18 }}
              />
            </label>

            <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>Trusted Sources Only</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Hide unverified records from live feed for strict trust mode.</div>
              </div>
              <input
                type="checkbox"
                checked={preferences.trustedSourcesOnly}
                onChange={(e) => applyPreferences({ trustedSourcesOnly: e.target.checked })}
                style={{ width: 18, height: 18 }}
              />
            </label>

            <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Languages size={14} /> Preferred Language
              </span>
              <select
                className="input"
                value={preferences.preferredLanguage}
                onChange={(e) => applyPreferences({ preferredLanguage: e.target.value })}
              >
                {LANGUAGE_OPTIONS.map((language) => (
                  <option key={language.code} value={language.code}>{language.label}</option>
                ))}
              </select>
            </label>

            <div>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Globe2 size={14} /> Interest Categories
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {INTEREST_OPTIONS.map((category) => {
                  const active = preferences.selectedCategories.includes(category.key);
                  return (
                    <button
                      key={category.key}
                      type="button"
                      className={`btn ${active ? 'btn-primary' : 'btn-ghost'} btn-sm`}
                      onClick={() => {
                        const selected = new Set(preferences.selectedCategories);
                        if (active) {
                          selected.delete(category.key);
                        } else {
                          selected.add(category.key);
                        }
                        applyPreferences({ selectedCategories: Array.from(selected) });
                      }}
                      style={{ boxShadow: active ? '0 0 0 1px rgba(6,182,212,0.35), 0 0 20px rgba(6,182,212,0.2)' : 'none' }}
                    >
                      {category.label}
                    </button>
                  );
                })}
              </div>
              <p style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: 'var(--text-muted)' }}>
                Choose one or more interests so users see live updates aligned to what they care about.
              </p>
            </div>
          </div>
        </motion.div>

        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.08 }}>
          <h3 style={{ fontSize: 16, fontWeight: 800, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Settings2 size={18} style={{ color: 'var(--accent-cyan)' }} />
            Manage Actions
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <button className="btn btn-primary" onClick={handleLiveSync} disabled={syncing}>
              <RefreshCw size={16} /> {syncing ? 'Syncing Live Feed...' : 'Start Live Sync'}
            </button>
            <button className="btn btn-ghost" onClick={handleComputeRisk} disabled={computing}>
              <Sparkles size={16} /> {computing ? 'Computing Risk...' : 'Recompute Risk Scores'}
            </button>
            <button className="btn btn-ghost" onClick={handleClearAlerts} disabled={clearingAlerts} style={{ color: 'var(--accent-amber)', borderColor: 'var(--accent-amber)' }}>
              <Trash2 size={16} /> {clearingAlerts ? 'Clearing Alerts...' : 'Clear All Alerts'}
            </button>
            <button className="btn btn-ghost" onClick={handleClearWorkspace} disabled={clearingWorkspace} style={{ color: 'var(--accent-rose)', borderColor: 'var(--accent-rose)' }}>
              <ShieldAlert size={16} /> {clearingWorkspace ? 'Clearing Workspace...' : 'Clear All Workspace Data'}
            </button>
          </div>
        </motion.div>
      </div>

      <div className="grid-2">
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.14 }}>
          <h3 style={{ fontSize: 16, fontWeight: 800, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={18} style={{ color: 'var(--accent-indigo)' }} />
            Live News Updates
          </h3>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 14, lineHeight: 1.7 }}>
            Fresh event records with AI authenticity classification. Labels are evidence-based and non-absolute, so uncertain items are marked for verification.
          </p>

          {loading ? (
            <div className="skeleton" style={{ height: 180 }} />
          ) : newsRecords.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              No records match your current filters. Try turning off Trusted Sources Only or selecting different interests.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {newsRecords.map((record) => (
                <div key={record.id} style={{ padding: 12, borderRadius: 12, background: 'var(--bg-hover)', border: '1px solid var(--border-primary)', transition: 'transform 160ms ease, box-shadow 160ms ease' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, lineHeight: 1.5, marginBottom: 6 }}>
                    {sanitizeStoredText(record.title) || 'Untitled record'}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                    {inferInterestCategories(record as any).slice(0, 3).map((category) => {
                      const label = INTEREST_OPTIONS.find((item) => item.key === category)?.label || category;
                      return (
                        <span key={`${record.id}-${category}`} className="badge badge-medium" style={{ fontSize: 10 }}>
                          {label}
                        </span>
                      );
                    })}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
                    {getEventSourceLabel(record as any)} | {formatDateTime(getTimelineValue(record))}
                  </div>
                  {(() => {
                    const verdict = classifyLiveNewsAuthenticity(record as any);
                    const toneColor = verdict.verdict === 'likely_genuine'
                      ? 'var(--accent-emerald)'
                      : verdict.verdict === 'possibly_misleading'
                        ? 'var(--accent-rose)'
                        : 'var(--accent-amber)';

                    return (
                      <div style={{ marginBottom: 10 }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 700, color: toneColor, padding: '4px 8px', border: `1px solid ${toneColor}`, borderRadius: 999 }}>
                          <AlertTriangle size={12} />
                          {verdict.label}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.55 }}>
                          {verdict.reason}
                        </div>
                      </div>
                    );
                  })()}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {record.source_url && (
                      <a href={record.source_url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-sm">
                        <ExternalLink size={14} /> Source
                      </a>
                    )}
                    <a href={buildGoogleNewsUrl(record as any)} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm">
                      <Sparkles size={14} /> Live News
                    </a>
                    {preferences.preferredLanguage !== 'en' && (
                      <a
                        href={buildTranslateUrl(record.title || '', preferences.preferredLanguage)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn-ghost btn-sm"
                      >
                        <Languages size={14} /> Translate
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </motion.div>

        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
          <h3 style={{ fontSize: 16, fontWeight: 800, marginBottom: 14 }}>Quick Navigation</h3>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 14, lineHeight: 1.7 }}>
            Fast access to verification and control workflows.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Link href="/dashboard/events" className="btn btn-ghost">Open Events</Link>
            <Link href="/dashboard/alerts" className="btn btn-ghost">Open Alerts</Link>
            <Link href="/dashboard/analytics" className="btn btn-ghost">Open Analytics</Link>
            <Link href="/dashboard/about" className="btn btn-ghost">Open About</Link>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
