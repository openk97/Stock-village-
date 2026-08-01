/**
 * main.js — Entry Lit components (STRANGLER PATTERN).
 *
 * Module ini di-bundle Vite (script type="module" di index.html). Custom
 * element terdaftar di global customElements -> bisa dipakai dari HTML klasik
 * tanpa konflik dengan vanilla JS yang ada.
 *
 * Aturan strangler: komponen baru/termigrasi ditambahkan di sini; app.js tetap
 * vanilla selama transisi. Saat satu area sudah penuh Lit, baru dipotong dari
 * app.js.
 */
import './sv-status-dot.js';
import './sv-badge.js';
import './sv-breadth-bar.js';

// Daftarkan komponen yang tersedia untuk debug/audit
window.__litComponents = ['sv-status-dot', 'sv-badge', 'sv-breadth-bar'];
