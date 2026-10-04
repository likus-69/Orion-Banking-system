/**
 * Orion Banking — UI utilities
 * Toasts, theme toggle, formatting, stars background, modal helpers.
 */
(function () {
  'use strict';

  // ── Stars background (canvas) ─────────────────────────────
  function initStars() {
    const canvas = document.getElementById('stars');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, stars = [];

    function resize() {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
      stars = [];
      const count = Math.min(80, Math.floor((w * h) / 18000));
      for (let i = 0; i < count; i++) {
        stars.push({
          x: Math.random() * w,
          y: Math.random() * h,
          r: Math.random() * 1.4 + 0.2,
          a: Math.random() * 0.8 + 0.2,
          twinkle: Math.random() * 0.02 + 0.005,
          phase: Math.random() * Math.PI * 2,
        });
      }
    }
    function draw(t) {
      ctx.clearRect(0, 0, w, h);
      for (const s of stars) {
        const a = s.a + Math.sin(t * s.twinkle + s.phase) * 0.3;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(232, 184, 92, ${Math.max(0, Math.min(1, a))})`;
        ctx.fill();
      }
      requestAnimationFrame(draw);
    }
    resize();
    window.addEventListener('resize', resize);
    requestAnimationFrame(draw);
  }

  // ── Theme (dark/light) ────────────────────────────────────
  function initTheme() {
    const saved = localStorage.getItem('orion_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    const toggle = document.querySelector('.theme-toggle');
    if (toggle) {
      toggle.textContent = saved === 'dark' ? '☀' : '☾';
      toggle.addEventListener('click', () => {
        const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('orion_theme', next);
        toggle.textContent = next === 'dark' ? '☀' : '☾';
      });
    }
  }

  // ── Toasts ────────────────────────────────────────────────
  function ensureToastContainer() {
    let c = document.getElementById('toastContainer');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toastContainer';
      document.body.appendChild(c);
    }
    return c;
  }
  function toast(message, level = 'info', duration = 3500) {
    const container = ensureToastContainer();
    const el = document.createElement('div');
    el.className = `toast ${level}`;
    el.innerHTML = `<span>${message}</span><button class="close" aria-label="Dismiss">×</button>`;
    container.appendChild(el);

    const close = () => {
      el.classList.add('removing');
      setTimeout(() => el.remove(), 250);
    };
    el.querySelector('.close').addEventListener('click', close);
    if (duration > 0) setTimeout(close, duration);
  }

  // ── Money / date formatting ────────────────────────────────
  function fmtMoney(n, withSign = false) {
    const v = Number(n || 0);
    const s = v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (withSign && v > 0) return `+$${s}`;
    if (withSign && v < 0) return `-$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    return `$${s}`;
  }
  function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  }
  function fmtDateShort(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
  }

  // ── Modal helpers ─────────────────────────────────────────
  function confirmModal({ title, body, confirmLabel = 'Confirm', danger = false }) {
    return new Promise((resolve) => {
      const backdrop = document.createElement('div');
      backdrop.className = 'modal-backdrop';
      backdrop.innerHTML = `
        <div class="modal" role="dialog" aria-modal="true">
          <h3>${title}</h3>
          <p>${body}</p>
          <div class="actions">
            <button class="btn ghost" data-action="cancel">Cancel</button>
            <button class="btn ${danger ? 'danger' : ''}" data-action="confirm">${confirmLabel}</button>
          </div>
        </div>`;
      document.body.appendChild(backdrop);
      function close(value) {
        backdrop.remove();
        resolve(value);
      }
      backdrop.querySelector('[data-action=cancel]').addEventListener('click', () => close(false));
      backdrop.querySelector('[data-action=confirm]').addEventListener('click', () => close(true));
      backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) close(false);
      });
    });
  }

  // ── Auth guard for protected pages ────────────────────────
  function requireAuth(redirect = '/login') {
    if (!window.OrionAPI.isAuthenticated()) {
      window.location.href = redirect;
      return false;
    }
    return true;
  }

  // ── Logout handling ───────────────────────────────────────
  function initLogoutButton() {
    const btn = document.querySelector('[data-action=logout]');
    if (!btn) return;
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const ok = await window.OrionUI.confirmModal({
        title: 'Log out?',
        body: 'You will need to sign in again to access your account.',
        confirmLabel: 'Log out',
        danger: true,
      });
      if (!ok) return;
      await window.OrionAPI.logout();
      window.location.href = '/login';
    });
  }

  // ── Init ──────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initStars();
    initLogoutButton();

    window.addEventListener('orion:unauthorized', () => {
      window.OrionUI.toast('Your session has expired. Please sign in again.', 'warn', 5000);
      setTimeout(() => { window.location.href = '/login'; }, 1500);
    });
  });

  // ── Export ────────────────────────────────────────────────
  window.OrionUI = {
    toast,
    fmtMoney,
    fmtDate,
    fmtDateShort,
    confirmModal,
    requireAuth,
  };
})();
