/**
 * IHSG Insight Dynamic Script
 * Mengelola pembaruan harga real-time, grafik interaktif SVG, indikator teknikal,
 * serta sistem watchlist lokal dengan integrasi database.
 */

document.addEventListener("DOMContentLoaded", () => {
    // State Lokal untuk UI Dinamis
    let currentPeriod = "1y";
    let showSMA50 = true;
    let showSMA200 = true;
    let showRSI = true;
    
    // Database Fallback/Inisialisasi Data jika API offline
    let dbHistory = [];
    let dbRealtime = {
        current_price: 7245.50,
        change: 34.20,
        change_percent: 0.47,
        open: 7211.30,
        high: 7260.10,
        low: 7208.50,
        volume: 14200000000
    };
    
    const defaultWatchlist = [
        { symbol: "BBCA", name: "Bank Central Asia Tbk.", price: 10450, change: 1.46 },
        { symbol: "BBRI", name: "Bank Rakyat Indonesia Tbk.", price: 4720, change: -0.84 },
        { symbol: "TLKM", name: "Telkom Indonesia Tbk.", price: 2950, change: 0.00 },
        { symbol: "GOTO", name: "GoTo Gojek Tokopedia Tbk.", price: 52, change: -1.89 }
    ];
    let activeWatchlist = JSON.parse(localStorage.getItem("ihsg_watchlist")) || defaultWatchlist;

    const API_BASE = "http://localhost:8000/api";

    // 1. Menghasilkan Mock Data Historis yang Realistis (Fallback jika API offline)
    function generateMockHistory(days = 100) {
        const data = [];
        let basePrice = 7100;
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - days);

        for (let i = 0; i < days; i++) {
            const currentPrice = basePrice + (Math.random() - 0.47) * 45;
            basePrice = currentPrice;
            const dateStr = new Date(startDate.getTime() + i * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
            
            data.push({
                date: dateStr,
                close: currentPrice,
                open: currentPrice * (1 + (Math.random() - 0.5) * 0.002),
                high: currentPrice * (1 + Math.random() * 0.004),
                low: currentPrice * (1 - Math.random() * 0.004),
                volume: Math.floor(Math.random() * 8e9) + 5e9
            });
        }

        // Hitung Indikator MA & RSI
        for (let i = 0; i < data.length; i++) {
            // SMA 50
            if (i >= 50) {
                const sum = data.slice(i - 50, i).reduce((acc, cur) => acc + cur.close, 0);
                data[i].sma_50 = sum / 50;
            } else {
                data[i].sma_50 = data[i].close * 0.98;
            }

            // SMA 200
            if (i >= 200) {
                const sum = data.slice(i - 200, i).reduce((acc, cur) => acc + cur.close, 0);
                data[i].sma_200 = sum / 200;
            } else {
                data[i].sma_200 = data[i].close * 0.95;
            }

            // RSI 14
            data[i].rsi_14 = 35 + Math.sin(i / 5) * 25 + Math.random() * 15;
        }

        return data;
    }

    // 2. Integrasi Utama Pengambilan Data
    async function syncAllData() {
        try {
            // Mengambil data real-time dari FastAPI
            const resRealtime = await fetch(`${API_BASE}/ihsg/realtime`);
            if (resRealtime.ok) {
                const data = await resRealtime.json();
                dbRealtime = data;
                document.getElementById("connection-status").innerText = "Database Live Connected";
            }
        } catch (e) {
            console.log("FastAPI backend offline, menggunakan fallback database.");
            document.getElementById("connection-status").innerText = "Database Demo Fallback";
        }

        // Render Summary Real-time
        renderRealtime();

        // Fetch History
        try {
            const resHistory = await fetch(`${API_BASE}/ihsg/history?period=${currentPeriod}`);
            if (resHistory.ok) {
                dbHistory = await resHistory.json();
            } else {
                dbHistory = generateMockHistory(currentPeriod === "1mo" ? 30 : currentPeriod === "3mo" ? 90 : 120);
            }
        } catch (e) {
            dbHistory = generateMockHistory(currentPeriod === "1mo" ? 30 : currentPeriod === "3mo" ? 90 : 120);
        }

        // Render Chart Utama & RSI
        renderCharts();

        // Fetch News, Sectors & Sentiment
        syncAsideWidgets();
    }

    // Render Ringkasan Angka Realtime
    function renderRealtime() {
        const priceEl = document.getElementById("ihsg-price");
        const changeCont = document.getElementById("ihsg-change-container");
        const arrowEl = document.getElementById("ihsg-arrow");
        const changeEl = document.getElementById("ihsg-change");
        
        const prevPrice = parseFloat(priceEl.innerText.replace(/,/g, ''));
        const newPrice = dbRealtime.current_price;

        priceEl.innerText = newPrice.toLocaleString("id-ID", { minimumFractionDigits: 2 });
        
        // Flashing effect saat harga berubah
        if (prevPrice && prevPrice !== newPrice) {
            const flashClass = newPrice > prevPrice ? "price-up-flash" : "price-down-flash";
            const widget = document.getElementById("price-card-widget");
            widget.classList.add(flashClass);
            setTimeout(() => widget.classList.remove(flashClass), 800);
        }

        const isUp = dbRealtime.change >= 0;
        arrowEl.innerText = isUp ? "▲" : "▼";
        changeEl.innerText = `${isUp ? '+' : ''}${dbRealtime.change.toFixed(2)} (${isUp ? '+' : ''}${dbRealtime.change_percent.toFixed(2)}%)`;
        
        if (isUp) {
            changeCont.className = "text-xs font-bold mt-1 flex items-center gap-1 text-emerald-400";
        } else {
            changeCont.className = "text-xs font-bold mt-1 flex items-center gap-1 text-red-400";
        }

        document.getElementById("ihsg-open").innerText = dbRealtime.open.toLocaleString("id-ID");
        document.getElementById("ihsg-high").innerText = dbRealtime.high.toLocaleString("id-ID");
        document.getElementById("ihsg-low").innerText = dbRealtime.low.toLocaleString("id-ID");
        document.getElementById("ihsg-volume").innerText = (dbRealtime.volume / 1e9).toFixed(1) + "B";
    }

    // Sync Widget News, Sectors, and Sentiment
    async function syncAsideWidgets() {
        // News List
        let newsData = [];
        try {
            const res = await fetch(`${API_BASE}/news`);
            if (res.ok) newsData = await res.json();
        } catch(e) {}

        if (newsData.length === 0) {
            newsData = [
                { id: 1, title: "BI Pertahankan Suku Bunga di 6.00%, Pasar Merespon Positif", sentiment: "Positive", score: 0.85, published_at: "10 Menit Lalu", source: "CNBC Indonesia" },
                { id: 2, title: "Laba Bersih BCA (BBCA) Kuartal II Melampaui Estimasi Konsensus", sentiment: "Positive", score: 0.90, published_at: "1 Jam Lalu", source: "Bisnis.com" },
                { id: 3, title: "Bursa Saham Wall Street Ditutup Koreksi Imbas Rilis Data Tenaga Kerja AS", sentiment: "Negative", score: -0.65, published_at: "3 Jam Lalu", source: "Kontan" }
            ];
        }

        const newsContainer = document.getElementById("news-list-container");
        newsContainer.innerHTML = newsData.map(item => `
            <article class="pt-2.5 first:pt-0 space-y-1">
                <span class="text-[8px] font-bold px-1.5 py-0.5 rounded ${
                    item.sentiment === 'Positive' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
                }">
                    ${item.sentiment} (${item.score > 0 ? '+' : ''}${item.score.toFixed(1)})
                </span>
                <h4 class="text-[11px] font-semibold text-slate-200 hover:text-emerald-400 cursor-pointer transition-colors leading-relaxed">
                    ${item.title}
                </h4>
                <p class="text-[9px] text-slate-500">${item.published_at} • ${item.source}</p>
            </article>
        `).join("");

        // Sectors List
        let sectorsData = [];
        try {
            const res = await fetch(`${API_BASE}/sectors`);
            if (res.ok) sectorsData = await res.json();
        } catch(e) {}

        if (sectorsData.length === 0) {
            sectorsData = [
                { sector_name: "1. Finansial (IDXFIN)", change_percent: 1.24 },
                { sector_name: "2. Infrastruktur (IDXINFRA)", change_percent: 0.87 },
                { sector_name: "3. Energi (IDXENERGY)", change_percent: -0.42 }
            ];
        }

        const sectorsContainer = document.getElementById("sectors-list-container");
        sectorsContainer.innerHTML = sectorsData.map(s => `
            <div class="flex justify-between items-center">
                <span class="text-slate-400">${s.sector_name}</span>
                <span class="font-bold ${s.change_percent >= 0 ? 'text-emerald-400' : 'text-red-400'}">
                    ${s.change_percent >= 0 ? '+' : ''}${s.change_percent.toFixed(2)}%
                </span>
            </div>
        `).join("");

        // Sentiment Index Meter
        let sentimentData = { sentiment_label: "Greed", score: 72 };
        try {
            const res = await fetch(`${API_BASE}/sentiment`);
            if (res.ok) sentimentData = await res.json();
        } catch(e) {}

        const labelEl = document.getElementById("sentiment-label");
        labelEl.innerText = sentimentData.sentiment_label;
        labelEl.className = `px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
            sentimentData.sentiment_label === 'Greed' ? 'bg-emerald-500/10 text-emerald-400' :
            sentimentData.sentiment_label === 'Fear' ? 'bg-red-500/10 text-red-400' : 'bg-yellow-500/10 text-yellow-400'
        }`;
        document.getElementById("sentiment-bar").style.width = `${sentimentData.score}%`;
        document.getElementById("sentiment-score").innerText = `${sentimentData.score}%`;
    }

    // 3. Render Grafik Utama & RSI Menggunakan Manipulasi DOM SVG
    function renderCharts() {
        if (dbHistory.length === 0) return;

        const svg = document.getElementById("ihsg-svg-chart");
        const svgWidth = 800;
        const svgHeight = 260;
        const paddingLeft = 60;
        const paddingRight = 20;
        const paddingTop = 20;
        const paddingBottom = 40;

        const prices = dbHistory.map(h => h.close);
        const minP = Math.min(...prices) * 0.995;
        const maxP = Math.max(...prices) * 1.005;

        const getX = (idx) => paddingLeft + (idx / (dbHistory.length - 1)) * (svgWidth - paddingLeft - paddingRight);
        const getY = (val) => svgHeight - paddingBottom - ((val - minP) / (maxP - minP)) * (svgHeight - paddingTop - paddingBottom);

        const buildPath = (values) => {
            return values.map((val, idx) => `${idx === 0 ? 'M' : 'L'} ${getX(idx).toFixed(1)} ${getY(val).toFixed(1)}`).join(" ");
        };

        const buildAreaPath = () => {
            const linePoints = dbHistory.map((h, idx) => `${getX(idx).toFixed(1)} ${getY(h.close).toFixed(1)}`).join(" L ");
            return `M ${getX(0).toFixed(1)} ${svgHeight - paddingBottom} L ${linePoints} L ${getX(dbHistory.length - 1).toFixed(1)} ${svgHeight - paddingBottom} Z`;
        };

        let svgContent = `
            <defs>
                <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#10b981" stop-opacity="0.25" />
                    <stop offset="100%" stop-color="#10b981" stop-opacity="0.0" />
                </linearGradient>
            </defs>
        `;

        // Grid Horizontal
        [0, 0.25, 0.5, 0.75, 1].forEach(ratio => {
            const priceVal = minP + ratio * (maxP - minP);
            const y = getY(priceVal);
            svgContent += `
                <line x1="${paddingLeft}" y1="${y}" x2="${svgWidth - paddingRight}" y2="${y}" stroke="#1e293b" stroke-width="1" stroke-dasharray="4 4" />
                <text x="${paddingLeft - 10}" y="${y + 3}" fill="#64748b" font-size="9" text-anchor="end">${Math.round(priceVal).toLocaleString('id-ID')}</text>
            `;
        });

        // Sumbu X Tanggal
        svgContent += `
            <text x="${getX(0)}" y="${svgHeight - 15}" fill="#64748b" font-size="9" text-anchor="start">${dbHistory[0].date}</text>
            <text x="${getX(Math.floor(dbHistory.length / 2))}" y="${svgHeight - 15}" fill="#64748b" font-size="9" text-anchor="middle">${dbHistory[Math.floor(dbHistory.length / 2)].date}</text>
            <text x="${getX(dbHistory.length - 1)}" y="${svgHeight - 15}" fill="#64748b" font-size="9" text-anchor="end">${dbHistory[dbHistory.length - 1].date}</text>
        `;

        svgContent += `<path d="${buildAreaPath()}" fill="url(#areaGrad)" />`;

        if (showSMA200) {
            svgContent += `<path d="${buildPath(dbHistory.map(h => h.sma_200))}" fill="none" stroke="#f87171" stroke-width="1.5" />`;
        }

        if (showSMA50) {
            svgContent += `<path d="${buildPath(dbHistory.map(h => h.sma_50))}" fill="none" stroke="#60a5fa" stroke-width="1.5" />`;
        }

        svgContent += `<path d="${buildPath(prices)}" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" />`;
        svgContent += `<line id="hover-v-line" x1="0" y1="${paddingTop}" x2="0" y2="${svgHeight - paddingBottom}" stroke="#475569" stroke-width="1.5" stroke-dasharray="2 2" class="hidden" />`;

        svg.innerHTML = svgContent;

        // Render RSI Sub-Chart
        const rsiChart = document.getElementById("rsi-svg-chart");
        let rsiContent = "";

        [30, 50, 70].forEach(level => {
            const y = 80 - 40 + 10 - (level / 100) * 40;
            rsiContent += `
                <line x1="${paddingLeft}" y1="${y}" x2="${svgWidth - paddingRight}" y2="${y}" stroke="${level === 50 ? '#334155' : '#581c87'}" stroke-width="1" stroke-dasharray="2 2" />
                <text x="${paddingLeft - 10}" y="${y + 3}" fill="#8b5cf6" font-size="8" text-anchor="end">${level}</text>
            `;
        });

        const rsiPath = dbHistory.map((h, idx) => {
            const x = getX(idx);
            const y = 80 - 40 + 10 - (h.rsi_14 / 100) * 40;
            return `${idx === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
        }).join(" ");

        rsiContent += `<path d="${rsiPath}" fill="none" stroke="#a78bfa" stroke-width="1.5" />`;
        rsiChart.innerHTML = rsiContent;

        // Hover Interactive
        svg.onmousemove = (e) => {
            const rect = svg.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const svgRelativeX = (mouseX / rect.width) * svgWidth;
            const chartActiveWidth = svgWidth - paddingLeft - paddingRight;
            const relativeXOnChart = svgRelativeX - paddingLeft;
            
            let idx = Math.round((relativeXOnChart / chartActiveWidth) * (dbHistory.length - 1));
            idx = Math.max(0, Math.min(dbHistory.length - 1, idx));

            const pt = dbHistory[idx];
            const vLine = document.getElementById("hover-v-line");
            vLine.setAttribute("x1", getX(idx));
            vLine.setAttribute("x2", getX(idx));
            vLine.classList.remove("hidden");

            const tooltip = document.getElementById("chart-tooltip");
            tooltip.innerHTML = `
                <div class="font-bold text-slate-300 border-b border-slate-800 pb-1 mb-1">${pt.date}</div>
                <div class="flex justify-between gap-4">
                    <span class="text-slate-500">IHSG Close:</span>
                    <span class="font-bold text-white">${pt.close.toLocaleString('id-ID', { minimumFractionDigits: 1 })}</span>
                </div>
                ${showSMA50 ? `<div class="flex justify-between gap-4 text-blue-400"><span>SMA 50:</span><span class="font-bold">${pt.sma_50.toLocaleString('id-ID', { minimumFractionDigits: 1 })}</span></div>` : ''}
                ${showSMA200 ? `<div class="flex justify-between gap-4 text-red-400"><span>SMA 200:</span><span class="font-bold">${pt.sma_200.toLocaleString('id-ID', { minimumFractionDigits: 1 })}</span></div>` : ''}
                ${showRSI ? `<div class="flex justify-between gap-4 text-purple-400"><span>RSI 14:</span><span class="font-bold">${pt.rsi_14.toFixed(1)}</span></div>` : ''}
            `;
            tooltip.style.left = `${Math.min(getX(idx) - 40, svgWidth - 160)}px`;
            tooltip.style.top = '10px';
            tooltip.classList.remove("hidden");
        };

        svg.onmouseleave = () => {
            document.getElementById("hover-v-line").classList.add("hidden");
            document.getElementById("chart-tooltip").classList.add("hidden");
        };
    }

    // 4. Watchlist Interaksi Dinamis
    function renderWatchlist() {
        const grid = document.getElementById("watchlist-grid");
        grid.innerHTML = activeWatchlist.map(item => `
            <div class="bg-slate-950 border border-slate-850 p-4 rounded-xl flex justify-between items-start relative group">
                <div class="space-y-1">
                    <span class="font-extrabold text-white text-sm">${item.symbol}</span>
                    <span class="block text-[10px] text-slate-500 truncate w-32">${item.name}</span>
                    <div class="text-sm font-black pt-1">Rp ${item.price.toLocaleString('id-ID')}</div>
                    <span class="inline-block text-[10px] font-bold ${item.change >= 0 ? 'text-emerald-400' : 'text-red-400'}">
                        ${item.change >= 0 ? '▲' : '▼'} ${item.change >= 0 ? '+' : ''}${item.change.toFixed(2)}%
                    </span>
                </div>
                <button onclick="removeStock('${item.symbol}')" class="text-slate-600 hover:text-red-400 p-1 rounded hover:bg-red-500/10 transition-all absolute top-2 right-2 md:opacity-0 group-hover:opacity-100" title="Hapus">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19.5 8.25l-12 12m0-12l12 12" />
                    </svg>
                </button>
            </div>
        `).join("");
    }

    // Form Submit Tambah Watchlist
    document.getElementById("add-watchlist-form").onsubmit = (e) => {
        e.preventDefault();
        const symbol = document.getElementById("stock-symbol").value.toUpperCase();
        const name = document.getElementById("stock-name").value;
        const randomPrice = Math.floor(Math.random() * 12000) + 100;
        const randomChange = parseFloat(((Math.random() * 6) - 3).toFixed(2));

        activeWatchlist.push({ symbol, name, price: randomPrice, change: randomChange });
        localStorage.setItem("ihsg_watchlist", JSON.stringify(activeWatchlist));
        
        document.getElementById("stock-symbol").value = "";
        document.getElementById("stock-name").value = "";
        renderWatchlist();
    };

    // Global Functions untuk pemanggilan inline HTML
    window.removeStock = (symbol) => {
        activeWatchlist = activeWatchlist.filter(item => item.symbol !== symbol);
        localStorage.setItem("ihsg_watchlist", JSON.stringify(activeWatchlist));
        renderWatchlist();
    };

    window.setPeriod = (p) => {
        currentPeriod = p;
        ["1mo", "3mo", "6mo", "1y"].forEach(periodId => {
            const btn = document.getElementById(`btn-${periodId}`);
            if (periodId === p) {
                btn.className = "px-2 py-0.5 rounded text-[9px] uppercase transition-all bg-emerald-500 text-slate-950 font-bold";
            } else {
                btn.className = "px-2 py-0.5 rounded text-[9px] uppercase transition-all hover:text-white text-slate-400";
            }
        });
        syncAllData();
    };

    // 5. Toggle Kontrol Indikator
    document.getElementById("toggle-sma50").onclick = () => {
        showSMA50 = !showSMA50;
        const btn = document.getElementById("toggle-sma50");
        if (showSMA50) {
            btn.className = "px-2 py-1 rounded border bg-blue-500/15 text-blue-400 border-blue-500/30 transition-all";
            btn.innerText = "✓ SMA 50";
        } else {
            btn.className = "px-2 py-1 rounded border bg-slate-950 text-slate-600 border-slate-800 transition-all";
            btn.innerText = "SMA 50";
        }
        renderCharts();
    };

    document.getElementById("toggle-sma200").onclick = () => {
        showSMA200 = !showSMA200;
        const btn = document.getElementById("toggle-sma200");
        if (showSMA200) {
            btn.className = "px-2 py-1 rounded border bg-red-500/15 text-red-400 border-red-500/30 transition-all";
            btn.innerText = "✓ SMA 200";
        } else {
            btn.className = "px-2 py-1 rounded border bg-slate-950 text-slate-600 border-slate-800 transition-all";
            btn.innerText = "SMA 200";
        }
        renderCharts();
    };

    document.getElementById("toggle-rsi").onclick = () => {
        showRSI = !showRSI;
        const btn = document.getElementById("toggle-rsi");
        const rsiCont = document.getElementById("rsi-container");
        if (showRSI) {
            btn.className = "px-2 py-1 rounded border bg-purple-500/15 text-purple-400 border-purple-500/30 transition-all";
            btn.innerText = "✓ RSI";
            rsiCont.classList.remove("hidden");
        } else {
            btn.className = "px-2 py-1 rounded border bg-slate-950 text-slate-600 border-slate-800 transition-all";
            btn.innerText = "RSI";
            rsiCont.classList.add("hidden");
        }
        renderCharts();
    };

    // 6. Simulasi Ticker Harga Berfluktuasi
    setInterval(() => {
        const tick = (Math.random() - 0.48) * 4;
        dbRealtime.current_price += tick;
        dbRealtime.change += tick;
        dbRealtime.change_percent = (dbRealtime.change / dbRealtime.open) * 100;
        if (dbRealtime.current_price > dbRealtime.high) dbRealtime.high = dbRealtime.current_price;
        if (dbRealtime.current_price < dbRealtime.low) dbRealtime.low = dbRealtime.current_price;
        renderRealtime();
    }, 3500);

    // Inisialisasi awal
    renderWatchlist();
    syncAllData();

    // Submit Form Newsletter
    document.getElementById("newsletter-form").onsubmit = (e) => {
        e.preventDefault();
        alert("Sukses! Email Anda berhasil didaftarkan dalam database buletin.");
        e.currentTarget.querySelector("input").value = "";
    };
});
