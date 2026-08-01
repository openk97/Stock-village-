/**
 * sv-breadth-bar — Komponen Lit (STRANGLER PATTERN, langkah 3).
 *
 * Menggantikan blok market breadth (naik/tetap/turun) yang selama ini
 * di-update via 6 id terpisah (breadth-up/flat/down, bar & label).
 *   <sv-breadth-bar up="47" flat="13" down="22"></sv-breadth-bar>
 * - Reactive properties up/flat/down (angka) -> render bar proporsional +
 *   label persen + jumlah emiten.
 * - Shadow DOM (terisolasi). Tone tetap pakai design token.
 */
import { LitElement, html, css } from 'lit';

export class SVBreadthBar extends LitElement {
  static properties = {
    up: { type: Number },
    flat: { type: Number },
    down: { type: Number },
  };

  static styles = css`
    .row { display: flex; flex-direction: column; gap: 8px; font-size: 11px; }
    .metric { display: flex; justify-content: space-between; align-items: center; }
    .metric b { font-family: 'JetBrains Mono', monospace; font-weight: 800; }
    .up { color: var(--bull-color); }
    .flat { color: var(--neutral-color); }
    .down { color: var(--bear-color); }
    .bar { display: flex; height: 6px; background: var(--bg-dark); border-radius: 3px; overflow: hidden; }
    .seg-up { background: var(--bull-color); }
    .seg-flat { background: var(--neutral-color); }
    .seg-down { background: var(--bear-color); }
    .lbl { display: flex; justify-content: space-between; font-size: 8px; color: var(--neutral-color); }
  `;

  constructor() {
    super();
    this.up = 0;
    this.flat = 0;
    this.down = 0;
  }

  render() {
    const total = (this.up + this.flat + this.down) || 1;
    const pct = (n) => Math.round((n / total) * 100);
    const w = (n) => ((n / total) * 100).toFixed(1) + '%';
    return html`
      <div class="row">
        <div class="metric"><span>Saham Naik (Advances):</span><b class="up">${this.up} Emiten</b></div>
        <div class="metric"><span>Saham Tetap (Unchanged):</span><b class="flat">${this.flat} Emiten</b></div>
        <div class="metric"><span>Saham Turun (Declines):</span><b class="down">${this.down} Emiten</b></div>
        <div class="bar" role="img" aria-label="Breadth: ${pct(this.up)}% naik, ${pct(this.flat)}% tetap, ${pct(this.down)}% turun">
          <div class="seg-up" style="width:${w(this.up)}" title="Naik: ${pct(this.up)}%"></div>
          <div class="seg-flat" style="width:${w(this.flat)}" title="Tetap: ${pct(this.flat)}%"></div>
          <div class="seg-down" style="width:${w(this.down)}" title="Turun: ${pct(this.down)}%"></div>
        </div>
        <div class="lbl">
          <span>${pct(this.up)}% Naik</span>
          <span>${pct(this.flat)}% Tetap</span>
          <span>${pct(this.down)}% Turun</span>
        </div>
      </div>
    `;
  }
}

customElements.define('sv-breadth-bar', SVBreadthBar);
