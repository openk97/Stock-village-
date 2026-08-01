# UI SYSTEM — Stock Village

**Peran:** Senior Frontend Engineer · **Tujuan:** komponen UI reusable + aksesibel + siap produksi (loading/empty/error state, responsive, DX bersih). **Tanpa framework** — vanilla JS murni, tanpa dependency.

---

## 1. Component Architecture

```
frontend/
├── index.html          # markup + <link> css + <script> (lib -> ui -> app)
├── css/
│   ├── styles.css      # tema & tata letak global
│   └── components.css  # gaya SEMUA komponen UI (design token dari styles.css)
└── js/
    ├── lib.js          # fungsi murni (tanpa DOM) — unit-testable
    ├── ui.js           # [BARU] library komponen UI (window.UI)
    └── app.js          # logika DOM/UI aplikasi (closure DOMContentLoaded)
```

### Pola API dua bentuk (kunci reusability & testability)
```js
UI.<name>.html(props)  -> string HTML murni   (unit-testable di Node, template-able)
UI.<name>.mount(el, props) -> { el, update(props), destroy() }   (attach ke DOM)
```
- **`html()`** — fungsi murni: tidak menyentuh DOM, bisa diuji tanpa browser, bisa dipakai untuk template/SSR.
- **`mount()`** — me-render ke elemen + memasang event; mengembalikan handle `{update, destroy}` agar pemanggil bisa mengubah/membersihkan tanpa query ulang.
- Semua props di-escape → **aman XSS** (ada test khusus).

### Daftar komponen (13)
| Komponen | Fungsi | State bawaan |
|---|---|---|
| `UI.spinner` | indikator loading (sm/md/lg) | role=status, aria-label |
| `UI.skeleton` | placeholder loading (anti CLS) | aria-busy |
| `UI.emptyState` | kosong + aksi opsional | role=status |
| `UI.errorState` | gagal + tombol coba lagi | role=alert |
| `UI.badge` | label tonal (success/warn/error/info/neutral) | — |
| `UI.statusDot` | lampu 3 warna (success/warn/danger) + tooltip | aria-label |
| `UI.button` | variasi + state loading | disabled saat loading |
| `UI.metric` | kartu angka (label/value/sub/tone) | — |
| `UI.panel` | kontainer dengan loading/empty/error BAKU | skeleton/empty/error |
| `UI.toast` | notifikasi transient (stack, auto-dismiss) | aria-live=polite |
| `UI.modal` | dialog aksesibel (focus trap, Esc, scroll-lock) | aria-modal |
| `UI.tabs` | tab keyboard (roving tabindex, arrow keys) | aria-selected |
| `UI.tooltip` | hover & focus (aria-describedby) | role=tooltip |

---

## 2. Props / API Design

### Spinner
```js
UI.spinner.html({ size: 'lg', label: 'Memuat data…' })
```

### Skeleton
```js
UI.skeleton.html({ lines: 3, widths: ['100%', '90%', '70%'], label: 'Memuat berita…' })
```

### Empty & Error state
```js
UI.emptyState.html({ icon: '📭', title: 'Belum ada data', description: 'Coba tambah watchlist', action: { label: 'Tambah' } })
UI.errorState.html({ title: 'Gagal memuat', message: 'Jaringan tidak terjangkau', retry: { label: 'Coba Lagi', onClick } })
```

### Button
```js
UI.button.mount(el, { label: 'Simpan', variant: 'primary', onClick, loading: false, ariaLabel })
// .setLoading(true) untuk spinner di dalam tombol
```

### Panel (state bawaan — paling sering dipakai)
```js
UI.panel.mount(el, {
  title: 'Berita Terkini',
  actions: UI.button.html({ label: '⟳ Refresh' }),
  loading: true,          // tampilkan skeleton
  // loading:false, error:'...', empty:{...} → state otomatis
  content: '<div>…</div>' // konten normal
})
```

### Toast & Modal & Tabs (imperatif)
```js
UI.toast.show('Tersimpan', { type: 'success' })           // success|warn|error|info, duration
UI.modal.open({ title: 'Konfirmasi', content: '…', footer: '…', onClose })
UI.tabs.mount(el, { label: 'Strategi', tabs: [{ label: 'VPA', render: panel => … }], activeIndex, onChange })
```

### Tooltip
```js
UI.tooltip.mount(el, 'Sumber: Yahoo Finance (Live/Delayed)')
```

