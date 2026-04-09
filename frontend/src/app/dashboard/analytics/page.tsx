'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { riskAPI, dashboardAPI, eventsAPI } from '@/lib/api';
import {
  BarChart3, TrendingUp, PieChart as PieIcon, Target,
  RotateCcw, RefreshCw, ShieldCheck, Clock3, Sparkles,
} from 'lucide-react';
import {
  EventRecord,
  formatDateTime,
  formatLocation,
  getEventSourceLabel,
  getOfficialSource,
  getSourceTimeValue,
  isOfficialSource,
  sanitizeStoredText,
} from '@/lib/event-utils';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  CartesianGrid,
} from 'recharts';
import { getLiveUiPreferences } from '@/lib/live-ui-preferences';

const COLORS = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#f43f5e', '#a855f7', '#ec4899', '#14b8a6'];
const TIMELINE_WINDOWS = [
  { label: '7D', days: 7 },
  { label: '14D', days: 14 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
];

function formatShortDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  }).format(date);
}

function getTimelineTimestamp(event: EventRecord) {
  return event.event_date || getSourceTimeValue(event) || event.created_at || null;
}

function getRiskLevelBadge(level: string) {
  if (level === 'critical') return 'badge-critical';
  if (level === 'high') return 'badge-high';
  if (level === 'medium') return 'badge-medium';
  return 'badge-low';
}

function buildRiskDrivers(score: any) {
  const drivers: string[] = [];
  if (Number(score?.severity_component) >= 0.8) drivers.push('high event severity');
  else if (Number(score?.severity_component) >= 0.6) drivers.push('elevated event severity');

  if (Number(score?.confidence_component) >= 0.75) drivers.push('strong confidence');
  if (Number(score?.proximity_component) >= 0.85) drivers.push('high proximity impact');
  if (Number(score?.supply_chain_weight) > 1.05) drivers.push('supply-chain chokepoint weight');
  if (Number(score?.region_weight) > 1.05) drivers.push('regional strategic weight');

  if (Number(score?.time_decay_factor) >= 0.7) drivers.push('fresh timeline');
  else if (Number(score?.time_decay_factor) < 0.4) drivers.push('older timing reduced impact');

  return drivers;
}

function buildRiskHeadline(score: any) {
  const drivers = buildRiskDrivers(score);
  if (drivers.length === 0) {
    return 'This score comes directly from the stored severity, confidence, proximity, time-decay, regional, and supply-chain factors.';
  }

  if (score?.risk_level === 'critical') {
    return `Critical score because ${drivers.slice(0, 3).join(', ')}.`;
  }

  if (score?.risk_level === 'high') {
    return `High score because ${drivers.slice(0, 3).join(', ')}.`;
  }

  return `Current score is mainly shaped by ${drivers.slice(0, 3).join(', ')}.`;
}

