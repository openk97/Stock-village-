/**
 * Unit test fungsi murni frontend (js/lib.js) -- dijalankan dengan Node:
 *   node tests/lib.test.js
 * Tanpa browser/Playwright: hanya fungsi murni (tanpa DOM).
 * Catatan: binding `const` di skrip klasik bersifat LEXICAL (bukan properti
 * global), jadi diakses lewat vm.runInContext -- sama seperti browser (app.js
 * melihatnya dari global lexical scope).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const code = fs.readFileSync(path.join(__dirname, '../js/lib.js'), 'utf8');
const ctx = vm.createContext({});
vm.runInContext(code, ctx);
const E = (expr) => vm.runInContext(expr, ctx);

// hashSymbolToInt: deterministik
assert.strictEqual(E('hashSymbolToInt("BBCA")'), E('hashSymbolToInt("BBCA")'));
assert.notStrictEqual(E('hashSymbolToInt("BBCA")'), E('hashSymbolToInt("BBRI")'));

// formatCompactValue
assert.strictEqual(E('formatCompactValue(1500000000)'), '1.50b');
assert.strictEqual(E('formatCompactValue(-2500000)'), '-2.50m');
assert.strictEqual(E('formatCompactValue(999)'), '999.00');

// formatIntID (format Indonesia)
assert.strictEqual(E('formatIntID(1234567)'), '1.234.567');
assert.strictEqual(E('formatIntID(null)'), '-');

// headerSearchEscape
assert.strictEqual(E('headerSearchEscape("<a&\\"b>")'), '&lt;a&amp;&quot;b&gt;');

// BROKER_DIRECTORY: 10 broker
assert.strictEqual(E('BROKER_DIRECTORY.length'), 10);
assert.strictEqual(E('BROKER_DIRECTORY[0].code'), 'DX');
assert.strictEqual(E('BROKER_DIRECTORY[5].code'), 'YP');

// MARQUEE_META
assert.strictEqual(E('MARQUEE_META.usdidr.fmt(17990)'), 'Rp 17.990');
assert.strictEqual(E('MARQUEE_META.us10y.fmt(47.4)'), '4.74%');

// strategi stock pick
assert.strictEqual(E('STOCKPICK_DAY_STRATEGIES.length'), 4);
assert.strictEqual(E('STOCKPICK_SWING_STRATEGIES.length'), 7);

console.log('lib.js unit tests PASS — semua assert OK');
