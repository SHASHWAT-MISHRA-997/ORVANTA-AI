export type EventRecord = {
  id: string;
  title: string;
  description?: string | null;
  event_type: string;
  source: string;
  source_url?: string | null;
  source_id?: string | null;
  source_domain?: string | null;
  source_status?: 'official' | 'unverified' | string | null;
  source_status_reason?: string | null;
  country?: string | null;
  region?: string | null;
  city?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  severity?: number | null;
  confidence?: number | null;
  credibility_score?: number | null;
  is_verified?: number | null;
  is_duplicate?: number | null;
  tags?: unknown;
  actors?: unknown;
  raw_data?: unknown;
  event_date?: string | null;
  ingested_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  official_source?: EvidenceLink | null;
  supporting_sources?: EvidenceLink[] | null;
  video_links?: EvidenceLink[] | null;
  search_links?: EvidenceLink[] | null;
  detail_available?: boolean | null;
  detail_reason?: string | null;
  detail_missing_fields?: string[] | null;
  has_exact_coordinates?: boolean | null;
  location_precision?: string | null;
};

export type SourceTrustStatus = 'official' | 'unverified';
export type InterestCategory =
  | 'geopolitics'
  | 'cybersecurity'
  | 'technology'
  | 'innovation'
  | 'economy'
  | 'health'
  | 'climate'
  | 'supply_chain'
  | 'defense'
  | 'energy'
  | 'other';

export type EvidenceLink = {
  title: string;
  url: string;
  source: string;
  host?: string | null;
  kind?: string | null;
  category?: string | null;
  verified?: boolean | null;
  reason?: string | null;
  published_at?: string | null;
  snippet?: string | null;
};

const COUNTRY_ALIASES: Record<string, string> = {
  UK: 'United Kingdom',
  USA: 'United States',
  US: 'United States',
  UAE: 'United Arab Emirates',
  DPRK: 'North Korea',
  PRC: 'China',
};

const OFFICIAL_FEEDS = new Set([
  'cisa cyber alerts',
  'un news - peace and security',
  'reliefweb updates',
  'usgs significant earthquakes',
  'usgs m4.5+ earthquakes',
]);

const OFFICIAL_HOSTS = new Set([
  'cisa.gov',
  'news.un.org',
  'un.org',
  'reliefweb.int',
  'ochaopt.org',
  'who.int',
  'cdc.gov',
  'fema.gov',
  'usgs.gov',
  'state.gov',
  'whitehouse.gov',
  'europa.eu',
  'nato.int',
  'redcross.org',
  'icrc.org',
]);

const INTEREST_CATEGORY_RULES: Array<{ category: InterestCategory; keywords: string[] }> = [
  { category: 'cybersecurity', keywords: ['cyber', 'ransomware', 'malware', 'phishing', 'zero-day', 'ddos', 'breach', 'infosec'] },
  { category: 'technology', keywords: ['software', 'ai', 'ml', 'cloud', 'chip', 'semiconductor', 'data center', 'platform', 'saas'] },
  { category: 'innovation', keywords: ['innovation', 'startup', 'patent', 'research', 'breakthrough', 'prototype', 'r&d'] },
  { category: 'economy', keywords: ['inflation', 'gdp', 'trade', 'market', 'bank', 'economy', 'finance', 'tariff'] },
  { category: 'health', keywords: ['health', 'disease', 'outbreak', 'hospital', 'medical', 'who', 'pandemic', 'vaccine'] },
  { category: 'climate', keywords: ['climate', 'flood', 'wildfire', 'storm', 'hurricane', 'earthquake', 'drought', 'weather'] },
  { category: 'supply_chain', keywords: ['supply chain', 'logistics', 'shipment', 'port', 'manufacturing', 'freight'] },
  { category: 'defense', keywords: ['defense', 'military', 'army', 'air force', 'navy', 'border', 'security forces'] },
  { category: 'energy', keywords: ['energy', 'oil', 'gas', 'power', 'grid', 'electricity', 'nuclear', 'renewable'] },
  { category: 'geopolitics', keywords: ['sanction', 'conflict', 'diplomatic', 'election', 'policy', 'government', 'war', 'ceasefire'] },
];

