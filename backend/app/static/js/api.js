/**
 * Orion Banking — API client
 * Handles token storage, automatic refresh on 401, and consistent error parsing.
 */
(function () {
  'use strict';

  const ACCESS_KEY = 'orion_access_token';
  const REFRESH_KEY = 'orion_refresh_token';
  const USER_KEY = 'orion_user';

  // ── Storage helpers ───────────────────────────────────────
  function getAccess() { return localStorage.getItem(ACCESS_KEY); }
  function getRefresh() { return localStorage.getItem(REFRESH_KEY); }
  function setTokens(access, refresh) {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  }
  function clearTokens() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  }
  function setUser(user) { localStorage.setItem(USER_KEY, JSON.stringify(user)); }
  function getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); }
    catch { return null; }
  }

  // ── Internal fetch wrapper ────────────────────────────────
  async function rawFetch(path, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    const token = getAccess();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const resp = await fetch(path, Object.assign({}, options, { headers }));
    return resp;
  }

  // ── Refresh on 401 ───────────────────────────────────────
  let refreshing = null;
  async function maybeRefresh(resp) {
    if (resp.status !== 401) return null;
    const refreshToken = getRefresh();
    if (!refreshToken) return null;
    if (refreshing) return refreshing;

    refreshing = (async () => {
      try {
        const r = await fetch('/api/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!r.ok) {
          clearTokens();
          return false;
        }
        const data = await r.json();
        setTokens(data.access_token, data.refresh_token);
        return true;
      } catch {
        clearTokens();
        return false;
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }

  async function request(path, options = {}) {
    let resp = await rawFetch(path, options);

    // Try refresh-on-401 once
    if (resp.status === 401) {
      const refreshed = await maybeRefresh(resp);
      if (refreshed) {
        resp = await rawFetch(path, options);
      } else {
        clearTokens();
        const event = new CustomEvent('orion:unauthorized');
        window.dispatchEvent(event);
      }
    }
    return resp;
  }

  // ── Public API ────────────────────────────────────────────
  function authHeader() {
    const token = getAccess();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  const api = {
    // Auth
    register: async (payload) => {
      const r = await request('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      return r.json().then((d) => ({ ok: r.ok, status: r.status, data: d }));
    },

    login: async (payload) => {
      const r = await request('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (r.ok && !data.needs_totp) {
        setTokens(data.access_token, data.refresh_token);
      }
      return { ok: r.ok, status: r.status, data };
    },

    verifyTotp: async (challengeToken, { code, backupCode } = {}) =>
      request('/api/auth/verify-totp', {
        method: 'POST',
        body: JSON.stringify({
          challenge_token: challengeToken,
          code: code || null,
          backup_code: backupCode || null,
        }),
      }).then((r) => r.json()),

    // ── 2FA / TOTP ──────────────────────────────────────────────
    totpStatus: () => fetch('/api/2fa/status', { headers: authHeader() }).then((r) => r.json()),
    totpSetup: () => fetch('/api/2fa/setup', { method: 'POST', headers: authHeader() }).then((r) => r.json()),
    totpVerifySetup: (code) =>
      fetch('/api/2fa/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ code }),
      }).then((r) => r.json()),
    totpDisable: (code, backupCode) =>
      fetch('/api/2fa/disable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ code: code || null, backup_code: backupCode || null }),
      }).then((r) => ({ ok: r.ok, status: r.status })),
    totpRegenerateBackupCodes: (code, backupCode) =>
      fetch('/api/2fa/regenerate-backup-codes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ code: code || null, backup_code: backupCode || null }),
      }).then((r) => r.json()),

    logout: async () => {
      try {
        await request('/api/auth/logout', { method: 'POST' });
      } catch (_) { /* ignore */ }
      clearTokens();
    },

    refresh: async () => {
      const r = await request('/api/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: getRefresh() }),
      });
      const data = await r.json();
      if (r.ok) setTokens(data.access_token, data.refresh_token);
      return { ok: r.ok, data };
    },

    // Account
    me: () => request('/api/accounts/me').then((r) => r.json()),
    updateProfile: (payload) =>
      request('/api/accounts/me', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }).then((r) => r.json()),
    updateKYC: (payload) =>
      request('/api/accounts/me/kyc', {
        method: 'PUT',
        body: JSON.stringify(payload),
      }).then((r) => r.json()),

    // Transactions
    deposit: (payload) =>
      request('/api/transactions/deposit', {
        method: 'POST',
        body: JSON.stringify(payload),
      }).then((r) => r.json()),
    withdraw: (payload) =>
      request('/api/transactions/withdraw', {
        method: 'POST',
        body: JSON.stringify(payload),
      }).then((r) => r.json()),
    transfer: (payload) =>
      request('/api/transactions/transfer', {
        method: 'POST',
        body: JSON.stringify(payload),
      }).then((r) => r.json()),
    listTransactions: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/transactions${q ? '?' + q : ''}`).then((r) => r.json());
    },
    getTransaction: (id) =>
      request(`/api/transactions/${id}`).then((r) => r.json()),

    // Analytics
    analyticsSummary: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return request(`/api/analytics/summary${q ? '?' + q : ''}`).then((r) => r.json());
    },

    // Notifications
    listNotifications: (unreadOnly = false) =>
      request(`/api/notifications${unreadOnly ? '?unread_only=true' : ''}`).then((r) => r.json()),
    markNotificationRead: (id) =>
      request(`/api/notifications/${id}/read`, { method: 'POST' }),
    markAllNotificationsRead: () =>
      request('/api/notifications/read-all', { method: 'POST' }),

    // Statements
    statementPdfUrl: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return `/api/statements/export.pdf${q ? '?' + q : ''}`;
    },

    // Admin
    adminStats: () => fetch('/api/admin/stats').then((r) => r.json()),
    adminListUsers: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return fetch(`/api/admin/users${q ? '?' + q : ''}`).then((r) => r.json());
    },
    adminGetUser: (id) => fetch(`/api/admin/users/${id}`).then((r) => r.json()),
    adminListPendingKyc: (params = {}) => {
      const q = new URLSearchParams(params).toString();
      return fetch(`/api/admin/kyc/pending${q ? '?' + q : ''}`).then((r) => r.json());
    },
    adminApproveKyc: (userId, notes = null) =>
      fetch(`/api/admin/kyc/${userId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes }),
      }).then((r) => r.json()),
    adminRejectKyc: (userId, reason) =>
      fetch(`/api/admin/kyc/${userId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      }).then((r) => r.json()),
    adminLockUser: (userId) =>
      fetch(`/api/admin/users/${userId}/lock`, { method: 'POST' }).then((r) => r.json()),
    adminUnlockUser: (userId) =>
      fetch(`/api/admin/users/${userId}/unlock`, { method: 'POST' }).then((r) => r.json()),

    // Helpers
    getAccess, getRefresh, setTokens, clearTokens, setUser, getUser,
    isAuthenticated: () => !!getAccess(),
  };

  window.OrionAPI = api;
})();
