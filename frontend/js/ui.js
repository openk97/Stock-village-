/**
 * ui.js — Production-grade UI component library (vanilla, dependency-free).
 *
 * SENIOR FRONTEND ENGINEERING: reusable + accessible + loading/empty/error
 * states baked in. Setiap komponen punya DUA bentuk API:
 *   - UI.<name>.html(props)  -> string HTML murni (unit-testable, template-able)
 *   - UI.<name>.mount(el, props) -> attach + event wiring; kembalikan
 *                                   { el, update(props), destroy() }
 *
 * Aksesibilitas: role/aria-live untuk feedback, focus-trap + Esc untuk modal,
 * roving tabindex + arrow-keys untuk tabs, aria-describedby untuk tooltip,
 * kontras & focus-visible di CSS. Dimuat SEBELUM app.js; diekspos global `UI`
 * (sama seperti lib.js) agar kompatibel dengan closure app.js.
 */
(function (global) {
  'use strict';

  var UI = {};

  // -------------------------------------------------------------------------
  // Helpers internal
  // -------------------------------------------------------------------------
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function cls() {
    return Array.prototype.slice.call(arguments).filter(Boolean).join(' ');
  }

  function elFromHtml(html) {
    var t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  // -------------------------------------------------------------------------
  // 1. SPINNER — indikator loading ringan (aria-label, aria-hidden detail)
  // -------------------------------------------------------------------------
  UI.spinner = {
    html: function (opts) {
      var o = opts || {};
      var size = o.size || 'md'; // sm | md | lg
      var label = o.label || 'Memuat…';
      return '<span class="ui-spinner ui-spinner--' + esc(size) + '" role="status" aria-label="' + esc(label) + '"><span class="ui-spinner__ring" aria-hidden="true"></span></span>';
    },
    mount: function (el, opts) {
      el.innerHTML = UI.spinner.html(opts);
      return { el: el, update: function (o) { el.innerHTML = UI.spinner.html(o); }, destroy: function () { el.innerHTML = ''; } };
    }
  };

  // -------------------------------------------------------------------------
  // 2. SKELETON — placeholder loading (jangan teks berkedip; kurangi CLS)
  // -------------------------------------------------------------------------
  UI.skeleton = {
    html: function (opts) {
      var o = opts || {};
      var lines = o.lines || 3;
      var out = '<div class="ui-skeleton" role="status" aria-label="' + esc(o.label || 'Memuat konten…') + '" aria-busy="true">';
      for (var i = 0; i < lines; i++) {
        out += '<div class="ui-skeleton__line" style="width:' + esc((o.widths && o.widths[i]) || (92 - i * 8) + '%') + '"></div>';
      }
      return out + '</div>';
    },
    mount: function (el, opts) { el.innerHTML = UI.skeleton.html(opts); return { el: el, destroy: function () { el.innerHTML = ''; } }; }
  };

  // -------------------------------------------------------------------------
  // 3. EMPTY STATE — halaman/panel kosong dengan aksi opsional
  // -------------------------------------------------------------------------
  UI.emptyState = {
    html: function (o) {
      o = o || {};
      var action = o.action
        ? '<button type="button" class="ui-btn ui-btn--primary" data-ui-action>' + esc(o.action.label) + '</button>'
        : '';
      return '<div class="ui-empty" role="status">' +
        '<div class="ui-empty__icon" aria-hidden="true">' + esc(o.icon || '📭') + '</div>' +
        '<h3 class="ui-empty__title">' + esc(o.title || 'Belum ada data') + '</h3>' +
        (o.description ? '<p class="ui-empty__desc">' + esc(o.description) + '</p>' : '') +
        action +
        '</div>';
    },
    mount: function (el, o) {
      o = o || {};
      el.innerHTML = UI.emptyState.html(o);
      var btn = el.querySelector('[data-ui-action]');
      if (btn && typeof o.action.onClick === 'function') {
        btn.addEventListener('click', o.action.onClick);
      }
      return {
        el: el,
        update: function (p) { el.innerHTML = UI.emptyState.html(p); if (p.action && typeof p.action.onClick === 'function') { el.querySelector('[data-ui-action]').addEventListener('click', p.action.onClick); } },
        destroy: function () { el.innerHTML = ''; }
      };
    }
  };

  // -------------------------------------------------------------------------
  // 4. ERROR STATE — kegagalan dengan tombol coba lagi (accessibility: role=alert)
  // -------------------------------------------------------------------------
  UI.errorState = {
    html: function (o) {
      o = o || {};
      var retry = o.retry
        ? '<button type="button" class="ui-btn ui-btn--ghost" data-ui-retry>' + esc(o.retry.label || 'Coba Lagi') + '</button>'
        : '';
      return '<div class="ui-error" role="alert">' +
        '<div class="ui-error__icon" aria-hidden="true">' + esc(o.icon || '⚠️') + '</div>' +
        '<h3 class="ui-error__title">' + esc(o.title || 'Terjadi kesalahan') + '</h3>' +
        (o.message ? '<p class="ui-error__msg">' + esc(o.message) + '</p>' : '') +
        retry +
        '</div>';
    },
    mount: function (el, o) {
      o = o || {};
      el.innerHTML = UI.errorState.html(o);
      var btn = el.querySelector('[data-ui-retry]');
      if (btn && typeof o.retry.onClick === 'function') {
        btn.addEventListener('click', o.retry.onClick);
      }
      return { el: el, destroy: function () { el.innerHTML = ''; } };
    }
  };

  // -------------------------------------------------------------------------
  // 5. BADGE — label status tonal (success/warn/error/info/neutral)
  // -------------------------------------------------------------------------
  UI.badge = {
    html: function (o) {
      o = o || {};
      return '<span class="ui-badge ui-badge--' + esc(o.tone || 'neutral') + '">' + esc(o.text) + '</span>';
    },
    mount: function (el, o) { el.innerHTML = UI.badge.html(o); return { el: el, update: function (p) { el.innerHTML = UI.badge.html(p); } }; }
  };

  // -------------------------------------------------------------------------
  // 6. STATUS DOT — lampu status 3-warna + tooltip (red/green/yellow)
  // -------------------------------------------------------------------------
  UI.statusDot = {
    html: function (o) {
      o = o || {};
      var tone = o.tone || 'neutral'; // success | warn | danger | neutral
      var title = o.title ? ' title="' + esc(o.title) + '"' : '';
      return '<span class="ui-status-dot ui-status-dot--' + esc(tone) + '"' + title + ' role="img" aria-label="' + esc(o.label || 'Status') + '" aria-hidden="true"></span>';
    },
    mount: function (el, o) { el.innerHTML = UI.statusDot.html(o); return { el: el, update: function (p) { el.innerHTML = UI.statusDot.html(p); } }; }
  };

  // -------------------------------------------------------------------------
  // 7. BUTTON — variasi + state loading (spinner di dalam)
  // -------------------------------------------------------------------------
  UI.button = {
    html: function (o) {
      o = o || {};
      var loading = o.loading ? UI.spinner.html({ size: 'sm' }) : '';
      var disabled = o.disabled || o.loading ? ' disabled' : '';
      return '<button type="button" class="ui-btn ui-btn--' + esc(o.variant || 'primary') + '"' +
        disabled +
        (o.title ? ' title="' + esc(o.title) + '"' : '') +
        (o.ariaLabel ? ' aria-label="' + esc(o.ariaLabel) + '"' : '') +
        '>' + loading + '<span class="ui-btn__label">' + esc(o.label || '') + '</span></button>';
    },
    mount: function (el, o) {
      o = o || {};
      el.innerHTML = UI.button.html(o);
      var btn = el.querySelector('button');
      if (btn && typeof o.onClick === 'function') btn.addEventListener('click', o.onClick);
      return {
        el: el,
        setLoading: function (v) { btn.disabled = v; btn.querySelector('.ui-btn__label').style.opacity = v ? 0.4 : 1; },
        destroy: function () { el.innerHTML = ''; }
      };
    }
  };

  // -------------------------------------------------------------------------
  // 8. METRIC CARD — angka besar + sub + tone (dipakai dashboard/statistik)
  // -------------------------------------------------------------------------
  UI.metric = {
    html: function (o) {
      o = o || {};
      return '<div class="ui-metric">' +
        '<span class="ui-metric__label">' + esc(o.label || '') + '</span>' +
        '<span class="ui-metric__value ui-metric__value--' + esc(o.tone || 'neutral') + '">' + esc(o.value ?? '—') + '</span>' +
        (o.sub ? '<span class="ui-metric__sub">' + esc(o.sub) + '</span>' : '') +
        '</div>';
    },
    mount: function (el, o) { el.innerHTML = UI.metric.html(o); return { el: el, update: function (p) { el.innerHTML = UI.metric.html(p); } }; }
  };

  // -------------------------------------------------------------------------
  // 9. PANEL — kontainer konsisten dengan state (loading/empty/error) bawaan
  // -------------------------------------------------------------------------
  UI.panel = {
    html: function (o) {
      o = o || {};
      var body = '';
      if (o.loading) {
        body = UI.skeleton.html({ lines: o.skeletonLines || 3 });
      } else if (o.error) {
        body = UI.errorState.html({ title: o.errorTitle, message: o.error, retry: o.retry });
      } else if (o.empty) {
        body = UI.emptyState.html(o.empty);
      } else {
        body = typeof o.content === 'string' ? o.content : '';
      }
      return '<section class="ui-panel"' + (o.id ? ' id="' + esc(o.id) + '"' : '') + '>' +
        (o.title || o.actions
          ? '<header class="ui-panel__head">' +
            (o.title ? '<h3 class="ui-panel__title">' + esc(o.title) + '</h3>' : '') +
            (o.actions ? '<div class="ui-panel__actions">' + o.actions + '</div>' : '') +
            '</header>'
          : '') +
        '<div class="ui-panel__body" data-ui-body>' + body + '</div>' +
        '</section>';
    },
    mount: function (el, o) {
      o = o || {};
      el.innerHTML = UI.panel.html(o);
      var body = el.querySelector('[data-ui-body]');
      var retry = el.querySelector('[data-ui-retry]');
      if (retry && o.retry && typeof o.retry.onClick === 'function') retry.addEventListener('click', o.retry.onClick);
      return {
        el: el,
        body: body,
        update: function (p) { el.innerHTML = UI.panel.html(p); },
        destroy: function () { el.innerHTML = ''; }
      };
    }
  };

  // -------------------------------------------------------------------------
  // 10. TOAST — feedback transient (aria-live polite; auto-dismiss; stack)
  // -------------------------------------------------------------------------
  var toastContainer = null;
  UI.toast = {
    _ensureContainer: function () {
      if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'ui-toast-region';
        toastContainer.setAttribute('aria-live', 'polite');
        toastContainer.setAttribute('role', 'status');
        document.body.appendChild(toastContainer);
      }
      return toastContainer;
    },
    show: function (message, opts) {
      var o = opts || {};
      var type = o.type || 'info'; // success | warn | error | info
      var container = UI.toast._ensureContainer();
      var item = elFromHtml(
        '<div class="ui-toast ui-toast--' + esc(type) + '" role="status">' +
        '<span class="ui-toast__msg">' + esc(message) + '</span>' +
        '<button type="button" class="ui-toast__close" aria-label="Tutup">✕</button></div>'
      );
      container.appendChild(item);
      var dismiss = function () {
        item.classList.add('ui-toast--out');
        setTimeout(function () { if (item.parentNode) item.parentNode.removeChild(item); }, 250);
      };
      item.querySelector('.ui-toast__close').addEventListener('click', dismiss);
      var auto = o.duration == null ? 4000 : o.duration;
      if (auto > 0) setTimeout(dismiss, auto);
      return dismiss;
    }
  };

  // -------------------------------------------------------------------------
  // 11. MODAL — aksesibel: focus trap, Esc, aria-modal, scroll-lock body
  // -------------------------------------------------------------------------
  var modalCount = 0;
  UI.modal = {
    open: function (o) {
      o = o || {};
      var id = 'ui-modal-' + (++modalCount);
      var overlay = elFromHtml(
        '<div class="ui-modal-overlay" id="' + id + '" role="dialog" aria-modal="true"' +
        (o.title ? ' aria-labelledby="' + id + '-title"' : '') + '>' +
        '<div class="ui-modal" role="document">' +
        '<header class="ui-modal__head">' +
        '<h2 class="ui-modal__title" id="' + id + '-title">' + esc(o.title || '') + '</h2>' +
        '<button type="button" class="ui-modal__close" data-ui-close aria-label="Tutup dialog">✕</button>' +
        '</header>' +
        '<div class="ui-modal__body">' + (typeof o.content === 'string' ? o.content : '') + '</div>' +
        (o.footer ? '<footer class="ui-modal__foot">' + o.footer + '</footer>' : '') +
        '</div></div>'
      );
      document.body.appendChild(overlay);
      document.body.style.overflow = 'hidden'; // scroll-lock

      // Fokus trap
      var focusables = function () {
        return Array.prototype.slice.call(overlay.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'))
          .filter(function (n) { return !n.disabled && n.offsetParent !== null; });
      };
      var prevFocus = document.activeElement;
      var first = null, last = null;
      var focusFirst = function () {
        var f = focusables();
        first = f[0]; last = f[f.length - 1];
        (first || overlay).focus();
      };
      setTimeout(focusFirst, 0);

      var onKey = function (e) {
        if (e.key === 'Escape') { close(); return; }
        if (e.key === 'Tab') {
          var f = focusables();
          if (f.length === 0) return;
          first = f[0]; last = f[f.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      };
      var onDocKey = function (e) {
        if (e.key === 'Escape') close();
      };
      document.addEventListener('keydown', onDocKey);

      function close() {
        document.removeEventListener('keydown', onDocKey);
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        document.body.style.overflow = '';
        if (prevFocus && prevFocus.focus) prevFocus.focus();
        if (typeof o.onClose === 'function') o.onClose();
      }
      overlay.querySelector('[data-ui-close]').addEventListener('click', close);
      overlay.addEventListener('mousedown', function (e) { if (e.target === overlay) close(); });
      return { overlay: overlay, close: close };
    }
  };

  // -------------------------------------------------------------------------
  // 12. TABS — roving tabindex, arrow keys, aria-selected
  // -------------------------------------------------------------------------
  UI.tabs = {
    mount: function (el, o) {
      o = o || {};
      var tabs = o.tabs || [];
      var activeIdx = o.activeIndex || 0;
      var tablist = elFromHtml('<div class="ui-tabs" role="tablist" aria-label="' + esc(o.label || 'Tab') + '"></div>');
      var panels = [];
      el.appendChild(tablist);

      function render() {
        tablist.innerHTML = tabs.map(function (t, i) {
          return '<button type="button" role="tab" id="ui-tab-' + i + '" aria-selected="' + (i === activeIdx) + '"' +
            (i === activeIdx ? ' class="ui-tabs__tab is-active"' : ' class="ui-tabs__tab"') +
            ' tabindex="' + (i === activeIdx ? '0' : '-1') + '">' + esc(t.label) + '</button>';
        }).join('');
        // panel area (dipanggil tiap ganti)
        if (panels[activeIdx]) { panels[activeIdx].parentNode.removeChild(panels[activeIdx]); }
        var panel = document.createElement('div');
        panel.className = 'ui-tabs__panel';
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', 'ui-tab-' + activeIdx);
        if (typeof tabs[activeIdx].render === 'function') tabs[activeIdx].render(panel);
        el.appendChild(panel);
        panels[activeIdx] = panel;
        if (typeof o.onChange === 'function') o.onChange(activeIdx);
      }

      tablist.addEventListener('keydown', function (e) {
        var btns = tablist.querySelectorAll('[role="tab"]');
        var i = activeIdx;
        if (e.key === 'ArrowRight') i = (i + 1) % btns.length;
        else if (e.key === 'ArrowLeft') i = (i - 1 + btns.length) % btns.length;
        else if (e.key === 'Home') i = 0;
        else if (e.key === 'End') i = btns.length - 1;
        else return;
        e.preventDefault();
        activeIdx = i;
        render();
        btns[activeIdx].focus();
      });
      tablist.addEventListener('click', function (e) {
        var btn = e.target.closest('[role="tab"]');
        if (!btn) return;
        activeIdx = parseInt(btn.id.split('-')[2], 10);
        render();
      });

      render();
      return { el: el, setActive: function (i) { activeIdx = i; render(); }, destroy: function () { el.innerHTML = ''; } };
    }
  };

  // -------------------------------------------------------------------------
  // 13. TOOLTIP — hover & focus, aria-describedby
  // -------------------------------------------------------------------------
  UI.tooltip = {
    mount: function (el, text) {
      var id = 'ui-tip-' + Math.random().toString(36).slice(2, 8);
      el.setAttribute('tabindex', '0');
      el.setAttribute('aria-describedby', id);
      var tip = document.createElement('span');
      tip.id = id;
      tip.className = 'ui-tooltip';
      tip.setAttribute('role', 'tooltip');
      tip.textContent = text;
      el.appendChild(tip);
      return { destroy: function () { if (tip.parentNode) tip.parentNode.removeChild(tip); } };
    }
  };

  global.UI = UI;
})(typeof window !== 'undefined' ? window : this);