function toText(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}

function decodeHtmlEntities(value: string): string {
  if (!value) return '';

  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    const textarea = document.createElement('textarea');
    textarea.innerHTML = value;
    return textarea.value;
  }

  return value
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCharCode(parseInt(code, 16)));
}

export function sanitizeStoredText(value: unknown): string {
  const text = toText(value);
  if (!text) return '';

  const withoutScripts = text
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ');
  const withoutTags = withoutScripts.replace(/<[^>]+>/g, ' ');
  const decoded = decodeHtmlEntities(withoutTags);

  return decoded.replace(/\s+/g, ' ').trim();
}

function getRawObject(rawData: unknown): Record<string, any> {
  return rawData && typeof rawData === 'object' && !Array.isArray(rawData)
    ? (rawData as Record<string, any>)
    : {};
}

function safeNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function extractPlaceSegments(place: unknown): { city: string; region: string; country: string } {
  const text = toText(place);
  if (!text) {
    return { city: '', region: '', country: '' };
  }

  const locationText = text.split(' of ', 2).pop()?.trim() || text;
  const segments = locationText.split(',').map((segment) => segment.trim()).filter(Boolean);

  if (segments.length === 0) {
    return { city: text, region: '', country: '' };
  }

  if (segments.length === 1) {
    return { city: segments[0], region: '', country: '' };
  }

  return {
    city: segments[0] || '',
    region: segments.slice(1, -1).join(', '),
    country: segments.at(-1) || '',
  };
}

function getLocationParts(event: Pick<EventRecord, 'city' | 'region' | 'country' | 'raw_data'>): {
  city: string;
  region: string;
  country: string;
} {
  const raw = getRawObject(event.raw_data);
  const placeParts = extractPlaceSegments(
    raw.place
    || raw.location_name
    || raw.address
    || raw.location
  );

  return {
    city: toText(event.city || raw.city || raw.locality || raw.town || raw.location_city || placeParts.city),
    region: toText(event.region || raw.region || raw.admin1 || raw.state || raw.province || raw.location_region || placeParts.region),
    country: toText(event.country || raw.country || raw.country_name || raw.sourcecountry || raw.location_country || placeParts.country),
  };
}

export function getEventCountry(event: Pick<EventRecord, 'country' | 'raw_data'>): string | null {
  const country = getLocationParts({
    city: undefined,
    region: undefined,
    country: event.country,
    raw_data: event.raw_data,
  }).country;
  return country || null;
}

export function getEventCoordinates(event: Pick<EventRecord, 'latitude' | 'longitude' | 'raw_data'>): {
  latitude: number | null;
  longitude: number | null;
} {
  const directLatitude = safeNumber(event.latitude);
  const directLongitude = safeNumber(event.longitude);
  if (directLatitude !== null && directLongitude !== null) {
    return { latitude: directLatitude, longitude: directLongitude };
  }

  const raw = getRawObject(event.raw_data);
  const coordinates = Array.isArray(raw.coordinates) ? raw.coordinates : [];
  const coordinateLatitude = safeNumber(coordinates[1]);
  const coordinateLongitude = safeNumber(coordinates[0]);
  if (coordinateLatitude !== null && coordinateLongitude !== null) {
    return { latitude: coordinateLatitude, longitude: coordinateLongitude };
  }

  const nestedWhere = raw.where && typeof raw.where === 'object' && !Array.isArray(raw.where)
    ? raw.where
    : {};
  const rawLatitude = safeNumber(raw.geo_lat ?? raw.latitude ?? raw.lat ?? nestedWhere.lat);
  const rawLongitude = safeNumber(raw.geo_lon ?? raw.longitude ?? raw.lon ?? raw.lng ?? raw.long ?? nestedWhere.lon ?? nestedWhere.lng ?? nestedWhere.long);
  if (rawLatitude !== null && rawLongitude !== null) {
    return { latitude: rawLatitude, longitude: rawLongitude };
  }

  const georssPoint = toText(raw.georss_point || raw.point);
  if (georssPoint) {
    const parts = georssPoint.replace(',', ' ').split(/\s+/).map((part) => safeNumber(part)).filter((value): value is number => value !== null);
    if (parts.length >= 2) {
      return { latitude: parts[0], longitude: parts[1] };
    }
  }

  return { latitude: null, longitude: null };
}

