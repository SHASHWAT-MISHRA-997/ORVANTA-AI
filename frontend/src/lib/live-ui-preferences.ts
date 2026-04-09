export type LiveUiPreferences = {
  autoRefresh: boolean;
  refreshSeconds: number;
  showInstructions: boolean;
  preferredLanguage: string;
  selectedCategories: string[];
  trustedSourcesOnly: boolean;
};

const STORAGE_KEY = 'orvanta_live_ui_preferences_v1';
const ALLOWED_REFRESH_SECONDS = new Set([10, 15, 30, 60]);

const DEFAULT_PREFERENCES: LiveUiPreferences = {
  autoRefresh: true,
  refreshSeconds: 15,
  showInstructions: false,
  preferredLanguage: 'en',
  selectedCategories: [],
  trustedSourcesOnly: false,
};

const ALLOWED_LANGUAGES = new Set(['en', 'hi', 'es', 'fr', 'de', 'ar', 'zh-CN', 'pt', 'ru', 'ja']);
const ALLOWED_CATEGORIES = new Set([
  'geopolitics',
  'cybersecurity',
  'technology',
  'innovation',
  'economy',
  'health',
  'climate',
  'supply_chain',
  'defense',
  'energy',
  'other',
]);

function sanitizePreferences(input: Partial<LiveUiPreferences> | null | undefined): LiveUiPreferences {
  const autoRefresh = typeof input?.autoRefresh === 'boolean'
    ? input.autoRefresh
    : DEFAULT_PREFERENCES.autoRefresh;
  const showInstructions = typeof input?.showInstructions === 'boolean'
    ? input.showInstructions
    : DEFAULT_PREFERENCES.showInstructions;
  const trustedSourcesOnly = typeof input?.trustedSourcesOnly === 'boolean'
    ? input.trustedSourcesOnly
    : DEFAULT_PREFERENCES.trustedSourcesOnly;

  const preferredLanguage = typeof input?.preferredLanguage === 'string' && ALLOWED_LANGUAGES.has(input.preferredLanguage)
    ? input.preferredLanguage
    : DEFAULT_PREFERENCES.preferredLanguage;

  const selectedCategories = Array.isArray(input?.selectedCategories)
    ? input.selectedCategories.filter((category): category is string => typeof category === 'string' && ALLOWED_CATEGORIES.has(category))
    : DEFAULT_PREFERENCES.selectedCategories;

  const candidateSeconds = Number(input?.refreshSeconds);
  const refreshSeconds = ALLOWED_REFRESH_SECONDS.has(candidateSeconds)
    ? candidateSeconds
    : DEFAULT_PREFERENCES.refreshSeconds;

  return {
    autoRefresh,
    refreshSeconds,
    showInstructions,
    preferredLanguage,
    selectedCategories,
    trustedSourcesOnly,
  };
}

export function getLiveUiPreferences(): LiveUiPreferences {
  if (typeof window === 'undefined') {
    return DEFAULT_PREFERENCES;
  }

  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (!stored) {
    return DEFAULT_PREFERENCES;
  }

  try {
    const parsed = JSON.parse(stored) as Partial<LiveUiPreferences>;
    return sanitizePreferences(parsed);
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function saveLiveUiPreferences(patch: Partial<LiveUiPreferences>): LiveUiPreferences {
  const next = sanitizePreferences({
    ...getLiveUiPreferences(),
    ...patch,
  });

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  return next;
}
