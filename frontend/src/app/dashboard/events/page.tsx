'use client';

import { Suspense, type ReactNode, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { eventsAPI, watchlistsAPI } from '@/lib/api';
import {
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  ExternalLink,
  Filter,
  Link2,
  LocateFixed,
  MapPin,
  Search,
  ShieldCheck,
} from 'lucide-react';
import {
  buildGoogleMapsUrl,
  EventRecord,
  getEventCoordinates,
  getEventCountry,
  getEventSourceLabel,
  formatDateTime,
  formatLocation,
  formatLocationPrecision,
  formatSourceTime,
  getRecordActivityLabel,
  getCoordinateLabel,
  getCountryDisplayName,
  getOfficialSource,
  getHostname,
  hasCoordinateValue,
  hasCountryValue,
  hasLocationPrecisionValue,
  hasLocationValue,
  isOfficialSource,
  sanitizeStoredText,
} from '@/lib/event-utils';
import { getLiveUiPreferences } from '@/lib/live-ui-preferences';

const cardVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.28 },
  }),
};

function normalize(value: unknown): string {
  return String(value ?? '').toLowerCase().trim();
}

function listify(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).filter(Boolean);
  }
  if (typeof value === 'string') {
    return value.split(',').map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

type SavedWatchlist = {
  id: string;
  name: string;
  keyword?: string | null;
  country?: string | null;
  source?: string | null;
  event_type?: string | null;
  matched_event_count?: number;
  alerts_created?: number;
  created_at?: string;
  last_matched_at?: string | null;
};

function buildWatchlistName(filters: {
  searchTerm: string;
  sourceFilter: string;
  countryFilter: string;
  typeFilter: string;
}) {
  const parts = [
    filters.countryFilter ? `Country: ${filters.countryFilter}` : '',
    filters.sourceFilter ? `Source: ${filters.sourceFilter}` : '',
    filters.typeFilter ? `Type: ${filters.typeFilter.replace(/_/g, ' ')}` : '',
    filters.searchTerm ? `Keyword: ${filters.searchTerm.trim()}` : '',
  ].filter(Boolean);

  return parts.join(' | ') || 'Saved Watchlist';
}

function formatWatchlistSummary(watchlist: SavedWatchlist) {
  return [
    watchlist.country ? `Country ${watchlist.country}` : '',
    watchlist.source ? `Source ${watchlist.source}` : '',
    watchlist.event_type ? `Type ${watchlist.event_type.replace(/_/g, ' ')}` : '',
    watchlist.keyword ? `Keyword ${watchlist.keyword}` : '',
  ].filter(Boolean).join(' | ');
}

function eventMatchesWatchlist(event: EventRecord, watchlist: SavedWatchlist) {
  const keyword = normalize(watchlist.keyword);
  const source = normalize(watchlist.source);
  const country = normalize(watchlist.country);
  const eventType = normalize(watchlist.event_type);
  const sourceLabel = normalize(getEventSourceLabel(event));
  const eventCountry = normalize(getCountryDisplayName(getEventCountry(event)));
  const location = normalize(formatLocation(event));
  const textBlob = [
    sanitizeStoredText(event.title),
    sanitizeStoredText(event.description),
    formatLocation(event),
    getEventSourceLabel(event),
    getCountryDisplayName(getEventCountry(event)),
    listify(event.tags).join(' '),
    listify(event.actors).join(' '),
  ].map((value) => String(value || '')).join(' ').toLowerCase();

  if (keyword && !textBlob.includes(keyword)) return false;
  if (source && sourceLabel !== source) return false;
  if (country && eventCountry !== country && location !== country) return false;
  if (eventType && normalize(event.event_type) !== eventType) return false;

  return true;
}

function EventsPageSuspenseFallback() {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Event Explorer</h1>
          <p className="page-subtitle">Loading live event records...</p>
        </div>
      </div>
      <div className="grid-4" style={{ marginBottom: 24 }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton" style={{ height: 100 }} />
        ))}
      </div>
      <div className="grid-2">
        <div className="skeleton" style={{ height: 680 }} />
        <div className="skeleton" style={{ height: 680 }} />
      </div>
    </div>
  );
}

