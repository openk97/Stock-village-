/**
 * sv-status-dot — Komponen Lit (STRANGLER PATTERN POC).
 *
 * Menggantikan <span id="sidebar-status-dot"> (lampu status 3 warna) yang
 * sebelumnya di-update via JS + inline style. Kini custom element reaktif:
 *   <sv-status-dot tone="success|warn|danger|neutral"></sv-status-dot>
 * - Shadow DOM (terisolasi, tidak bocor ke CSS global).
 * - Reactive property `tone` -> render ulang otomatis saat di-set.
 * - A11y: aria-hidden (dekoratif; teks status tetap di sibling).
 *
 * Ini POC untuk membuktikan strangler pattern: satu komponen kecil di-migrasi
 * ke Lit sementara sisanya tetap vanilla. Verifikasi: status dot tampil &
 * berubah warna sesuai koneksi (success/warn/danger).
 */
import { LitElement, html, css } from 'lit';

export class SVStatusDot extends LitElement {
  static properties = {
    tone: { type: String },
  };

  static styles = css`
    :host {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
      transition: background-color 0.3s;
    }
    .success { background-color: var(--bull-color); box-shadow: 0 0 6px rgba(0, 230, 118, 0.6); }
    .warn    { background-color: var(--spike-color); box-shadow: 0 0 6px rgba(250, 204, 21, 0.6); }
    .danger  { background-color: var(--bear-color);  box-shadow: 0 0 6px rgba(255, 51, 102, 0.6); }
    .neutral { background-color: var(--neutral-color); }
  `;

  constructor() {
    super();
    this.tone = 'neutral';
  }

  render() {
    return html`<span class="${this.tone}" aria-hidden="true"></span>`;
  }
}

customElements.define('sv-status-dot', SVStatusDot);
