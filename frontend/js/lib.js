// lib.js -- FUNGSI MURNI (tanpa DOM) yang dipakai seluruh aplikasi.
// FASE 6 (modularisasi frontend, aman): dipisah dari app.js supaya bisa
// diuji & dirawat terpisah. Dimuat SEBELUM app.js; semua binding di sini
// berada di global scope (terlihat dari closure app.js).
'use strict';

const STOCKPICK_DAY_STRATEGIES = ["Scalping", "Price Action", "Teknikal", "VPA"];

const STOCKPICK_SWING_STRATEGIES = ["Wyckoff", "Bandarmology", "Elliott Wave", "VPA", "Teknikal", "Sector Rotation", "Fundamental"];

function hashSymbolToInt(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
    }
    return hash;
}

function formatCompactValue(rawValue) {
    const absVal = Math.abs(rawValue);
    const sign = rawValue < 0 ? "-" : "";
    if (absVal >= 1e12) return `${sign}${(absVal / 1e12).toFixed(2)}t`;
    if (absVal >= 1e9) return `${sign}${(absVal / 1e9).toFixed(2)}b`;
    if (absVal >= 1e6) return `${sign}${(absVal / 1e6).toFixed(2)}m`;
    if (absVal >= 1e3) return `${sign}${(absVal / 1e3).toFixed(2)}k`;
    return `${sign}${absVal.toFixed(2)}`;
}

function formatIntID(n) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    return Math.round(n).toLocaleString("id-ID");
}

const BROKER_DIRECTORY = [
    { code: "DX", name: "Bahana" },
    { code: "CC", name: "Mandiri" },
    { code: "CS", name: "Credit Suisse" },
    { code: "AK", name: "UBS" },
    { code: "KZ", name: "CLSA" },
    { code: "YP", name: "Mirae Asset" },
    { code: "PD", name: "Indo Premier" },
    { code: "OD", name: "Danareksa" },
    { code: "MG", name: "Semesta" },
    { code: "ZP", name: "Maybank" }
];

const MARQUEE_META = {
    usdidr: { label: "💵 USD/IDR", fmt: (v) => "Rp " + Math.round(v).toLocaleString("id-ID") },
    n225:   { label: "🇯🇵 NIKKEI 225", fmt: (v) => v.toLocaleString("id-ID") },
    hsi:    { label: "🇭🇰 HANG SENG", fmt: (v) => v.toLocaleString("id-ID") },
    sti:    { label: "🇸🇬 STI INDEX", fmt: (v) => v.toLocaleString("id-ID") },
    dji:    { label: "🇺🇸 DOW JONES", fmt: (v) => v.toLocaleString("id-ID") },
    spx:    { label: "🇺🇸 S&P 500", fmt: (v) => v.toLocaleString("id-ID") },
    ixic:   { label: "🇺🇸 NASDAQ", fmt: (v) => v.toLocaleString("id-ID") },
    gold:   { label: "🪙 EMAS (USD/oz)", fmt: (v) => "$" + v.toLocaleString("en-US") + "/oz" },
    coal:   { label: "🪨 BATU BARA", fmt: (v) => "$" + v.toLocaleString("en-US") + "/ton" },
    brent:  { label: "🛢️ BRENT CRUDE", fmt: (v) => "$" + v.toLocaleString("en-US") + "/bbl" },
    cpo:    { label: "🌴 CPO SAWIT", fmt: (v) => "MYR " + v.toLocaleString("en-US") + "/ton" },
    copper: { label: "🔗 COPPER (LME)", fmt: (v) => "$" + v.toLocaleString("en-US") + "/ton" },
    us10y:  { label: "📈 US 10Y BOND", fmt: (v) => (v >= 30 ? v / 10 : v).toFixed(2) + "%" }
};

function headerSearchEscape(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
