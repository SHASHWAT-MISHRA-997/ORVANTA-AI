import axios from 'axios';

const DEFAULT_API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

function normalizeApiUrl(url: string) {
  return url.replace(/\/+$/, '');
}

function resolveApiUrl(): string {
  if (typeof window === 'undefined') {
    return normalizeApiUrl(DEFAULT_API_URL);
  }

  const hostname = window.location.hostname;
  const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';

  if (!isLocalhost) {
    return normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL || `${window.location.origin}/api/v1`);
  }

  if (window.location.port === '8080') {
    return `${window.location.origin.replace(/\/$/, '')}/api/v1`;
  }

  return `${window.location.protocol}//${hostname}:8080/api/v1`;
}

const apiBaseUrl = resolveApiUrl();

const api = axios.create({
  baseURL: apiBaseUrl,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

// JWT interceptor
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('warops_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    const detail = err.response?.data?.detail;

    if (err.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('warops_token');
      window.location.href = '/login';
    }

    if (
      status === 403 &&
      typeof window !== 'undefined' &&
      typeof detail === 'string' &&
      detail.toLowerCase().includes('disabled')
    ) {
      localStorage.removeItem('warops_token');
      window.location.href = '/login';
    }

    return Promise.reject(err);
  }
);

// Auth
export const authAPI = {
  register: (data: any) => api.post('/auth/register', data),
  login: (data: any) => api.post('/auth/login', data),
  loginWithGoogle: (data: { credential: string }) => api.post('/auth/google', data),
  loginWithClerk: (data: { clerk_token: string; email?: string; full_name?: string }) => api.post('/auth/clerk', data),
  loginWithSupabase: (data: {
    access_token: string;
    username?: string;
    full_name?: string;
    org_name?: string;
  }) => api.post('/auth/supabase', data),
  forgotPassword: (data: { email: string }) => api.post('/auth/forgot-password', data),
  resetPassword: (data: { token: string; new_password: string }) => api.post('/auth/reset-password', data),
  me: () => api.get('/auth/me'),
};

// Dashboard
export const dashboardAPI = {
  getStats: () => api.get('/dashboard'),
};

// Events
export const eventsAPI = {
  list: (params?: any) => api.get('/events', { params }),
  get: (id: string) => api.get(`/events/${id}`),
  create: (data: any) => api.post('/events', data),
  liveSync: (data?: { force?: boolean }) => api.post('/events/live-sync', data || {}),
};

// Risk Scores
export const riskAPI = {
  list: (params?: any) => api.get('/risk-score', { params }),
  compute: (data?: any) => api.post('/risk-score/compute', data || {}),
  trends: (days?: number) => api.get('/risk-score/trends', { params: { days: days || 30 } }),
};

// Alerts
export const alertsAPI = {
  list: (params?: any) => api.get('/alerts', { params }),
  acknowledge: (id: string) => api.post(`/alerts/${id}/ack`),
  resolve: (id: string) => api.post(`/alerts/${id}/resolve`),
  dismiss: (id: string) => api.post(`/alerts/${id}/dismiss`),
  clearAll: () => api.delete('/alerts/clear'),
};

export const watchlistsAPI = {
  list: () => api.get('/watchlists'),
  create: (data: any) => api.post('/watchlists', data),
  remove: (id: string) => api.delete(`/watchlists/${id}`),
};

export const organizationsAPI = {
  resetThresholds: () => api.post('/organizations/reset-thresholds'),
  clearThresholds: () => api.post('/organizations/clear-thresholds'),
  clearAllData: () => api.post('/organizations/clear-all-data'),
};

export const developerAPI = {
  listUsers: () => api.get('/developer/users'),
  releaseUser: (userId: string) => api.post(`/developer/users/${userId}/release`),
  releaseAllUsers: () => api.post('/developer/users/release-all'),
  clearReleasedUsers: () => api.delete('/developer/users/released'),
};

export const assistantAPI = {
  chat: (data: {
    message: string;
    history?: Array<{ role: 'user' | 'assistant'; content: string }>;
    client_now_iso?: string;
    client_tz_offset_minutes?: number;
  }) => api.post('/chat', data),
};

export default api;