export default function AnalyticsPage() {
  const [trends, setTrends] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [riskScores, setRiskScores] = useState<any>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [days, setDays] = useState(30);
  const [replayDays, setReplayDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState('');
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshSeconds, setRefreshSeconds] = useState(15);

  const load = useCallback(async (rangeDays = days, sync = false, force = false) => {
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

      const [trendsRes, statsRes, riskRes, eventsRes] = await Promise.allSettled([
        riskAPI.trends(rangeDays),
        dashboardAPI.getStats(),
        riskAPI.list({ limit: 200 }),
        eventsAPI.list({ page: 1, page_size: 200 }),
      ]);
      if (trendsRes.status === 'fulfilled') setTrends(trendsRes.value.data.trends || []);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
      if (riskRes.status === 'fulfilled') setRiskScores(riskRes.value.data);
      if (eventsRes.status === 'fulfilled') setEvents(eventsRes.value.data.events || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    const preferences = getLiveUiPreferences();
    setAutoRefreshEnabled(preferences.autoRefresh);
    setRefreshSeconds(preferences.refreshSeconds);
  }, []);

  useEffect(() => {
    void load(days, false);

    if (!autoRefreshEnabled) {
      return;
    }

    const interval = window.setInterval(() => {
      void load(days, false);
    }, refreshSeconds * 1000);

    return () => window.clearInterval(interval);
  }, [days, load, autoRefreshEnabled, refreshSeconds]);

  const handleRefresh = () => void load(days, false);
  const handleClearView = () => {
    setDays(30);
    setReplayDays(30);
    void load(30, false);
  };

  const officialEvents = events.filter((event) => isOfficialSource(event));
  const eventMap = Object.fromEntries(officialEvents.map((event) => [String(event.id), event]));

  const riskDistribution = riskScores?.scores
    ? (() => {
        const distribution: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 };
        riskScores.scores.forEach((score: any) => {
          distribution[score.risk_level] = (distribution[score.risk_level] || 0) + 1;
        });
        return Object.entries(distribution).map(([level, count]) => ({ level, count }));
      })()
    : [];

  const riskColors: Record<string, string> = {
    critical: '#f43f5e',
    high: '#f59e0b',
    medium: '#6366f1',
    low: '#10b981',
  };

  const trendPointsWithScores = trends.filter((point) => typeof point?.average_score === 'number');
  const hasTrendData = trendPointsWithScores.length > 0;
  const hasSingleTrendDay = trendPointsWithScores.length === 1;
  const chartMaxScore = hasTrendData
    ? Math.max(25, Math.ceil(Math.max(...trendPointsWithScores.map((point) => Number(point.average_score) || 0)) / 10) * 10)
    : 100;
  const chartMaxEventCount = hasTrendData
    ? Math.max(1, ...trendPointsWithScores.map((point) => Number(point.event_count) || 0))
    : 1;

  const replayWindow = TIMELINE_WINDOWS.find((window) => window.days === replayDays) || TIMELINE_WINDOWS[2];
  const replayCutoff = Date.now() - replayDays * 24 * 60 * 60 * 1000;
  const replayEvents = officialEvents
    .map((event) => ({ event, timestamp: getTimelineTimestamp(event) }))
    .filter((item) => {
      if (!item.timestamp) return false;
      const value = new Date(item.timestamp).getTime();
      return !Number.isNaN(value) && value >= replayCutoff;
    })
    .sort((a, b) => new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime());

  const explainabilityItems = [...(riskScores?.scores || [])]
    .sort((a: any, b: any) => (Number(b.overall_score) || 0) - (Number(a.overall_score) || 0))
    .slice(0, 5)
    .map((score: any) => ({
      score,
      event: eventMap[String(score.event_id)] || null,
      drivers: buildRiskDrivers(score),
      headline: buildRiskHeadline(score),
    }));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Analytics</h1>
          <p className="page-subtitle">
            Dedicated trend analysis from stored risk scores and aggregated event records. {autoRefreshEnabled ? `Live refresh ${refreshSeconds}s.` : 'Live refresh paused.'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[7, 14, 30, 90].map((range) => (
            <button
              key={range}
              className={`btn ${days === range ? 'btn-primary' : 'btn-ghost'} btn-sm`}
              onClick={() => setDays(range)}
            >
              {range}D
            </button>
          ))}
          <button className="btn btn-ghost btn-sm" onClick={handleClearView}>
            <RotateCcw size={14} />
            Reset Range
          </button>
          <button className="btn btn-ghost btn-sm" onClick={handleRefresh}>
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {(liveMessage || lastSyncedAt) && (
        <motion.div
          className="glass-card"
          style={{ marginBottom: 24, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          {liveMessage || 'Live analytics checked.'}
          {lastSyncedAt ? ` Last sync ${formatDateTime(lastSyncedAt)}.` : ''}
        </motion.div>
      )}

      <motion.div
        className="glass-card"
        style={{ marginBottom: 24 }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              <ShieldCheck size={18} style={{ color: 'var(--accent-emerald)' }} />
              Data Provenance
            </h3>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, maxWidth: 760 }}>
              These analytics use official stored records for your organization. The trend chart plots real event days with stored risk scores instead
              of stretching empty dates across the graph. Timeline Replay uses official event timestamps from the stored record, and Risk Score
              Explainability breaks down the same stored severity, confidence, proximity, time-decay, regional, and supply-chain factors used by the backend.
              Full-detail ready records: {stats?.detail_ready_events || 0}. Watchlist alerts created on sync are merged into the same alert queue.
            </p>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'right' }}>
            <div>{loading ? 'Refreshing analytics...' : 'Showing actual stored metrics'}</div>
            <div>Current as of {formatDateTime(stats?.generated_at)}</div>
          </div>
        </div>
      </motion.div>

      <div className="grid-4" style={{ marginBottom: 24 }}>
        {[
          { label: 'Avg Risk Score', value: riskScores?.average_score?.toFixed(1) || '--', icon: Target, color: 'var(--accent-indigo)' },
          { label: 'Critical Risks', value: riskScores?.critical_count || 0, icon: TrendingUp, color: 'var(--accent-rose)' },
          { label: 'High Risks', value: riskScores?.high_count || 0, icon: BarChart3, color: 'var(--accent-amber)' },
          { label: 'Events Tracked', value: stats?.total_events || 0, icon: PieIcon, color: 'var(--accent-cyan)' },
        ].map((card, i) => (
          <motion.div
            key={card.label}
            className="metric-card"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span className="metric-label">{card.label}</span>
              <card.icon size={18} style={{ color: card.color }} />
            </div>
            <span className="metric-value" style={{ color: card.color }}>{card.value}</span>
          </motion.div>
        ))}
      </div>

      <motion.div className="glass-card" style={{ marginBottom: 24 }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>
          Risk Score Trend by Event Timeline - {days} Days
        </h3>
        {hasTrendData ? (
          <>
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={trendPointsWithScores}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(75,85,99,0.2)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#6b7280', fontSize: 11 }}
                  tickFormatter={formatShortDate}
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                  tickCount={Math.min(6, trendPointsWithScores.length)}
                  minTickGap={24}
                />
                <YAxis
                  yAxisId="score"
                  tick={{ fill: '#6b7280', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, chartMaxScore]}
                />
                <YAxis
                  yAxisId="count"
                  orientation="right"
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, chartMaxEventCount]}
                />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#f9fafb' }}
                  labelFormatter={(label) => formatDateTime(label)}
                  formatter={(value: any, name: string) => {
                    if (name === 'Avg Score') {
                      return [value == null ? 'Not available' : value, name];
                    }
                    return [value, name];
                  }}
                />
                <Bar yAxisId="count" dataKey="event_count" fill="rgba(6,182,212,0.32)" radius={[4, 4, 0, 0]} name="Events" />
                <Line yAxisId="count" type="linear" dataKey="critical_count" stroke="#f43f5e" strokeWidth={2} dot={false} name="Critical Events" />
                <Line yAxisId="score" type="linear" dataKey="average_score" stroke="#6366f1" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 5 }} name="Avg Score" />
              </ComposedChart>
            </ResponsiveContainer>
            <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
              {hasSingleTrendDay
                ? 'Only one stored event day is available in this range, so the chart is limited to that real point.'
                : 'The chart shows only real days with stored risk scores, which keeps the timeline cleaner and avoids misleading empty-day shapes.'}
            </p>
          </>
        ) : (
          <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--text-muted)' }}>
            No stored risk scores fall inside this timeline range yet. Sync live data or compute scores to populate this chart with real records.
          </div>
        )}
      </motion.div>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.28 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Risk Level Distribution</h3>
          {riskDistribution.some((item) => item.count > 0) ? (
            <>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={riskDistribution} cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={4} dataKey="count" nameKey="level">
                    {riskDistribution.map((entry: any) => (
                      <Cell key={entry.level} fill={riskColors[entry.level] || '#6366f1'} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#f9fafb' }} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', justifyContent: 'center', gap: 16, marginTop: 8, flexWrap: 'wrap' }}>
                {riskDistribution.map((risk: any) => (
                  <span key={risk.level} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: riskColors[risk.level] }} />
                    {risk.level}: {risk.count}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--text-muted)' }}>
              No stored risk score rows are available yet for distribution analysis.
            </div>
          )}
        </motion.div>

        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.36 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Events by Type</h3>
          {(stats?.events_by_type || []).length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={stats?.events_by_type || []} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(75,85,99,0.2)" />
                <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 11 }} />
                <YAxis type="category" dataKey="event_type" tick={{ fill: '#9ca3af', fontSize: 11 }} width={110} />
                <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#f9fafb' }} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {(stats?.events_by_type || []).map((_: any, i: number) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--text-muted)' }}>
              No official stored events are available yet for event-type analysis.
            </div>
          )}
        </motion.div>
      </div>

      <div className="grid-2">
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.44 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Clock3 size={18} style={{ color: 'var(--accent-cyan)' }} />
                Timeline Replay
              </h3>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
                Replay official stored events over the last {replayWindow.label.toLowerCase()} to review investigations with a cleaner timeline.
              </p>
            </div>
            <div style={{ width: 'min(320px, 100%)' }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {TIMELINE_WINDOWS.map((window) => (
                  <button
                    key={window.label}
                    className={`btn ${replayDays === window.days ? 'btn-primary' : 'btn-ghost'} btn-sm`}
                    onClick={() => setReplayDays(window.days)}
                  >
                    {window.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {replayEvents.length === 0 ? (
            <div style={{ minHeight: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--text-muted)' }}>
              No official stored events fall inside the selected replay window yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 420, overflowY: 'auto', paddingRight: 4 }}>
              {replayEvents.slice(0, 18).map(({ event, timestamp }) => (
                <Link
                  key={event.id}
                  href={`/dashboard/events?event=${event.id}`}
                  style={{
                    display: 'block',
                    padding: 12,
                    borderRadius: 12,
                    border: '1px solid var(--border-primary)',
                    background: 'var(--bg-hover)',
                    color: 'var(--text-primary)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 6 }}>
                    <span className="badge badge-medium">{event.event_type.replace(/_/g, ' ')}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{formatDateTime(timestamp)}</span>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.5 }}>{sanitizeStoredText(event.title) || 'Untitled event'}</div>
                  <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    {formatLocation(event)} | {getEventSourceLabel(event)}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </motion.div>

        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.52 }}>
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Sparkles size={18} style={{ color: 'var(--accent-indigo)' }} />
              Risk Score Explainability
            </h3>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
              Why each score is high, which factors amplified it, and which stored source record it came from.
            </p>
          </div>

          {explainabilityItems.length === 0 ? (
            <div style={{ minHeight: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--text-muted)' }}>
              No stored risk scores are available yet for explainability review.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxHeight: 420, overflowY: 'auto', paddingRight: 4 }}>
              {explainabilityItems.map(({ score, event, drivers, headline }) => {
                const officialSource = event ? getOfficialSource(event) : null;
                return (
                  <div key={score.id} style={{ padding: 12, borderRadius: 12, border: '1px solid var(--border-primary)', background: 'var(--bg-hover)' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        {event ? (
                          <Link
                            href={`/dashboard/events?event=${score.event_id}`}
                            style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.5, color: 'var(--text-primary)' }}
                            className="hover:underline"
                          >
                            {sanitizeStoredText(event.title) || 'Untitled event'}
                          </Link>
                        ) : (
                          <div style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.5 }}>Event {String(score.event_id)}</div>
                        )}
                        <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                          {event ? `${formatLocation(event)} | ${getEventSourceLabel(event)}` : 'Stored event metadata is not available in this view.'}
                        </div>
                      </div>
                      <span className={`badge ${getRiskLevelBadge(score.risk_level)}`}>
                        {score.risk_level} {Number(score.overall_score || 0).toFixed(1)}
                      </span>
                    </div>

                    <p style={{ margin: '0 0 10px', fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      {headline}
                    </p>

                    {drivers.length > 0 && (
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                        {drivers.map((driver) => (
                          <span key={driver} className="badge badge-medium" style={{ textTransform: 'none', letterSpacing: 0 }}>
                            {driver}
                          </span>
                        ))}
                      </div>
                    )}

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                      <div>Severity factor: {Number(score.severity_component || 0).toFixed(2)}</div>
                      <div>Confidence factor: {Number(score.confidence_component || 0).toFixed(2)}</div>
                      <div>Proximity factor: {Number(score.proximity_component || 0).toFixed(2)}</div>
                      <div>Time-decay factor: {Number(score.time_decay_factor || 0).toFixed(2)}</div>
                      <div>Supply-chain weight: {Number(score.supply_chain_weight || 0).toFixed(2)}</div>
                      <div>Region weight: {Number(score.region_weight || 0).toFixed(2)}</div>
                    </div>

                    <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      Evidence contribution: {officialSource?.source || (event ? getEventSourceLabel(event) : 'Stored source not available')}.
                      {officialSource?.url && (
                        <>
                          {' '}
                          <a href={officialSource.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-cyan)' }}>
                            Open source
                          </a>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