function EventsPageContent() {
  const searchParams = useSearchParams();
  const selectedEventId = searchParams.get('event') || '';

  const [events, setEvents] = useState<EventRecord[]>([]);
  const [detailEvent, setDetailEvent] = useState<EventRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [countryFilter, setCountryFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [selectedEventMessage, setSelectedEventMessage] = useState<string | null>(null);
  const [watchlists, setWatchlists] = useState<SavedWatchlist[]>([]);
  const [savingWatchlist, setSavingWatchlist] = useState(false);
  const [deletingWatchlistId, setDeletingWatchlistId] = useState('');
  const [watchlistMessage, setWatchlistMessage] = useState<string | null>(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshSeconds, setRefreshSeconds] = useState(15);

  const loadWatchlists = async () => {
    try {
      const res = await watchlistsAPI.list();
      setWatchlists(res.data || []);
    } catch (err) {
      console.error('watchlists_load_error', err);
    }
  };

  const loadEvents = async (silent = false, sync = false, force = false) => {
    if (!silent && loading) {
      setLoading(true);
    }

    try {
      if (sync) {
        try {
          const syncRes = await eventsAPI.liveSync({ force });
          setLiveMessage(syncRes.data?.message || null);
          setLastSyncedAt(syncRes.data?.synced_at || new Date().toISOString());
        } catch (syncErr) {
          console.error('events_live_sync_error', syncErr);
        }
      }

      const res = await eventsAPI.list({ page: 1, page_size: 200 });
      const nextEvents: EventRecord[] = res.data.events || [];
      setEvents(nextEvents);
      setLastSyncedAt((current) => current || new Date().toISOString());

      if (selectedEventId) {
        const match = nextEvents.find((event) => event.id === selectedEventId);
        if (match) {
          setDetailEvent(match);
          setSelectedEventMessage(null);
        } else {
          try {
            const detailRes = await eventsAPI.get(selectedEventId);
            setDetailEvent(detailRes.data);
            setSelectedEventMessage(null);
          } catch {
            setDetailEvent(null);
            setSelectedEventMessage('This record is not available in official-only mode. If it exists, it is hidden because it is not official-source verified.');
          }
        }
      } else {
        setDetailEvent(null);
        setSelectedEventMessage(null);
      }
    } catch (err) {
      console.error('events_load_error', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const preferences = getLiveUiPreferences();
    setAutoRefreshEnabled(preferences.autoRefresh);
    setRefreshSeconds(preferences.refreshSeconds);
  }, []);

  useEffect(() => {
    void loadEvents(false, false);
    void loadWatchlists();

    if (!autoRefreshEnabled) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadEvents(true, false);
    }, refreshSeconds * 1000);

    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEventId, autoRefreshEnabled, refreshSeconds]);

  const saveCurrentFiltersAsWatchlist = async () => {
    if (!hasActiveFilters) {
      setWatchlistMessage('Set at least one filter before saving a watchlist.');
      return;
    }

    setSavingWatchlist(true);
    try {
      const payload = {
        name: buildWatchlistName({ searchTerm, sourceFilter, countryFilter, typeFilter }),
        keyword: searchTerm.trim() || undefined,
        source: sourceFilter || undefined,
        country: countryFilter || undefined,
        event_type: typeFilter || undefined,
      };
      const res = await watchlistsAPI.create(payload);
      setWatchlistMessage(
        `Watchlist saved. ${res.data.matched_event_count || 0} current matches and ${res.data.alerts_created || 0} alerts created.`
      );
      await loadWatchlists();
    } catch (err: any) {
      setWatchlistMessage(err.response?.data?.detail || 'Failed to save watchlist');
    } finally {
      setSavingWatchlist(false);
    }
  };

  const deleteWatchlist = async (watchlistId: string) => {
    setDeletingWatchlistId(watchlistId);
    try {
      await watchlistsAPI.remove(watchlistId);
      setWatchlistMessage('Watchlist deleted.');
      await loadWatchlists();
    } catch (err: any) {
      setWatchlistMessage(err.response?.data?.detail || 'Failed to delete watchlist');
    } finally {
      setDeletingWatchlistId('');
    }
  };

  const applyWatchlistFilters = (watchlist: SavedWatchlist) => {
    setSearchTerm(watchlist.keyword || '');
    setSourceFilter(watchlist.source || '');
    setCountryFilter(watchlist.country || '');
    setTypeFilter(watchlist.event_type || '');
    setWatchlistMessage(`Applied watchlist "${watchlist.name}".`);
  };

  const visibleEvents = events.filter((event) => {
    const isOfficial = isOfficialSource(event);
    const search = normalize(searchTerm);
    const source = normalize(sourceFilter);
    const country = normalize(countryFilter);
    const type = normalize(typeFilter);
    const sourceLabel = normalize(getEventSourceLabel(event));
    const sourceHost = normalize(event.source_domain || getHostname(event.source_url));
    const location = normalize(formatLocation(event));
    const derivedCountry = getEventCountry(event);
    const displayCountry = normalize(getCountryDisplayName(derivedCountry));
    const rawCountry = normalize(derivedCountry);
    const title = normalize(sanitizeStoredText(event.title));
    const description = normalize(sanitizeStoredText(event.description));
    const tags = normalize(listify(event.tags).join(' '));
    const actors = normalize(listify(event.actors).join(' '));
    const sourceTime = normalize(formatSourceTime(event));
    const primarySourceUrl = normalize(getOfficialSource(event)?.url || event.source_url);

    const matchesSearch =
      !search ||
      title.includes(search) ||
      description.includes(search) ||
      location.includes(search) ||
      sourceLabel.includes(search) ||
      sourceHost.includes(search) ||
      rawCountry.includes(search) ||
      displayCountry.includes(search) ||
      normalize(event.event_type).includes(search) ||
      normalize(event.source_url).includes(search) ||
      primarySourceUrl.includes(search) ||
      sourceTime.includes(search) ||
      tags.includes(search) ||
      actors.includes(search);

    const matchesSource = !source || sourceLabel === source;
    const matchesCountry =
      !country
      || rawCountry === country
      || displayCountry === country
      || (country === 'not available / not stored' && !rawCountry);
    const matchesType = !type || normalize(event.event_type) === type;

    return isOfficial && matchesSearch && matchesSource && matchesCountry && matchesType;
  });

  const officialEvents = events.filter((event) => isOfficialSource(event));
  const totalEvents = officialEvents.length;
  const sourceLinkedCount = officialEvents.filter((event) => Boolean(getOfficialSource(event)?.url || event.source_url)).length;
  const coordinateCount = officialEvents.filter((event) => {
    const coordinates = getEventCoordinates(event);
    return coordinates.latitude != null && coordinates.longitude != null;
  }).length;
  const detailReadyCount = officialEvents.filter((event) => event.detail_available).length;
  const countryCount = new Set(
    officialEvents.map((event) => getCountryDisplayName(getEventCountry(event))).filter((value) => value && value !== 'Country not available')
  ).size;

  const hasActiveFilters = Boolean(searchTerm || sourceFilter || countryFilter || typeFilter);
  const visibleSelectedEvent = selectedEventId
    ? visibleEvents.find((event) => event.id === selectedEventId) || null
    : null;
  const selectedEvent = selectedEventId
    ? (visibleSelectedEvent || (hasActiveFilters ? (visibleEvents[0] || null) : detailEvent))
    : (visibleEvents[0] || null);
  const selectedPrimarySource = getOfficialSource(selectedEvent);
  const selectedLocation = selectedEvent ? formatLocation(selectedEvent) : 'Location not available';
  const selectedCountry = selectedEvent ? getCountryDisplayName(getEventCountry(selectedEvent)) : 'Country not available';
  const selectedHasLocation = selectedEvent ? hasLocationValue(selectedEvent) : false;
  const selectedHasCountry = selectedEvent ? hasCountryValue(selectedEvent) && selectedCountry !== selectedLocation : false;
  const selectedHasPrecision = selectedEvent ? hasLocationPrecisionValue(selectedEvent.location_precision) : false;
  const selectedHasCoordinates = selectedEvent ? hasCoordinateValue(selectedEvent) : false;
  const selectedGoogleMapsUrl = selectedEvent && selectedHasCoordinates ? buildGoogleMapsUrl(selectedEvent) : null;
  const selectedDetailMissingFields = Array.isArray(selectedEvent?.detail_missing_fields)
    ? Array.from(new Set(selectedEvent.detail_missing_fields.filter(Boolean)))
    : [];
  const selectedDetailFields = selectedEvent ? [
    selectedHasLocation ? { label: 'Location', value: selectedLocation } : null,
    selectedHasCountry ? { label: 'Country', value: selectedCountry } : null,
    selectedHasPrecision ? { label: 'Location Precision', value: formatLocationPrecision(selectedEvent.location_precision) } : null,
    selectedHasCoordinates ? { label: 'Coordinates', value: getCoordinateLabel(selectedEvent) } : null,
    getHostname(selectedPrimarySource?.url || selectedEvent.source_url) !== 'Source host not available'
      ? { label: 'Source Host', value: getHostname(selectedPrimarySource?.url || selectedEvent.source_url) }
      : null,
    (selectedPrimarySource?.url || selectedEvent.source_url)
      ? {
          label: 'Source Link',
          value: (
            <a
              href={selectedPrimarySource?.url || selectedEvent.source_url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
              style={{ color: 'var(--accent-cyan)', wordBreak: 'break-word' }}
            >
              {selectedPrimarySource?.url || selectedEvent.source_url}
            </a>
          ),
        }
      : null,
    selectedEvent.source_id ? { label: 'Source ID', value: selectedEvent.source_id } : null,
    formatSourceTime(selectedEvent) !== 'Not supplied by source' ? { label: 'Source Time', value: formatSourceTime(selectedEvent) } : null,
    selectedEvent.event_date ? { label: 'Event Date', value: formatDateTime(selectedEvent.event_date) } : null,
    getRecordActivityLabel(selectedEvent) !== 'Not available' ? { label: 'Record Activity', value: getRecordActivityLabel(selectedEvent) } : null,
  ].filter(Boolean) as Array<{ label: string; value: ReactNode }> : [];
  const watchlistRows = watchlists.map((watchlist) => ({
    ...watchlist,
    matchedCount: officialEvents.filter((event) => eventMatchesWatchlist(event, watchlist)).length,
  }));

  const sourceOptions = Array.from(
    new Set(officialEvents.map((event) => getEventSourceLabel(event)).filter(Boolean))
  ).sort();
  const storedCountryOptions = Array.from(
    new Set(
      officialEvents
        .map((event) => getCountryDisplayName(getEventCountry(event)))
        .filter((value) => value && value !== 'Country not available')
    )
  ).sort();
  const hasUnknownCountryRecords = officialEvents.some((event) => !normalize(getEventCountry(event)));
  const countryOptions = hasUnknownCountryRecords
    ? [...storedCountryOptions, 'Not available / not stored']
    : storedCountryOptions;
  const typeOptions = Array.from(new Set(officialEvents.map((event) => event.event_type))).sort();

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <div>
            <h1 className="page-title">Event Explorer</h1>
            <p className="page-subtitle">Loading live event records...</p>
          </div>
        </div>
        <div className="grid-4" style={{ marginBottom: 24 }}>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton" style={{ height: 100 }} />
          ))}
        </div>
        <div className="grid-2">
          <div className="skeleton" style={{ height: 680 }} />
          <div className="skeleton" style={{ height: 680 }} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Event Explorer</h1>
          <p className="page-subtitle">
            Inspect stored official records with traceable source, time, and location. Events remain visible from stored official data regardless of dashboard workflow changes.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span className="pulse" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-emerald)' }} />
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            {autoRefreshEnabled
              ? `Live feed auto-refreshes every ${refreshSeconds} seconds`
              : 'Live feed auto-refresh paused in Manage'}
          </span>
        </div>
      </div>

      {(liveMessage || lastSyncedAt) && (
        <div className="glass-card" style={{ marginBottom: 20, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {liveMessage || 'Live feed checked.'}
          {lastSyncedAt ? ` Last sync ${formatDateTime(lastSyncedAt)}.` : ''}
        </div>
      )}

      <div className="glass-card" style={{ marginBottom: 20, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
        Event Explorer is the stored record view. This page reads directly from verified stored events, independent from optional guidance panels.
      </div>

      <div className="grid-4" style={{ marginBottom: 24 }}>
        {[
          { label: 'Official Records', value: totalEvents, icon: BadgeCheck, color: 'var(--accent-emerald)' },
          { label: 'Source Linked', value: sourceLinkedCount, icon: ExternalLink, color: 'var(--accent-emerald)' },
          { label: 'Exact Coordinates', value: coordinateCount, icon: MapPin, color: 'var(--accent-cyan)' },
          { label: 'Countries', value: countryCount, icon: LocateFixed, color: 'var(--accent-rose)' },
        ].map((card, i) => (
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

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Search size={16} style={{ color: 'var(--accent-indigo)' }} />
            <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Filter and Inspect</h3>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Search</span>
              <input
                className="input"
                placeholder="Search title, country, source, or location"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Source</span>
              <select className="input" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
                <option value="">All sources</option>
                {sourceOptions.map((source) => (
                  <option key={source} value={source}>{source}</option>
                ))}
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Country</span>
              <select className="input" value={countryFilter} onChange={(e) => setCountryFilter(e.target.value)}>
                <option value="">All countries</option>
                {countryOptions.map((country) => (
                  <option key={country} value={country}>{country}</option>
                ))}
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase' }}>Type</span>
              <select className="input" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <option value="">All types</option>
                {typeOptions.map((type) => (
                  <option key={type} value={type}>{type.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </label>
          </div>

          <div style={{ padding: 14, borderRadius: 12, background: 'var(--bg-hover)', border: '1px solid var(--border-primary)', marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                  Saved Filters and Watchlists
                </div>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                  Save the current filter combination and create alerts whenever a newly stored official record matches it.
                </p>
              </div>
              <button className="btn btn-primary btn-sm" onClick={saveCurrentFiltersAsWatchlist} disabled={savingWatchlist}>
                {savingWatchlist ? 'Saving...' : 'Save Current Filters'}
              </button>
            </div>

            {watchlistMessage && (
              <p style={{ margin: '0 0 10px', fontSize: 12, color: 'var(--text-secondary)' }}>
                {watchlistMessage}
              </p>
            )}

            {watchlistRows.length === 0 ? (
              <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
                No watchlists saved yet.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {watchlistRows.map((watchlist) => (
                  <div key={watchlist.id} style={{ padding: 12, borderRadius: 12, border: '1px solid var(--border-primary)', background: 'rgba(255,255,255,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{watchlist.name}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                          {formatWatchlistSummary(watchlist) || 'Saved filter combination'}
                        </div>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                          <span className="badge badge-low">{watchlist.matchedCount} matches now</span>
                          {watchlist.last_matched_at && (
                            <span className="badge badge-medium">last match {formatDateTime(watchlist.last_matched_at)}</span>
                          )}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button className="btn btn-ghost btn-sm" onClick={() => applyWatchlistFilters(watchlist)}>
                          Use
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => deleteWatchlist(watchlist.id)}
                          disabled={deletingWatchlistId === watchlist.id}
                          style={{ color: 'var(--accent-rose)' }}
                        >
                          {deletingWatchlistId === watchlist.id ? 'Deleting...' : 'Delete'}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.6 }}>
              Showing {visibleEvents.length} of {totalEvents} official records. {detailReadyCount} are full-detail ready.
            </p>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
              {lastSyncedAt ? `Last synced ${formatDateTime(lastSyncedAt)}` : 'Waiting for first sync'}
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxHeight: 620, overflowY: 'auto', paddingRight: 4 }}>
            {visibleEvents.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>
                <Filter size={28} style={{ opacity: 0.35, marginBottom: 8 }} />
                <p style={{ lineHeight: 1.7 }}>
                  {totalEvents === 0
                    ? 'No official-source records are available right now. Automatic verified feed sync will add records here when they are stored.'
                    : 'No official records match the current filters.'}
                </p>
              </div>
            ) : (
              visibleEvents.map((event, i) => {
                const isSelected = selectedEventId === event.id;
                return (
                  <motion.div
                    key={event.id}
                    custom={i}
                    initial="hidden"
                    animate="visible"
                    variants={cardVariants}
                  >
                    <Link
                      href={`/dashboard/events?event=${event.id}`}
                      className="glass-card"
                      style={{
                        display: 'block',
                        padding: 18,
                        borderColor: isSelected ? 'var(--accent-indigo)' : 'var(--border-primary)',
                        boxShadow: isSelected ? '0 0 0 1px rgba(99, 102, 241, 0.35), var(--shadow-glow)' : undefined,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                            <span className={`badge ${
                              event.is_duplicate === 1 ? 'badge-high' : 'badge-low'
                            }`}>
                              {event.is_duplicate === 1 ? 'duplicate' : 'official'}
                            </span>
                            {event.source_url ? (
                              <span className="badge badge-low">source linked</span>
                            ) : (
                              <span className="badge badge-medium">no source link</span>
                            )}
                            <span className={`badge ${event.detail_available ? 'badge-low' : 'badge-medium'}`}>
                              {event.detail_available ? 'detail ready' : 'partial detail'}
                            </span>
                            <span className="badge badge-medium">{getEventSourceLabel(event)}</span>
                          </div>

                          <h3 style={{ fontSize: 15, fontWeight: 800, lineHeight: 1.45, margin: 0, wordBreak: 'break-word' }}>
                            {sanitizeStoredText(event.title) || 'Untitled event'}
                          </h3>
                          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0 0', lineHeight: 1.6 }}>
                            {formatLocation(event)}
                          </p>

                          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                            <span>Type: {event.event_type.replace(/_/g, ' ')}</span>
                            <span>Severity: {event.severity ?? 0}/10</span>
                            <span>Confidence: {(Number(event.confidence) || 0).toFixed(2)}</span>
                            <span>Stored: {formatDateTime(event.created_at)}</span>
                          </div>
                        </div>

                        <ArrowRight size={16} style={{ color: 'var(--text-muted)', flexShrink: 0, marginTop: 4 }} />
                      </div>
                    </Link>
                  </motion.div>
                );
              })
            )}
          </div>
        </motion.div>

        <motion.div className="glass-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, delay: 0.08 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
                Record Detail
              </h3>
              <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
                {selectedEvent
                  ? selectedEvent.detail_available
                    ? 'Showing all stored evidence-backed fields for this record. Verified links and lookup tools are separated clearly.'
                    : 'Showing every stored field that is available. Missing fields remain marked as unavailable instead of being filled artificially.'
                  : 'Select an official record to inspect its provenance.'}
              </p>
            </div>
            {selectedEvent && (
              <span className={`badge ${selectedEvent.detail_available ? 'badge-low' : 'badge-medium'}`}>
                {selectedEvent.detail_available ? 'detail ready' : 'partial detail'}
              </span>
            )}
          </div>

          {selectedEvent ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                      <span className={`badge ${selectedEvent.is_duplicate === 1 ? 'badge-high' : 'badge-low'}`}>
                        {selectedEvent.is_duplicate === 1 ? 'duplicate' : 'official'}
                      </span>
                      <span className="badge badge-medium">{getEventSourceLabel(selectedEvent)}</span>
                      <span className="badge badge-medium">{selectedEvent.event_type.replace(/_/g, ' ')}</span>
                      {(selectedEvent.has_exact_coordinates || selectedHasPrecision) && (
                        <span className={`badge ${selectedEvent.has_exact_coordinates ? 'badge-low' : 'badge-medium'}`}>
                          {selectedEvent.has_exact_coordinates ? 'exact map' : formatLocationPrecision(selectedEvent.location_precision)}
                        </span>
                      )}
                    </div>
                    <h2 style={{ fontSize: 22, fontWeight: 900, lineHeight: 1.35, marginBottom: 8, wordBreak: 'break-word' }}>
                      {sanitizeStoredText(selectedEvent.title) || 'Untitled event'}
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, margin: 0 }}>
                      {sanitizeStoredText(selectedEvent.description) || 'No description was stored for this event.'}
                    </p>
                    <p style={{ margin: '12px 0 0', fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                      {sanitizeStoredText(selectedEvent.detail_reason) || 'This record does not yet have a complete evidence bundle.'}
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 16 }}>
                  {(selectedPrimarySource?.url || selectedEvent.source_url) && (
                    <a
                      href={selectedPrimarySource?.url || selectedEvent.source_url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-primary btn-sm"
                    >
                      <CheckCircle2 size={14} />
                      Open source link
                    </a>
                  )}
                  {selectedGoogleMapsUrl && (
                    <a
                      href={selectedGoogleMapsUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-ghost btn-sm"
                    >
                      <MapPin size={14} />
                      Open Google Maps
                    </a>
                  )}
                </div>
              </div>

              {selectedDetailMissingFields.length > 0 && (
                <div style={{ padding: 14, borderRadius: 12, background: 'var(--bg-hover)', border: '1px solid var(--border-primary)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Link2 size={16} style={{ color: 'var(--accent-amber)' }} />
                    <strong style={{ fontSize: 14 }}>Missing Stored Fields</strong>
                  </div>
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    These fields were not fully stored with this record, so the view stays limited to what can actually be verified.
                  </p>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
                    {selectedDetailMissingFields.map((item) => (
                      <span key={item} className="badge badge-medium" style={{ textTransform: 'none', letterSpacing: 0 }}>
                        missing {item}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid-2">
                {selectedDetailFields.map((item) => (
                  <div key={item.label} style={{ padding: 14, borderRadius: 12, background: 'var(--bg-hover)', border: '1px solid var(--border-primary)' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                      {item.label}
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.5, wordBreak: 'break-word' }}>
                      {item.value}
                    </div>
                  </div>
                ))}
              </div>

              <div className="grid-2">
                <div style={{ padding: 14, borderRadius: 12, background: 'var(--bg-hover)', border: '1px solid var(--border-primary)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                    Confidence
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 800 }}>
                    {(Number(selectedEvent.confidence) || 0).toFixed(2)}
                  </div>
                </div>
                <div style={{ padding: 14, borderRadius: 12, background: 'var(--bg-hover)', border: '1px solid var(--border-primary)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                    Credibility
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 800 }}>
                    {(Number(selectedEvent.credibility_score) || 0).toFixed(2)}
                  </div>
                </div>
              </div>

              {(listify(selectedEvent.tags).length > 0 || listify(selectedEvent.actors).length > 0) && (
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  {listify(selectedEvent.tags).map((tag) => (
                    <span key={tag} className="badge badge-medium" style={{ textTransform: 'none', letterSpacing: 0 }}>
                      {tag}
                    </span>
                  ))}
                  {listify(selectedEvent.actors).map((actor) => (
                    <span key={actor} className="badge badge-low" style={{ textTransform: 'none', letterSpacing: 0 }}>
                      {actor}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div style={{ minHeight: 520, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'var(--text-muted)', gap: 8 }}>
              <ShieldCheck size={32} style={{ opacity: 0.35 }} />
              <p style={{ fontSize: 14, maxWidth: 340, lineHeight: 1.7, margin: 0 }}>
                Pick an official record on the left to inspect the stored source, timeline, missing fields, and evidence readiness.
              </p>
              {selectedEventId && selectedEventMessage && (
                <p style={{ fontSize: 13, maxWidth: 420, lineHeight: 1.7, margin: '4px 0 0', color: 'var(--text-secondary)' }}>
                  {selectedEventMessage}
                </p>
              )}
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}

export default function EventsPage() {
  return (
    <Suspense fallback={<EventsPageSuspenseFallback />}>
      <EventsPageContent />
    </Suspense>
  );
}
