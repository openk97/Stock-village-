/**
 * sv-badge — Komponen Lit (STRANGLER PATTERN, langkah 2).
 *
 * Menggantikan badge teks berwarna yang selama ini di-update via className/
 * innerText (mis. #sectors-panel-badge "11 SEKTOR").
 *   <sv-badge text="11 SEKTOR" tone="success|neutral|warn|error"></sv-badge>
 * - Shadow DOM (terisolasi).
 * - Reactive properties text/tone/mono.
 * - tone success = hijau (text-bull), neutral = slate + mono, dst — mereplikasi
 *   tampilan lama.
 */
import { LitElement, html, css } from 'lit';

export class SVBadge extends LitElement {
  static properties = {
    text: { type: String },
    tone: { type: String },
    mono: { type: Boolean, reflect: true },
  };

  static styles = css`
    :host {
      display: inline-block;
      font-weight: 800;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .success { color: var(--bull-color); }
    .neutral { color: var(--neutral-color); }
    .warn    { color: var(--spike-color); }
    .error   { color: var(--bear-color); }
    .mono    { font-family: 'JetBrains Mono', monospace; }
    .s9      { font-size: 9px; }
    .s8      { font-size: 8px; }
  `;

  constructor() {
    super();
    this.text = '';
    this.tone = 'neutral';
    this.mono = false;
  }

  render() {
    return html`<span class="${this.tone} ${this.mono ? 'mono' : ''} ${this.mono ? 's9' : 's8'}">${this.text}</span>`;
  }
}

customElements.define('sv-badge', SVBadge);