---

## 3. Production-Ready Implementation (intisari)

### Aksesibilitas — dipasang di setiap komponen
- **Toast**: `aria-live="polite" role="status"` → screen reader membacakan tanpa memotong aktivitas.
- **Modal**: `role="dialog" aria-modal="true"`, **focus trap** (Tab/Shift+Tab terkurung), **Esc menutup**, `aria-labelledby` ke judul, **scroll-lock body**, fokus kembali ke elemen asal.
- **Tabs**: `role="tablist"/"tab"/"tabpanel"`, **roving tabindex**, navigasi **Arrow/Home/End**, `aria-selected` sinkron.
- **Tooltip**: `aria-describedby` + `role="tooltip"`, muncul saat hover **dan** fokus keyboard.
- **Button/Badge/StatusDot**: `aria-label` eksplisit, `disabled` saat loading.
- **Focus-visible** jelas (outline) di semua interaktif — lihat `components.css`.

### State handling (loading / empty / error) — satu sumber
`UI.panel` mengkapsulkan keempat kondisi; komponen lain mandiri:
```
loading  -> skeleton (bukan teks berkedip, kurangi CLS)
empty    -> emptyState + aksi
error    -> errorState + retry (role=alert)
normal   -> konten
```
Pemakai panel tidak perlu menulis ulang pola if/else — cukup set `loading/empty/error/content`.

### Edge cases yang ditangani
- XSS → semua props di-`esc()` (test khusus `&lt;script&gt;`).
- Toast bertumpuk → container stack + auto-dismiss + tombol tutup; animasi keluar rapi.
- Modal di layar sempit → `max-width:100%`, scroll konten di dalam.
- Tabs overflow di mobile → `overflow-x:auto` pada tablist.
- Fokus hilang setelah modal tutup → dikembalikan ke `document.activeElement` sebelumnya.
- `update()` pada komponen → re-render tanpa menumpuk listener (rebind tiap render).

---

## 4. Usage Examples (integrasi nyata di app)

### 4.1 Panel berita dengan state loading → error → data
```js
const beritaPanel = UI.panel.mount(document.getElementById('news-panel'), {
  title: 'Berita Terkini', loading: true, skeletonLines: 4
});
// saat data tiba:
beritaPanel.update({ title: 'Berita Terkini', content: renderNewsHtml(items) });
// saat gagal:
beritaPanel.update({ title: 'Berita Terkini', error: 'Jaringan tidak terjangkau', retry: { label: 'Coba Lagi', onClick: fetchNews } });
```

### 4.2 Toast sukses setelah simpan watchlist
```js
UI.toast.show('BBCA ditambahkan ke watchlist', { type: 'success' });
```

### 4.3 Modal detail dengan fokus trap otomatis
```js
UI.modal.open({ title: `Detail ${symbol}`, content: detailHtml, onClose: () => refreshList() });
```

### 4.4 Status lampu yang konsisten (statusDot)
```js
el.innerHTML = UI.statusDot.html({ tone: isAllReal ? 'success' : fallback ? 'warn' : 'danger', label: statusText, title: tooltip });
```

---

## 5. Best Practices (yang diterapkan & dipatuhi)

1. **Tanpa dependency** — komponen murni vanilla; tidak mengunci ke framework → mudah diport ke React/Vue nanti (API `html`/`mount` analog dengan render/component).
2. **Aksesibilitas sejak awal, bukan tambahan** — ARIA, fokus, keyboard diuji (Playwright).
3. **HTML murni dapat diuji** — `html()` diuji di Node tanpa DOM (`tests/ui.test.js`).
4. **State visual satu sumber** — loading/empty/error lewat `UI.panel` → konsisten di seluruh app.
5. **Escape semua input** — tidak ada XSS lewat props.
6. **DX bersih** — API konsisten (`html`/`mount`), nama jelas, dokumen ini sebagai referensi.
7. **Mobile-first** — breakpoint di CSS komponen; tiap komponen diuji 390px tanpa overflow.

---

## 6. Tests & Verification

- `node tests/ui.test.js` → **13 komponen, semua assert PASS** (termasuk XSS escape).
- Playwright (browser nyata): toast `aria-live` tampil, modal `aria-modal` + **Esc menutup**, tabs **ArrowRight** berpindah & `aria-selected` sinkron, app tetap normal (marquee/berita/status real), mobile 390px tanpa overflow, **0 JS error**.
