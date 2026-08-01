#!/usr/bin/env python3
"""
perf_budget.py — Performance budget & mobile audit (CI-able).

Mengukur (lewat Performance API browser):
  - LCP (Largest Contentful Paint) & FCP — budget < 2500ms / < 1500ms
  - Total transfer JS & CSS (gzip) — budget internal (tanpa CDN eksternal)
  - ukuran index.html
  - JS errors = 0
  - overflow horizontal di semua view pada viewport 390px (mobile)

Usage:
  python3 tests/perf_budget.py --base http://localhost:8081/index.html

Exit code 0 = pass, 1 = fail (bisa dipakai CI).
"""
import argparse
import json
import sys
import time

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# BUDGET (tech-lead decision; sesuaikan saat app tumbuh)
# ---------------------------------------------------------------------------
BUDGET = {
    # FCP = metrik budget utama (reliabel di headless & perangkat nyata).
    # LCP tidak ter-trigger konsisten di headless -> diukur manual via
    # Lighthouse di perangkat nyata (lihat PERFORMANCE_BUDGET.md).
    "fcp_ms": 1500,
    "js_gzip_kb": 150,       # internal JS saja (lib/ui/app + lit); tv.js = CDN eksternal
    "css_gzip_kb": 15,
    "html_kb": 200,
    "js_errors": 0,
}

VIEWS = [
    ("home", "changeTerminalView('home')"),
    ("watchlist", "changeTerminalView('watchlist')"),
    ("stockpick", "changeTerminalView('stockpick')"),
    ("datalog", "changeTerminalView('datalog')"),
    ("strategi", "changeTerminalView('strategi'); openStrategiTab('teknikal')"),
    ("kalkulator", "changeTerminalView('calculator'); openCalculatorTab('valuation')"),
    ("korelasi", "changeTerminalView('korelasi'); openKorelasiTab('guide')"),
    ("edukasi", "changeTerminalView('edukasi'); openEdukasiTab('basics')"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8081/index.html")
    ap.add_argument("--mobile", action="store_true", default=True)
    args = ap.parse_args()

    results = {}
    fails = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chromium", headless=True)
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True, device_scale_factor=3)
        page = ctx.new_page()
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))

        # Pasang observer LCP via init script (berjalan SEBELUM setiap navigasi —
        # evaluate di halaman awal tidak bertahan saat pindah URL).
        page.add_init_script("""() => {
            window.__lcp = null;
            try {
                new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    if (entries.length) window.__lcp = Math.round(entries[entries.length-1].startTime);
                }).observe({ type: 'largest-contentful-paint', buffered: true });
            } catch (e) { window.__lcp = -1; }
        }""")

        # --- Load + metrics ---
        t0 = time.time()
        page.goto(args.base, wait_until="load", timeout=60000)
        nav = page.evaluate("""() => {
            const nav = performance.getEntriesByType('navigation')[0];
            return { load: nav ? Math.round(nav.loadEventEnd) : 0, domContentLoaded: nav ? Math.round(nav.domContentLoadedEventEnd) : 0 };
        }""")
        page.wait_for_timeout(3000)
        metrics = page.evaluate("""async () => {
            const entries = performance.getEntriesByType('paint');
            const fcp = entries.find(e => e.name === 'first-contentful-paint');
            const lcp = window.__lcp;
            return { fcp: fcp ? Math.round(fcp.startTime) : null, lcp: lcp };
        }""")
        results["load_ms"] = round((time.time() - t0) * 1000)

        # --- Transfer size per jenis (responses) ---
        sizes = {"js": 0, "css": 0, "html": 0}
        for r in page.request.get_all_pages() if False else []:
            pass
        # ambil via response listener saat load ulang
        def collect():
            page.reload(wait_until="load", timeout=60000)
            page.wait_for_timeout(2500)
        # pakai API request.get (playwright request context sudah otomatis collect)
        resp_info = page.evaluate("""() => {
            const res = performance.getEntriesByType('resource');
            let js=0, css=0;
            res.forEach(r => {
                const n = r.name;
                if (/\\/js\\//.test(n) || n.includes('.js')) js += r.transferSize;
                else if (/\\/assets\\//.test(n) && n.endsWith('.css')) css += r.transferSize;
            });
            return { js, css };
        }""")
        sizes["js"] = round(resp_info["js"] / 1024, 1)
        sizes["css"] = round(resp_info["css"] / 1024, 1)
        # html size
        html_resp = page.request.get(args.base)
        sizes["html"] = round(len(html_resp.body()) / 1024, 1)

        results["js_gzip_kb"] = sizes["js"]
        results["css_gzip_kb"] = sizes["css"]
        results["html_kb"] = sizes["html"]

        # --- Mobile overflow audit (semua view) ---
        overflows = []
        for label, script in VIEWS:
            page.evaluate(script)
            page.wait_for_timeout(900)
            d = page.evaluate("""() => ({ doc: document.documentElement.scrollWidth, vw: document.documentElement.clientWidth })""")
            if d["doc"] > d["vw"] + 1:
                overflows.append(label)
        results["mobile_overflow_views"] = overflows

        results["js_errors"] = len(js_errors)
        results["lcp_ms"] = metrics.get("lcp")
        results["fcp_ms"] = metrics.get("fcp")
        browser.close()

    # --- Evaluasi budget ---
    print(json.dumps(results, indent=2))
    checks = [
        ("FCP", results.get("fcp_ms"), BUDGET["fcp_ms"]),
        ("JS gzip KB", results.get("js_gzip_kb"), BUDGET["js_gzip_kb"]),
        ("CSS gzip KB", results.get("css_gzip_kb"), BUDGET["css_gzip_kb"]),
        ("HTML KB", results.get("html_kb"), BUDGET["html_kb"]),
    ]
    for name, val, limit in checks:
        ok = val is not None and val <= limit
        print(f"{'✓' if ok else '✗'} {name}: {val} (budget ≤ {limit})")
        if not ok:
            fails.append(name)
    if results.get("js_errors", 0) > 0:
        fails.append("js_errors"); print(f"✗ JS errors: {results['js_errors']}")
    else:
        print("✓ JS errors: 0")
    if results.get("mobile_overflow_views"):
        fails.append("overflow"); print(f"✗ Overflow: {results['mobile_overflow_views']}")
    else:
        print("✓ Mobile overflow: tidak ada")

    print("\nRESULT:", "PASS" if not fails else f"FAIL {fails}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