function parseDateValue(value: unknown): Date | null {
  if (value === null || value === undefined) return null;

  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  const text = String(value).trim();
  if (!text) return null;

  if (/^\d{14}$/.test(text)) {
    const year = Number(text.slice(0, 4));
    const month = Number(text.slice(4, 6)) - 1;
    const day = Number(text.slice(6, 8));
    const hour = Number(text.slice(8, 10));
    const minute = Number(text.slice(10, 12));
    const second = Number(text.slice(12, 14));
    const date = new Date(Date.UTC(year, month, day, hour, minute, second));
    return Number.isNaN(date.getTime()) ? null : date;
  }

  if (/^\d{8}$/.test(text)) {
    const year = Number(text.slice(0, 4));
    const month = Number(text.slice(4, 6)) - 1;
    const day = Number(text.slice(6, 8));
    const date = new Date(Date.UTC(year, month, day));
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function normalizeHost(url?: string | null): string {
  const value = toText(url);
  if (!value) return '';

  try {
    const host = new URL(value).hostname.toLowerCase();
    return host.replace(/^www\./, '');
  } catch {
    return value.toLowerCase().replace(/^www\./, '');
  }
}

function normalizeFeedName(raw: Record<string, any>): string {
  return toText(raw.feed || raw.source_name || raw.name).toLowerCase();
}

export function classifySourceTrust(event: Pick<EventRecord, 'source' | 'source_url' | 'raw_data' | 'source_status' | 'source_domain' | 'source_status_reason'>): {
  status: SourceTrustStatus;
  domain: string;
  reason: string;
} {
  const explicit = toText(event.source_status).toLowerCase();
  if (explicit === 'official' || explicit === 'unverified') {
    return {
      status: explicit as SourceTrustStatus,
      domain: toText(event.source_domain) || normalizeHost(event.source_url),
      reason: toText(event.source_status_reason) || 'Status provided by backend',
    };
  }

  const raw = getRawObject(event.raw_data);
  const host = normalizeHost(event.source_url || event.source_domain || raw.url || raw.link);
  const feedName = normalizeFeedName(raw);
  const sourceName = toText(event.source).toLowerCase();

  if (host && (host.endsWith('.gov') || host.endsWith('.mil') || OFFICIAL_HOSTS.has(host))) {
    return { status: 'official', domain: host, reason: `Official host: ${host}` };
  }

  if (feedName && OFFICIAL_FEEDS.has(feedName)) {
    return { status: 'official', domain: host, reason: `Official feed: ${raw.feed || raw.source_name || raw.name}` };
  }

  if (sourceName === 'manual' || sourceName === 'agent') {
    return { status: 'unverified', domain: host, reason: 'Manually entered or automation-generated record requires review' };
  }

  return { status: 'unverified', domain: host, reason: 'No official host or official feed match found' };
}

export function isOfficialSource(event: Pick<EventRecord, 'source' | 'source_url' | 'raw_data' | 'source_status' | 'source_domain' | 'source_status_reason'>): boolean {
  return classifySourceTrust(event).status === 'official';
}

export function formatSourceTrustLabel(status?: string | null): string {
  const value = toText(status).toLowerCase();
  if (value === 'official') return 'Official source';
  if (value === 'unverified') return 'Unverified source';
  return 'Source not classified';
}

export type LiveNewsAuthenticity = {
  verdict: 'likely_genuine' | 'needs_review' | 'possibly_misleading';
  label: string;
  reason: string;
};

export function classifyLiveNewsAuthenticity(
  event: Pick<EventRecord, 'source' | 'source_url' | 'raw_data' | 'source_status' | 'source_domain' | 'source_status_reason' | 'confidence'>
): LiveNewsAuthenticity {
  const trust = classifySourceTrust(event);
  const confidence = safeNumber(event.confidence) ?? 0;
  const hasSourceLink = Boolean(toText(event.source_url));

  if (trust.status === 'official') {
    return {
      verdict: 'likely_genuine',
      label: 'Likely Genuine',
      reason: trust.reason || 'Official source verification passed',
    };
  }

  if (!hasSourceLink && confidence < 50) {
    return {
      verdict: 'possibly_misleading',
      label: 'Possibly Misleading',
      reason: 'No source link and low confidence; treat as potentially unreliable until verified',
    };
  }

  return {
    verdict: 'needs_review',
    label: 'Needs Verification',
    reason: trust.reason || 'Insufficient official evidence; verify source before acting',
  };
}

export function formatDateTime(value?: string | Date | null): string {
  if (!value) return 'Not available';
  const date = parseDateValue(value);
  if (!date || Number.isNaN(date.getTime())) return toText(value);
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export function formatDateOnly(value?: string | Date | null): string {
  if (!value) return 'Not available';
  const date = parseDateValue(value);
  if (!date || Number.isNaN(date.getTime())) return toText(value);
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
  }).format(date);
}

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function formatSourceLabel(source?: string | null): string {
  const value = toText(source);
  if (!value) return 'Source not specified';

  const normalized = value.toLowerCase();
  if (normalized === 'gdelt') return 'GDELT';
  if (normalized === 'acled') return 'ACLED';
  if (normalized === 'rss') return 'RSS';
  if (normalized === 'manual') return 'Manual';
  if (normalized === 'agent') return 'Automated ingest';

  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

export function getEventSourceLabel(event: Pick<EventRecord, 'source' | 'source_url' | 'raw_data'>): string {
  const raw = getRawObject(event.raw_data);
  const rawLabel = toText(raw.feed || raw.source_name || raw.name || raw.publisher || raw.channel);
  if (rawLabel) return rawLabel;

  const host = normalizeHost(
    toText(event.source_url || raw.entry_link || raw.official_url || raw.report_url || raw.feed_url || raw.url || raw.link)
  );
  if (host) return host;

  return formatSourceLabel(event.source);
}

export function getCountryDisplayName(country?: string | null): string {
  const value = toText(country);
  if (!value || value.toLowerCase() === 'unknown') return 'Country not available';

  const alias = COUNTRY_ALIASES[value.toUpperCase()];
  if (alias) return alias;

  if (value.length <= 3 && /^[A-Za-z]{2,3}$/.test(value) && typeof Intl !== 'undefined' && 'DisplayNames' in Intl) {
    try {
      const displayNames = new Intl.DisplayNames(['en'], { type: 'region' });
      const resolved = displayNames.of(value.toUpperCase());
      if (resolved) return resolved;
    } catch {
      // Fall back to the raw value below.
    }
  }

  return value;
}

export function formatLocation(event: Pick<EventRecord, 'city' | 'region' | 'country' | 'raw_data'>): string {
  const locationParts = getLocationParts(event);
  const parts = [
    toText(locationParts.city),
    toText(locationParts.region),
    getCountryDisplayName(locationParts.country),
  ]
    .filter((part) => part && part.toLowerCase() !== 'country not available' && part.toLowerCase() !== 'unknown');
  if (parts.length === 0) return 'Location not available';
  return parts.join(', ');
}

function composeSearchQuery(event: Pick<EventRecord, 'title' | 'city' | 'region' | 'country' | 'raw_data'>): string {
  const location = formatLocation(event);
  return [sanitizeStoredText(event.title), location]
    .filter((part) => part && part !== 'Location not available')
    .join(' ')
    .trim();
}

export function buildGoogleMapsUrl(event: Pick<EventRecord, 'title' | 'latitude' | 'longitude' | 'city' | 'region' | 'country' | 'raw_data'>): string | null {
  const coordinates = getEventCoordinates(event);
  if (coordinates.latitude !== null && coordinates.longitude !== null) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${coordinates.latitude},${coordinates.longitude}`)}`;
  }

  const query = [formatLocation(event), toText(event.title)]
    .filter((part) => part && part !== 'Location not available')
    .join(' ')
    .trim();
  if (query) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  }

  return null;
}

