'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { alertsAPI, eventsAPI } from '@/lib/api';
import { AlertTriangle, Bell, CheckCircle, RefreshCw, ExternalLink, Trash2 } from 'lucide-react';
import { formatDateTime, sanitizeStoredText } from '@/lib/event-utils';
import { getLiveUiPreferences } from '@/lib/live-ui-preferences';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState('');
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshSeconds, setRefreshSeconds] = useState(15);

  const loadAlerts = useCallback(async (sync = false, force = false) => {
    setLoading(true);
    try {
      if (sync) {
        try {
          const syncRes = await eventsAPI.liveSync({ force });
          setLiveMessage(syncRes.data?.message || '');
          setLastSyncedAt(syncRes.data?.synced_at || new Date().toISOString());
        } catch (syncErr) {
          console.error(syncErr);
        }
      }

      const params: any = { limit: 50 };
      if (statusFilter) params.status = statusFilter;
      if (priorityFilter) params.priority = priorityFilter;
      const res = await alertsAPI.list(params);
      setAlerts(res.data.alerts || []);
      setTotal(res.data.total || 0);
      setActiveCount(res.data.active_count || 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [priorityFilter, statusFilter]);

  useEffect(() => {
    const preferences = getLiveUiPreferences();
    setAutoRefreshEnabled(preferences.autoRefresh);
    setRefreshSeconds(preferences.refreshSeconds);
  }, []);

  useEffect(() => {
    void loadAlerts(false);

    if (!autoRefreshEnabled) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadAlerts(false);
    }, refreshSeconds * 1000);

    return () => window.clearInterval(interval);
  }, [loadAlerts, autoRefreshEnabled, refreshSeconds]);

  const handleAcknowledge = async (id: string) => {
    try {
      await alertsAPI.acknowledge(id);
      await loadAlerts(false);
    } catch (err) {
      console.error(err);
    }
  };

  const handleResolve = async (id: string) => {
    try {
      await alertsAPI.resolve(id);
      await loadAlerts(false);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDismiss = async (id: string) => {
    try {
      await alertsAPI.dismiss(id);
      await loadAlerts(false);
    } catch (err) {
      console.error(err);
    }
  };

  const handleClearAll = async () => {
    if (window.confirm('Are you sure you want to delete ALL alerts? This action is permanent.')) {
      try {
        await alertsAPI.clearAll();
        await loadAlerts(false);
      } catch (err) {
        console.error(err);
      }
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">
            {activeCount} active alerts | {total} total | {autoRefreshEnabled ? `auto-refresh ${refreshSeconds}s` : 'auto-refresh paused'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-ghost" onClick={() => void loadAlerts(false)} disabled={loading}>
            <RefreshCw size={16} /> {loading ? 'Refreshing...' : 'Refresh'}
          </button>
          <button
            className="btn btn-ghost"
            onClick={handleClearAll}
            style={{ color: 'var(--accent-rose)', borderColor: 'var(--accent-rose)' }}
          >
            <Trash2 size={16} /> Clear All
          </button>
        </div>
      </div>

      {(liveMessage || lastSyncedAt) && (
        <div className="glass-card" style={{ marginBottom: 20, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {liveMessage || 'Live alerts checked.'}
          {lastSyncedAt ? ` Last sync ${formatDateTime(lastSyncedAt)}.` : ''}
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <select
          className="input"
          style={{ width: 'auto' }}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select
          className="input"
          style={{ width: 'auto' }}
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
        >
          <option value="">All Priorities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Priority</th>
              <th>Title</th>
              <th>Status</th>
              <th>Type</th>
              <th>Created</th>
              <th>Source URL</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {alerts.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
                  <Bell size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
                  <p>No alerts found. Automatic verified record sync will refresh this queue as new stored matches arrive.</p>
                </td>
              </tr>
            ) : (
              alerts.map((alert) => (
                <motion.tr
                  key={alert.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                >
                  <td><span className={`badge badge-${alert.priority}`}>{alert.priority}</span></td>
                  <td style={{ maxWidth: 420, whiteSpace: 'normal', lineHeight: 1.55 }}>
                    <div>
                      {alert.event_id ? (
                        <Link
                          href={`/dashboard/events?event=${alert.event_id}`}
                          style={{ fontWeight: 700, color: 'var(--text-primary)' }}
                          className="hover:underline"
                        >
                          {sanitizeStoredText(alert.title) || 'Untitled alert'}
                        </Link>
                      ) : (
                        <span style={{ fontWeight: 600 }}>{sanitizeStoredText(alert.title) || 'Untitled alert'}</span>
                      )}
                      {alert.meta_data?.watchlist_name && (
                        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>
                          Watchlist: {alert.meta_data.watchlist_name}
                        </div>
                      )}
                    </div>
                  </td>
                  <td>
                    <span
                      style={{
                        color: alert.status === 'active' ? 'var(--accent-rose)' :
                          alert.status === 'acknowledged' ? 'var(--accent-amber)' : 'var(--accent-emerald)',
                        fontWeight: 600,
                        fontSize: 12,
                      }}
                    >
                      {alert.status}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>{String(alert.alert_type).replace(/_/g, ' ')}</td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                    {formatDateTime(alert.created_at)}
                  </td>
                  <td>
                    {alert.source_url ? (
                      <a
                        href={alert.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--accent-indigo)', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}
                        className="hover:underline"
                      >
                        <ExternalLink size={12} /> Verify
                      </a>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>N/A</span>
                    )}
                  </td>
                  <td style={{ display: 'flex', gap: 4 }}>
                    {alert.event_id && (
                      <Link
                        href={`/dashboard/events?event=${alert.event_id}`}
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: 10, padding: '4px 10px' }}
                      >
                        <AlertTriangle size={14} /> View
                      </Link>
                    )}
                    {alert.status === 'active' && (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => handleAcknowledge(alert.id)}
                        title="Acknowledge"
                      >
                        <CheckCircle size={14} /> Ack
                      </button>
                    )}
                    {(alert.status === 'active' || alert.status === 'acknowledged') && (
                      <>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => handleResolve(alert.id)}
                          style={{ fontSize: 10, padding: '4px 10px' }}
                        >
                          Resolve
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => handleDismiss(alert.id)}
                          style={{ fontSize: 10, padding: '4px 10px', color: 'var(--accent-rose)' }}
                        >
                          Dismiss
                        </button>
                      </>
                    )}
                  </td>
                </motion.tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
