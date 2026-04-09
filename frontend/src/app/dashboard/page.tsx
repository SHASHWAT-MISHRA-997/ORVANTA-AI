'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { dashboardAPI, alertsAPI, eventsAPI } from '@/lib/api';
import {
  AlertTriangle, BadgeCheck,
  MapPin, Trash2, ExternalLink,
  Info, ArrowRight, ShieldCheck, RefreshCw, BookOpen, SlidersHorizontal,
} from 'lucide-react';
import {
  formatDateTime,
  getEventCoordinates,
  getOfficialSource,
  isOfficialSource,
  sanitizeStoredText,
} from '@/lib/event-utils';
import { getLiveUiPreferences, saveLiveUiPreferences } from '@/lib/live-ui-preferences';

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.35 },
  }),
};

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [liveSyncing, setLiveSyncing] = useState(false);
  const [liveMessage, setLiveMessage] = useState('');
  const [lastLiveSync, setLastLiveSync] = useState<string | null>(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshSeconds, setRefreshSeconds] = useState(15);
  const [showInstructions, setShowInstructions] = useState(false);

  const load = useCallback(async (sync = false, force = false) => {
    let syncFailed = false;
    try {
      if (sync) {
        try {
          const syncRes = await eventsAPI.liveSync({ force });
          setLiveMessage(syncRes.data?.message || 'Live sync completed successfully.');
          setLastLiveSync(syncRes.data?.synced_at || new Date().toISOString());
        } catch (syncErr: any) {
          syncFailed = true;
          console.error('dashboard_live_sync_error', syncErr);
          const detail = syncErr?.response?.data?.detail;
          setLiveMessage(
            typeof detail === 'string' && detail
              ? `Live sync failed: ${detail}`
              : 'Live sync failed due to a temporary server issue. Please retry in a moment.'
          );
        }
      }

      const [statsRes, alertsRes, eventsRes] = await Promise.allSettled([
        dashboardAPI.getStats(),
        alertsAPI.list({ limit: 5 }),
        eventsAPI.list({ page_size: 100 }),
      ]);

      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
      if (alertsRes.status === 'fulfilled') setAlerts(alertsRes.value.data.alerts || []);
      if (eventsRes.status === 'fulfilled') setEvents(eventsRes.value.data.events || []);

      if (sync && !syncFailed) {
        setLastLiveSync((current) => current || new Date().toISOString());
      }
    } catch (err) {
      console.error('Dashboard load error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const preferences = getLiveUiPreferences();
    setAutoRefreshEnabled(preferences.autoRefresh);
    setRefreshSeconds(preferences.refreshSeconds);
    setShowInstructions(preferences.showInstructions);
  }, []);

  useEffect(() => {
    void load(false);

    if (!autoRefreshEnabled) {
      return;
    }

    const interval = window.setInterval(() => {
      void load(false);
    }, refreshSeconds * 1000);

    return () => window.clearInterval(interval);
  }, [load, autoRefreshEnabled, refreshSeconds]);

  if (loading) {
    return (
      <div>
        <div className="page-header"><div><h1 className="page-title">Dashboard</h1></div></div>
        <div className="grid-4" style={{ marginBottom: 24 }}>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton" style={{ height: 100 }} />
          ))}
        </div>
        <div className="grid-2">
          <div className="skeleton" style={{ height: 360 }} />
          <div className="skeleton" style={{ height: 360 }} />
        </div>
      </div>
    );
  }

  const totalEvents = stats?.total_events || events.length || 0;
  const officialVisibleEvents = events.filter((event) => isOfficialSource(event));
  const officialEvents = stats?.official_events ?? officialVisibleEvents.length;
  const sourceLinkedEvents = stats?.source_linked_events ?? officialVisibleEvents.filter((event) => Boolean(getOfficialSource(event)?.url || event.source_url)).length;
  const coordinateCount = stats?.events_with_coordinates ?? officialVisibleEvents.filter((event) => {
    const coordinates = getEventCoordinates(event);
    return coordinates.latitude != null && coordinates.longitude != null;
  }).length;
  const detailReadyCount = stats?.detail_ready_events ?? officialVisibleEvents.filter((event) => event.detail_available).length;
  const duplicateEvents = stats?.duplicate_events ?? officialVisibleEvents.filter((event) => event.is_duplicate === 1).length;
  const averageConfidence = stats?.average_event_confidence
    ?? (events.length
      ? Number(
          (
            events.reduce((sum, event) => sum + (Number(event.confidence) || 0), 0)
            / events.length
          ).toFixed(2)
        )
      : 0);

  const verificationCoverage = totalEvents > 0 ? Math.round((sourceLinkedEvents / totalEvents) * 100) : 0;

  const metricCards = [
    { label: 'Official Records', value: officialEvents, icon: BadgeCheck, color: 'var(--accent-emerald)' },
    { label: 'Source Linked', value: sourceLinkedEvents, icon: ExternalLink, color: 'var(--accent-cyan)' },
    { label: 'Exact Coordinates', value: coordinateCount, icon: MapPin, color: 'var(--accent-amber)' },
    { label: 'Active Alerts', value: stats?.active_alerts || 0, icon: AlertTriangle, color: 'var(--accent-rose)' },
  ];

  const handleClearAlerts = async () => {
    if (window.confirm('Delete all alerts?')) {
      try {
        await alertsAPI.clearAll();
        setAlerts([]);
        setStats((prev: any) => ({ ...prev, active_alerts: 0 }));
      } catch (err) {
        console.error(err);
      }
    }
  };

  const handleStartLiveSync = async () => {
    setLiveSyncing(true);
    setLiveMessage('Live sync started. Fetching latest official records...');
    try {
      await load(true, true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === 'string' && detail) {
        setLiveMessage(`Live sync failed: ${detail}`);
      } else {
        setLiveMessage('Live sync failed due to a temporary server issue. Please retry in a moment.');
      }
    } finally {
      setLiveSyncing(false);
    }
  };

  const handleToggleInstructions = () => {
    const next = !showInstructions;
    setShowInstructions(next);
    saveLiveUiPreferences({ showInstructions: next });
  };

  const overviewItems = [
    'Client start point: open Dashboard first. Live summary cards refresh automatically and show current official record health.',
    'To start live review properly, move in this order: Events verification -> Analytics trend check -> Alerts action queue -> Manage controls.',
    'Control remains with client operators: verify each source link, acknowledge or resolve alerts, and apply changes from Manage before final decisions.',
  ];

  const startControlItems = [
    'Step 1: Click Start Live Sync on this page, then review dashboard health snapshot.',
    'Step 2: Open Events and verify source URL, source time, event time, and location.',
    'Step 3: Open Analytics to review trend direction and risk distribution from stored records.',
    'Step 4: Open Alerts to prioritize high/critical items, then acknowledge or resolve after review.',
    'Step 5: Open Manage to control auto-refresh cadence and run manual sync actions.',
    'Step 6: Use About instructions when needed for verification workflow support.',
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Command Center</h1>
          <p className="page-subtitle">Operational summary based on official stored organization data and computed risk records.</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <span className="pulse" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-emerald)' }} />
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Official-only live view | Updated {formatDateTime(stats?.generated_at)}
          </span>
        </div>
      </div>

      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          marginBottom: 24,
          border: '2px solid var(--accent-cyan)',
          background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.12), rgba(99, 102, 241, 0.08))',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
          <div>
            <h3 style={{ fontSize: 17, fontWeight: 800, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              <SlidersHorizontal size={18} style={{ color: 'var(--accent-cyan)' }} />
              Live Operations Hub
            </h3>
            <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.65, maxWidth: 720 }}>
              Client controls are now centralized in Manage. Live sync, analytics refresh, and UI behavior stay aligned across all dashboard pages.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={handleStartLiveSync}
              disabled={liveSyncing}
              className="btn btn-primary"
              style={{ opacity: liveSyncing ? 0.7 : 1, cursor: liveSyncing ? 'not-allowed' : 'pointer' }}
            >
              <RefreshCw size={16} />
              {liveSyncing ? 'Starting Live Sync...' : 'Start Live Sync'}
            </button>
            <Link href="/dashboard/manage" className="btn btn-ghost">
              <SlidersHorizontal size={16} />
              Manage
            </Link>
            <Link href="/dashboard/about" className="btn btn-ghost">
              About
              <ArrowRight size={16} />
            </Link>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleToggleInstructions}
              title={showInstructions ? 'Hide instructions' : 'Show instructions'}
              aria-label={showInstructions ? 'Hide instructions' : 'Show instructions'}
            >
              <Info size={16} />
            </button>
          </div>
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
          {autoRefreshEnabled
            ? `Live auto-refresh is active every ${refreshSeconds} seconds.`
            : 'Live auto-refresh is paused. You can enable it from Manage.'}
        </div>
      </motion.div>

      {showInstructions && (
        <motion.div
          className="glass-card"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ marginBottom: 24 }}
        >
          <h3 style={{ fontSize: 16, fontWeight: 800, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <BookOpen size={18} style={{ color: 'var(--accent-indigo)' }} />
            Optional Client Instructions
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
            {overviewItems.map((item) => (
              <p key={item} style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
                {item}
              </p>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 10 }}>
            {startControlItems.map((item) => (
              <div key={item} style={{ padding: '10px 12px', borderRadius: 10, background: 'var(--bg-hover)', border: '1px solid var(--border-primary)', fontSize: 12, lineHeight: 1.55 }}>
                {item}
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {(liveMessage || lastLiveSync) && (
        <div className="glass-card" style={{ marginBottom: 24, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {liveMessage || 'Live sync ready.'}
          {lastLiveSync ? ` Last sync ${formatDateTime(lastLiveSync)}.` : ''}
        </div>
      )}

      <div className="grid-4" style={{ marginBottom: 24 }}>
        {metricCards.map((card, i) => (
          <motion.div
            key={card.label}
            className="metric-card"
            custom={i}
            initial="hidden"
            animate="visible"
            variants={cardVariants}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span className="metric-label">{card.label}</span>
              <card.icon size={18} style={{ color: card.color }} />
            </div>
            <span className="metric-value" style={{ color: card.color }}>{card.value}</span>
          </motion.div>
        ))}
      </div>

      <div style={{ marginBottom: 24 }}>
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.42 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
              <AlertTriangle size={18} style={{ color: 'var(--accent-rose)' }} />
              Recent Alerts
            </h3>
            {alerts.length > 0 && (
              <button
                onClick={handleClearAlerts}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--accent-rose)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                <Trash2 size={14} /> Clear
              </button>
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {alerts.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: 14, padding: 24, textAlign: 'center' }}>No active alerts yet. Live sync will populate this panel when verified risk thresholds are crossed.</p>
            ) : (
              alerts.slice(0, 5).map((alert: any) => (
                <div
                  key={alert.id}
                  style={{
                    padding: '12px 16px',
                    background: 'var(--bg-hover)',
                    borderRadius: 'var(--radius-sm)',
                    borderLeft: `3px solid ${
                      alert.priority === 'critical' ? 'var(--accent-rose)'
                        : alert.priority === 'high' ? 'var(--accent-amber)'
                          : 'var(--accent-indigo)'
                    }`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      {alert.event_id ? (
                        <Link
                          href={`/dashboard/events?event=${alert.event_id}`}
                          style={{
                            fontSize: 13,
                            fontWeight: 700,
                            overflowWrap: 'anywhere',
                            lineHeight: 1.45,
                            color: 'var(--text-primary)',
                          }}
                        >
                          {sanitizeStoredText(alert.title) || 'Untitled alert'}
                        </Link>
                      ) : (
                        <span style={{ fontSize: 13, fontWeight: 600, overflowWrap: 'anywhere', lineHeight: 1.45 }}>
                          {sanitizeStoredText(alert.title) || 'Untitled alert'}
                        </span>
                      )}
                      {alert.source_url && (
                        <a
                          href={alert.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: 'var(--accent-indigo)', flexShrink: 0 }}
                          title="Verify source"
                        >
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </div>
                    <span className={`badge badge-${alert.priority}`}>{alert.priority}</span>
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                    {formatDateTime(alert.created_at)}
                  </p>
                </div>
              ))
            )}
          </div>
        </motion.div>
      </div>

      <div>
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <ShieldCheck size={18} style={{ color: 'var(--accent-emerald)' }} />
            Official Source Snapshot
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12, marginBottom: 16 }}>
            {[
              { label: 'Official', value: officialEvents },
              { label: 'Source Linked', value: sourceLinkedEvents },
              { label: 'Detail Ready', value: detailReadyCount },
              { label: 'Coverage', value: `${verificationCoverage}%` },
              { label: 'Duplicates', value: duplicateEvents },
              { label: 'Avg Confidence', value: averageConfidence.toFixed(2) },
            ].map((item) => (
              <div key={item.label} style={{ padding: 12, borderRadius: 12, background: 'var(--bg-hover)', border: '1px solid var(--border-primary)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{item.label}</div>
                <div style={{ fontSize: 22, fontWeight: 800, marginTop: 4 }}>{item.value}</div>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {verificationCoverage}% of official records currently include a stored source link. {detailReadyCount} records are ready for full-detail inspection and duplicates stay excluded from the default verified view.
          </p>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6, marginTop: 10 }}>
            Snapshot generated at {formatDateTime(stats?.generated_at)} | Coordinates available for {coordinateCount} official records
          </p>
        </motion.div>
      </div>
    </div>
  );
}