export function buildGoogleNewsUrl(event: Pick<EventRecord, 'title' | 'city' | 'region' | 'country' | 'raw_data'>): string {
  const query = composeSearchQuery(event);
  return `https://news.google.com/search?q=${encodeURIComponent(query)}`;
}

export function buildTranslateUrl(text: string, targetLanguage: string): string {
  const safeText = sanitizeStoredText(text) || text;
  return `https://translate.google.com/?sl=auto&tl=${encodeURIComponent(targetLanguage)}&text=${encodeURIComponent(safeText)}&op=translate`;
}

export function inferInterestCategories(event: Pick<EventRecord, 'title' | 'description' | 'event_type' | 'source' | 'raw_data'>): InterestCategory[] {
  const raw = getRawObject(event.raw_data);
  const haystack = [
    sanitizeStoredText(event.title),
    sanitizeStoredText(event.description),
    toText(event.event_type),
    toText(event.source),
    sanitizeStoredText(raw.summary || raw.snippet || raw.description || raw.feed || raw.source_name),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  const matched = INTEREST_CATEGORY_RULES
    .filter((rule) => rule.keywords.some((keyword) => haystack.includes(keyword)))
    .map((rule) => rule.category);

  return matched.length > 0 ? Array.from(new Set(matched)) : ['other'];
}

export function buildGoogleSearchUrl(event: Pick<EventRecord, 'title' | 'city' | 'region' | 'country' | 'raw_data'>): string {
  const query = composeSearchQuery(event);
  return `https://www.google.com/search?q=${encodeURIComponent(query)}`;
}

export function buildYouTubeSearchUrl(event: Pick<EventRecord, 'title' | 'city' | 'region' | 'country' | 'raw_data'>): string {
  const title = sanitizeStoredText(event.title);
  const location = formatLocation(event);
  const query = [title ? `"${title}"` : '', location !== 'Location not available' ? location : '']
    .filter(Boolean)
    .join(' ')
    .trim() || composeSearchQuery(event);
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
}

export function getHostname(url?: string | null): string {
  const value = toText(url);
  if (!value) return 'Source host not available';

  try {
    return new URL(value).hostname.replace(/^www\./, '');
  } catch {
    return value;
  }
}

export function getSourceTimeValue(event: Pick<EventRecord, 'raw_data'>): string | null {
  const raw = getRawObject(event.raw_data);
  const candidates = [
    raw.published_at,
    raw.published,
    raw.seen_at,
    raw.seendate,
    raw.updated_at,
    raw.updated,
    raw.source_time,
    raw.reported_at,
  ];

  for (const candidate of candidates) {
    const text = toText(candidate);
    if (text) return text;
  }

  return null;
}

export function formatSourceTime(event: Pick<EventRecord, 'raw_data'>): string {
  const raw = getRawObject(event.raw_data);
  const value = getSourceTimeValue(event);
  if (!value) return 'Not supplied by source';

  const label = raw.published_at || raw.published
    ? 'Published at'
    : raw.seen_at || raw.seendate
      ? 'Seen at'
      : raw.updated_at || raw.updated
        ? 'Updated at'
        : 'Source time';

  return `${label} ${formatDateTime(value)}`;
}

export function getCoordinateLabel(event: Pick<EventRecord, 'latitude' | 'longitude' | 'raw_data'>): string {
  const coordinates = getEventCoordinates(event);
  if (coordinates.latitude === null || coordinates.longitude === null) {
    return 'Coordinates not supplied by source';
  }

  return `${coordinates.latitude.toFixed(4)}, ${coordinates.longitude.toFixed(4)}`;
}

export function hasLocationValue(event: Pick<EventRecord, 'city' | 'region' | 'country' | 'raw_data'>): boolean {
  return formatLocation(event) !== 'Location not available';
}

export function hasCountryValue(event: Pick<EventRecord, 'country' | 'raw_data'>): boolean {
  return getCountryDisplayName(getEventCountry(event)) !== 'Country not available';
}

export function hasLocationPrecisionValue(value?: string | null): boolean {
  return toText(value).toLowerCase() !== 'unknown' && toText(value) !== '';
}

export function hasCoordinateValue(event: Pick<EventRecord, 'latitude' | 'longitude' | 'raw_data'>): boolean {
  const coordinates = getEventCoordinates(event);
  return coordinates.latitude !== null && coordinates.longitude !== null;
}

export function getRecordActivityLabel(event: Pick<EventRecord, 'created_at' | 'ingested_at' | 'updated_at'>): string {
  if (toText(event.updated_at)) {
    return `Updated ${formatDateTime(event.updated_at)}`;
  }
  if (toText(event.ingested_at)) {
    return `Ingested ${formatDateTime(event.ingested_at)}`;
  }
  if (toText(event.created_at)) {
    return `Stored ${formatDateTime(event.created_at)}`;
  }
  return 'Not available';
}

export function getEvidenceLinks(value: unknown): EvidenceLink[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is EvidenceLink => {
    return Boolean(
      item
      && typeof item === 'object'
      && !Array.isArray(item)
      && typeof (item as EvidenceLink).url === 'string'
      && typeof (item as EvidenceLink).title === 'string'
    );
  });
}

