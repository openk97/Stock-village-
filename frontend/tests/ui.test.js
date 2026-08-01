/**
 * Unit test UI component library (js/ui.js) — bagian MURNI (html()).
 * Di jalankan dengan Node:  node tests/ui.test.js
 * Bagian mount()/DOM diuji via Playwright (lihat verify_ui.py di sesi dev).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const code = fs.readFileSync(path.join(__dirname, '../js/ui.js'), 'utf8');
const sandbox = {};
sandbox.window = sandbox;         // ui.js meng-expose ke window
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const UI = sandbox.UI;

// --- spinner ---
const sp = UI.spinner.html({ size: 'lg', label: 'Tunggu' });
assert.ok(sp.includes('role="status"'), 'spinner role');
assert.ok(sp.includes('aria-label="Tunggu"'), 'spinner a11y label');
assert.ok(sp.includes('ui-spinner--lg'), 'spinner size');

// --- skeleton ---
const sk = UI.skeleton.html({ lines: 4 });
assert.strictEqual((sk.match(/ui-skeleton__line/g) || []).length, 4, 'skeleton lines');
assert.ok(sk.includes('aria-busy="true"'), 'skeleton busy');

// --- empty state ---
const es = UI.emptyState.html({ title: 'Kosong', description: 'Belum ada', action: { label: 'Tambah' } });
assert.ok(es.includes('Belum ada'), 'empty desc');
assert.ok(es.includes('data-ui-action'), 'empty action btn');
assert.ok(es.includes('role="status"'), 'empty role');

// --- error state ---
const er = UI.errorState.html({ title: 'Gagal', message: 'Network', retry: { label: 'Coba' } });
assert.ok(er.includes('role="alert"'), 'error alert role');
assert.ok(er.includes('data-ui-retry'), 'error retry btn');

// --- badge ---
assert.ok(UI.badge.html({ text: 'OK', tone: 'success' }).includes('ui-badge--success'));

// --- status dot ---
const sd = UI.statusDot.html({ tone: 'warn', label: 'Parsial', title: 'Sebagian data' });
assert.ok(sd.includes('ui-status-dot--warn'), 'status tone');
assert.ok(sd.includes('title="Sebagian data"'), 'status tooltip');
assert.ok(sd.includes('aria-label="Parsial"'), 'status a11y');

// --- button ---
const bt = UI.button.html({ label: 'Simpan', variant: 'primary', loading: true, ariaLabel: 'Simpan data' });
assert.ok(bt.includes('disabled'), 'button disabled saat loading');
assert.ok(bt.includes('ui-spinner'), 'button spinner saat loading');
assert.ok(bt.includes('aria-label="Simpan data"'), 'button aria-label');

// --- metric ---
const mt = UI.metric.html({ label: 'Volume', value: '1.2M', tone: 'success', sub: '+5%' });
assert.ok(mt.includes('1.2M') && mt.includes('+5%'), 'metric value+sub');

// --- panel (loading/empty/error built-in) ---
const pl = UI.panel.html({ title: 'Berita', loading: true, skeletonLines: 2 });
assert.strictEqual((pl.match(/ui-skeleton__line/g) || []).length, 2, 'panel loading -> skeleton');
const pe = UI.panel.html({ title: 'X', empty: { title: 'Kosong' } });
assert.ok(pe.includes('Kosong'), 'panel empty state');

// --- XSS safety: html() harus meng-escape ---
const xss = UI.badge.html({ text: '<script>alert(1)</script>' });
assert.ok(!xss.includes('<script>'), 'no raw script');
assert.ok(xss.includes('&lt;script&gt;'), 'escaped');

console.log('ui.js unit tests PASS — semua assert OK (' + Object.keys(UI).length + ' komponen)');