export function getOfficialSource(event: EventRecord | null | undefined): EvidenceLink | null {
  if (!event?.official_source || typeof event.official_source !== 'object') {
    return null;
  }

  return event.official_source as EvidenceLink;
}

export function getSupportingSources(event: EventRecord | null | undefined): EvidenceLink[] {
  return getEvidenceLinks(event?.supporting_sources);
}

export function getVideoLinks(event: EventRecord | null | undefined): EvidenceLink[] {
  return getEvidenceLinks(event?.video_links);
}

export function getSearchLinks(event: EventRecord | null | undefined): EvidenceLink[] {
  return getEvidenceLinks(event?.search_links);
}

export function getSearchLinkByKind(event: EventRecord | null | undefined, kind: string): EvidenceLink | null {
  return getSearchLinks(event).find((link) => toText(link.kind).toLowerCase() === kind.toLowerCase()) || null;
}

export function formatLocationPrecision(value?: string | null): string {
  const normalized = toText(value).toLowerCase();
  if (normalized === 'exact') return 'Exact coordinates';
  if (normalized === 'place') return 'City or region';
  if (normalized === 'country') return 'Country only';
  return 'Unknown precision';
}

export function formatEvidenceKind(value?: string | null): string {
  const normalized = toText(value).toLowerCase();
  if (normalized === 'official') return 'Official source';
  if (normalized === 'coverage') return 'Trusted coverage';
  if (normalized === 'video') return 'Verified video';
  if (normalized === 'news_search') return 'News search';
  if (normalized === 'video_search') return 'Video search';
  if (normalized === 'web_search') return 'Web search';
  if (normalized === 'map') return 'Map';
  return 'Reference';
}
