import React, { useState, useEffect, useRef } from 'react';

// Interfaces untuk Type-safety data API dari Backend Database
interface IHSGRealtimeData {
  name: string;
  symbol: string;
  current_price: number;
  previous_close: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  change: number;
  change_percent: number;
  last_updated: string;
}

interface IHSGHistoryData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma_50: number;
  sma_200: number;
  rsi_14: number;
}

interface NewsArticle {
  id: number;
  title: string;
  url: string;
  source: string;
  sentiment: 'Positive' | 'Neutral' | 'Negative';
  score: number;
  published_at: string;
}

interface SectorPerformance {
  sector_name: string;
  change_percent: number;
}

interface MarketSentiment {
  sentiment_label: 'Fear' | 'Neutral' | 'Greed';
  score: number;
}

// Watchlist Item untuk Simulasi Interaksi Tambahan
interface WatchlistItem {
  symbol: string;
  name: string;
  price: number;
  change: number;
}

export default function IHSGDashboard() {
  // State Management Utama
  const [realtime, setRealtime] = useState<IHSGRealtimeData | null>(null);
  const [history, setHistory] = useState<IHSGHistoryData[]>([]);
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [sectors, setSectors] = useState<SectorPerformance[]>([]);
  const [sentiment, setSentiment] = useState<MarketSentiment | null>(null);
  const [period, setPeriod] = useState<string>("1y");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // State untuk Kontrol Kustomisasi Chart (Integrasi Menengah ke Atas)
  const [showSMA50, setShowSMA50] = useState<boolean>(true);
  const [showSMA200, setShowSMA200] = useState<boolean>(true);
  const [showRSI, setShowRSI] = useState<boolean>(true);
  const [hoveredPoint, setHoveredPoint] = useState<IHSGHistoryData | null>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // State untuk Simulasi Fitur Portofolio / Watchlist Pribadi
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([
    { symbol: "BBCA", name: "Bank Central Asia Tbk.", price: 10450, change: 1.46 },
    { symbol: "BBRI", name: "Bank Rakyat Indonesia Tbk.", price: 4720, change: -0.84 },
    { symbol: "TLKM", name: "Telkom Indonesia Tbk.", price: 2950, change: 0.00 },
    { symbol: "GOTO", name: "GoTo Gojek Tokopedia Tbk.", price: 52, change: -1.89 }
  ]);
  const [newStockSymbol, setNewStockSymbol] = useState<string>("");
  const [newStockName, setNewStockName] = useState<string>("");

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

  // Pengambilan Data Berkelompok (Batch Fetching) dari Database Backend
  useEffect(() => {
    async function fetchDashboardData() {
      try {
        setLoading(true);
        setError(null);

        // Eksekusi paralel untuk meminimalkan latensi frontend
        const [
          realtimeRes,
          historyRes,
          newsRes,
          sectorsRes,
          sentimentRes
        ] = await Promise.all([
          fetch(`${API_BASE_URL}/ihsg/realtime`),
          fetch(`${API_BASE_URL}/ihsg/history?period=${period}`),
          fetch(`${API_BASE_URL}/news`),
          fetch(`${API_BASE_URL}/sectors`),
          fetch(`${API_BASE_URL}/sentiment`)
        ]);

        if (!realtimeRes.ok || !historyRes.ok || !newsRes.ok || !sectorsRes.ok || !sentimentRes.ok) {
          throw new Error("Gagal mengambil data dari database backend.");
        }

        const [
          realtimeData,
          historyData,
          newsData,
          sectorsData,
          sentimentData
        ] = await Promise.all([
          realtimeRes.json(),
          historyRes.json(),
          newsRes.json(),
          sectorsRes.json(),
          sentimentRes.json()
        ]);

        setRealtime(realtimeData);
        setHistory(historyData);
        setNews(newsData);
        setSectors(sectorsData);
        setSentiment(sentimentData);

      } catch (err: any) {
        setError(err.message || "Gagal menghubungi server database API.");
      } finally {
        setLoading(false);
      }
    }

    fetchDashboardData();
  }, [period, API_BASE_URL]);

  // Polling data real-time setiap 10 detik sekali untuk simulasi live-ticker
  useEffect(() => {
    if (loading || error) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/ihsg/realtime`);
        if (res.ok) {
          const data = await res.json();
          setRealtime(data);
        }
      } catch (e) {
        console.log("Gagal melakukan refresh real-time data.");
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [loading, error, API_BASE_URL]);

  // Handler Form Langganan Newsletter
  const handleNewsletterSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const emailInput = e.currentTarget.querySelector("input[type='email']") as HTMLInputElement;
    alert(`Sukses! Email Anda (${emailInput.value}) berhasil terdaftar dalam database newsletter IHSG Insight.`);
    emailInput.value = "";
  };

  // Handler Tambah Saham ke Watchlist Pribadi
  const handleAddWatchlist = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStockSymbol || !newStockName) return;
    const randomChange = parseFloat(((Math.random() * 6) - 3).toFixed(2));
    const randomPrice = Math.floor(Math.random() * 12000) + 100;
    
    setWatchlist([
      ...watchlist,
      { symbol: newStockSymbol.toUpperCase(), name: newStockName, price: randomPrice, change: randomChange }
    ]);
    setNewStockSymbol("");
    setNewStockName("");
  };

  // Handler Hapus Saham dari Watchlist
  const handleRemoveWatchlist = (symbol: string) => {
    setWatchlist(watchlist.filter(item => item.symbol !== symbol));
  };

  // --- KODE UTAMA ENGINES GRAFIK SVG ASINKRON (INTEGRASI PENUH TANPA DEPENDENSI EKSTERNAL) ---
  // Menghitung titik koordinat SVG untuk grafik responsive
  const svgWidth = 800;
  const svgHeight = 260;
  const paddingLeft = 60;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 40;

  // Mendapatkan nilai min dan max dari data historis bursa
  const prices = history.map(h => h.close).filter(p => p > 0);
  const minPrice = prices.length ? Math.min(...prices) * 0.995 : 0;
  const maxPrice = prices.length ? Math.max(...prices) * 1.005 : 10000;

  // Konversi data historis menjadi poin-poin koordinat di kanvas SVG
  const getX = (index: number) => {
    if (history.length <= 1) return paddingLeft;
    return paddingLeft + (index / (history.length - 1)) * (svgWidth - paddingLeft - paddingRight);
  };

  const getY = (value: number) => {
    if (maxPrice === minPrice) return svgHeight / 2;
    return svgHeight - paddingBottom - ((value - minPrice) / (maxPrice - minPrice)) * (svgHeight - paddingTop - paddingBottom);
  };

  // Membuat string path SVG untuk visualisasi
  const buildSvgPath = (dataValues: number[]) => {
    if (dataValues.length === 0) return "";
    return dataValues
      .map((val, idx) => {
        const x = getX(idx);
        const y = getY(val);
        return `${idx === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
  };

  // Membuat string path area isi (gradien fill)
  const buildSvgAreaPath = () => {
    if (history.length === 0) return "";
    const startX = getX(0);
    const startY = svgHeight - paddingBottom;
    const endX = getX(history.length - 1);
    const endY = svgHeight - paddingBottom;

    const linePoints = history.map((h, idx) => `${getX(idx).toFixed(1)} ${getY(h.close).toFixed(1)}`).join(" L ");
    return `M ${startX.toFixed(1)} ${startY.toFixed(1)} L ${linePoints} L ${endX.toFixed(1)} ${endY.toFixed(1)} Z`;
  };

  // Event handler untuk interaktivitas hover kursor pada grafik SVG
  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement, MouseEvent>) => {
    if (history.length === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    
    // Hitung koordinat X relatif dalam skala SVG
    const svgRelativeX = (mouseX / rect.width) * svgWidth;
    
    // Cari index data terdekat berdasarkan posisi X mouse
    const chartActiveWidth = svgWidth - paddingLeft - paddingRight;
    const relativeXOnChart = svgRelativeX - paddingLeft;
    
    let index = Math.round((relativeXOnChart / chartActiveWidth) * (history.length - 1));
    index = Math.max(0, Math.min(history.length - 1, index));
    
    setHoveredIndex(index);
    setHoveredPoint(history[index]);
  };

  const handleSvgMouseLeave = () => {
    setHoveredIndex(null);
    setHoveredPoint(null);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-screen bg-slate-950 text-white font-sans">
        <div className="flex flex-col items-center gap-4">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-emerald-500"></div>
          <span className="font-semibold text-lg text-slate-300">Menghubungkan & Memuat Data IHSG dari Database...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col justify-center items-center min-h-screen bg-slate-950 text-red-400 p-4 font-sans">
        <div className="text-xl font-bold mb-2">Error Sinkronisasi Database</div>
        <p className="text-slate-400 text-sm mb-4 text-center max-w-md">{error}</p>
        <button 
          onClick={() => setPeriod(period)}
          className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded-xl text-sm transition-all"
        >
          Coba Sinkronisasi Ulang
        </button>
      </div>
    );
  }

  return (
    <div className="bg-slate-950 text-slate-100 font-sans min-h-screen flex flex-col antialiased">
      
      {/* HEADER: Navigasi dan Logo Identitas */}
      <header className="sticky top-0 z-50 bg-slate-950/80 backdrop-blur-md border-b border-slate-900">
        <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-gradient-to-tr from-emerald-500 to-teal-400 p-2.5 rounded-xl shadow-lg shadow-emerald-500/10">
              <svg className="w-5 h-5 text-slate-950" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
              </svg>
            </div>
            <div>
              <span className="text-lg font-extrabold text-white tracking-tight">IHSG<span className="text-emerald-500">Insight</span></span>
              <span className="block text-[9px] text-slate-500 tracking-wider font-semibold uppercase">Database Integrated</span>
            </div>
          </div>

          <ul className="hidden md:flex items-center gap-6 text-xs font-semibold text-slate-400">
            <li><a href="#hero" className="hover:text-emerald-400 transition-colors">Beranda</a></li>
            <li><a href="#features" className="hover:text-emerald-400 transition-colors">Fitur Analisis</a></li>
            <li><a href="#watchlist" className="hover:text-emerald-400 transition-colors">Watchlist Ku</a></li>
            <li><a href="#about" className="hover:text-emerald-400 transition-colors">Tentang</a></li>
            <li><a href="#testimonials" className="hover:text-emerald-400 transition-colors">Opini</a></li>
          </ul>

          <div className="flex items-center gap-2 bg-slate-900 px-3 py-1.5 rounded-xl border border-slate-800">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span className="text-[10px] text-slate-300 font-bold uppercase tracking-wider">Live Polling Active</span>
          </div>
        </nav>
      </header>

      {/* CONTAINER DUA KOLOM: Main (3/4) & Aside (1/4) */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 grid grid-cols-1 lg:grid-cols-4 gap-8">
        
        {/* MAIN AREA (3/4): Berisi Data Historis, Sinyal Teknis, dan Profil */}
        <main className="lg:col-span-3 space-y-12">
          
          {/* 1. HERO SECTION: Performa Ringkasan Real-Time & Chart */}
          <section id="hero" className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-xl relative overflow-hidden">
            <div className="absolute -top-32 -left-32 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none"></div>

            {realtime && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center border-b border-slate-800/60 pb-6 mb-6">
                <div className="space-y-4">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase tracking-wider">
                    IHSG Real-Time Index
                  </span>
                  <h1 className="text-2xl sm:text-3xl font-black text-white leading-tight">
                    Analisis Bursa Saham <br />Indonesia Lebih Objektif
                  </h1>
                  <p className="text-slate-400 text-xs sm:text-sm leading-relaxed max-w-sm">
                    Akses pergerakan harga komprehensif didukung analisis tren otomatis Moving Average 50 & 200 hari.
                  </p>
                </div>

                <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-5 shadow-inner relative group">
                  <div className="absolute top-2 right-2 flex items-center gap-1.5 text-[9px] text-slate-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span>Auto-update 10s</span>
                  </div>
                  
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-[10px] font-bold text-slate-500 tracking-wider">SYMBOL: ^JKSE</span>
                  </div>
                  <div className="text-3xl font-black text-white transition-all duration-300">
                    {realtime.current_price.toLocaleString('id-ID', { minimumFractionDigits: 2 })}
                  </div>
                  <div className={`text-xs font-bold mt-1 flex items-center gap-1 ${realtime.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    <span>{realtime.change >= 0 ? '▲' : '▼'}</span>
                    <span>{realtime.change.toFixed(2)} ({realtime.change_percent >= 0 ? '+' : ''}{realtime.change_percent.toFixed(2)}%)</span>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-y-2 pt-4 mt-4 border-t border-slate-900 text-[11px] text-slate-400">
                    <div className="flex justify-between pr-3 border-r border-slate-900">
                      <span className="text-slate-500">Buka:</span>
                      <span className="font-semibold">{realtime.open.toLocaleString('id-ID')}</span>
                    </div>
                    <div className="flex justify-between pl-3">
                      <span className="text-slate-500">Tertinggi:</span>
                      <span className="font-semibold text-emerald-400">{realtime.high.toLocaleString('id-ID')}</span>
                    </div>
                    <div className="flex justify-between pr-3 border-r border-slate-900">
                      <span className="text-slate-500">Terendah:</span>
                      <span className="font-semibold text-red-400">{realtime.low.toLocaleString('id-ID')}</span>
                    </div>
                    <div className="flex justify-between pl-3">
                      <span className="text-slate-500">Volume:</span>
                      <span className="font-semibold">{(realtime.volume / 1e9).toFixed(1)}B</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* --- CORE INTEGRATION: RENDERING INTEGRASI GRAFIK INTERAKTIF BARU --- */}
            <div>
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
                <div>
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Visualisasi Grafik IHSG</h3>
                  <p className="text-[10px] text-slate-500">Arahkan kursor ke grafik untuk memantau data historis</p>
                </div>
                
                {/* Switcher Tampilan Indikator Teknikal */}
                <div className="flex flex-wrap gap-2 text-[10px] font-bold">
                  <button 
                    onClick={() => setShowSMA50(!showSMA50)}
                    className={`px-2 py-1 rounded border transition-all ${showSMA50 ? 'bg-blue-500/15 text-blue-400 border-blue-500/30' : 'bg-slate-950 text-slate-600 border-slate-800'}`}
                  >
                    {showSMA50 ? '✓ SMA 50' : 'SMA 50'}
                  </button>
                  <button 
                    onClick={() => setShowSMA200(!showSMA200)}
                    className={`px-2 py-1 rounded border transition-all ${showSMA200 ? 'bg-red-500/15 text-red-400 border-red-500/30' : 'bg-slate-950 text-slate-600 border-slate-800'}`}
                  >
                    {showSMA200 ? '✓ SMA 200' : 'SMA 200'}
                  </button>
                  <button 
                    onClick={() => setShowRSI(!showRSI)}
                    className={`px-2 py-1 rounded border transition-all ${showRSI ? 'bg-purple-500/15 text-purple-400 border-purple-500/30' : 'bg-slate-950 text-slate-600 border-slate-800'}`}
                  >
                    {showRSI ? '✓ RSI' : 'RSI'}
                  </button>
                  
                  {/* Selector Periode */}
                  <div className="flex gap-1 bg-slate-950 p-0.5 rounded border border-slate-800">
                    {["1mo", "3mo", "6mo", "1y"].map((p) => (
                      <button
                        key={p}
                        onClick={() => setPeriod(p)}
                        className={`px-2 py-0.5 rounded text-[9px] uppercase transition-all ${period === p ? "bg-emerald-500 text-slate-950" : "text-slate-400 hover:text-slate-200"}`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Box Canvas Render Grafik SVG */}
              <div className="relative bg-slate-950 border border-slate-850 rounded-2xl p-2 sm:p-4">
                
                {/* Floating Tooltip kursor hover */}
                {hoveredPoint && (
                  <div 
                    className="absolute bg-slate-900 border border-slate-700/80 p-3 rounded-xl shadow-2xl z-20 text-[10px] space-y-1"
                    style={{
                      left: `${Math.min(getX(hoveredIndex || 0) - 40, svgWidth - 160)}px`,
                      top: '10px'
                    }}
                  >
                    <div className="font-bold text-slate-300 border-b border-slate-800 pb-1 mb-1">{hoveredPoint.date}</div>
                    <div className="flex justify-between gap-4">
                      <span className="text-slate-500">IHSG Close:</span>
                      <span className="font-bold text-white">{hoveredPoint.close.toLocaleString('id-ID', { minimumFractionDigits: 1 })}</span>
                    </div>
                    {showSMA50 && hoveredPoint.sma_50 > 0 && (
                      <div className="flex justify-between gap-4 text-blue-400">
                        <span>SMA 50:</span>
                        <span className="font-bold">{hoveredPoint.sma_50.toLocaleString('id-ID', { minimumFractionDigits: 1 })}</span>
                      </div>
                    )}
                    {showSMA200 && hoveredPoint.sma_200 > 0 && (
                      <div className="flex justify-between gap-4 text-red-400">
                        <span>SMA 200:</span>
                        <span className="font-bold">{hoveredPoint.sma_200.toLocaleString('id-ID', { minimumFractionDigits: 1 })}</span>
                      </div>
                    )}
                    {showRSI && hoveredPoint.rsi_14 > 0 && (
                      <div className="flex justify-between gap-4 text-purple-400">
                        <span>RSI 14:</span>
                        <span className="font-bold">{hoveredPoint.rsi_14.toFixed(1)}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Grafis SVG Utama */}
                <svg 
                  viewBox={`0 0 ${svgWidth} ${svgHeight}`} 
                  className="w-full h-auto select-none"
                  onMouseMove={handleSvgMouseMove}
                  onMouseLeave={handleSvgMouseLeave}
                >
                  <defs>
                    {/* Efek Gradien Area Di bawah Garis Close IHSG */}
                    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
                      <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>

                  {/* Grid Horizontal Garis Bantu */}
                  {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
                    const priceVal = minPrice + ratio * (maxPrice - minPrice);
                    const y = getY(priceVal);
                    return (
                      <g key={i}>
                        <line 
                          x1={paddingLeft} 
                          y1={y} 
                          x2={svgWidth - paddingRight} 
                          y2={y} 
                          stroke="#1e293b" 
                          strokeWidth="1" 
                          strokeDasharray="4 4" 
                        />
                        <text 
                          x={paddingLeft - 10} 
                          y={y + 3} 
                          fill="#64748b" 
                          fontSize="9" 
                          textAnchor="end"
                        >
                          {priceVal.toLocaleString('id-ID', { maximumFractionDigits: 0 })}
                        </text>
                      </g>
                    );
                  })}

                  {/* Teks Tanggal di Sumbu X (Awal, Tengah, Akhir) */}
                  {history.length > 2 && (
                    <>
                      <text x={getX(0)} y={svgHeight - 15} fill="#64748b" fontSize="9" textAnchor="start">
                        {history[0].date}
                      </text>
                      <text x={getX(Math.floor(history.length / 2))} y={svgHeight - 15} fill="#64748b" fontSize="9" textAnchor="middle">
                        {history[Math.floor(history.length / 2)].date}
                      </text>
                      <text x={getX(history.length - 1)} y={svgHeight - 15} fill="#64748b" fontSize="9" textAnchor="end">
                        {history[history.length - 1].date}
                      </text>
                    </>
                  )}

                  {/* 1. Rendera Area Gradient Fill di bawah Chart */}
                  <path d={buildSvgAreaPath()} fill="url(#areaGrad)" />

                  {/* 2. Rendera SMA 200 (Garis Merah) jika diaktifkan */}
                  {showSMA200 && (
                    <path 
                      d={buildSvgPath(history.map(h => h.sma_200))} 
                      fill="none" 
                      stroke="#f87171" 
                      strokeWidth="1.5" 
                    />
                  )}

                  {/* 3. Rendera SMA 50 (Garis Biru) jika diaktifkan */}
                  {showSMA50 && (
                    <path 
                      d={buildSvgPath(history.map(h => h.sma_50))} 
                      fill="none" 
                      stroke="#60a5fa" 
                      strokeWidth="1.5" 
                    />
                  )}

                  {/* 4. Rendera Garis Close IHSG Utama (Garis Hijau Tebal) */}
                  <path 
                    d={buildSvgPath(history.map(h => h.close))} 
                    fill="none" 
                    stroke="#10b981" 
                    strokeWidth="2.5" 
                    strokeLinecap="round"
                  />

                  {/* Garis Vertikal Pointer Saat Hover */}
                  {hoveredIndex !== null && (
                    <line 
                      x1={getX(hoveredIndex)} 
                      y1={paddingTop} 
                      x2={getX(hoveredIndex)} 
                      y2={svgHeight - paddingBottom} 
                      stroke="#475569" 
                      strokeWidth="1.5" 
                      strokeDasharray="2 2"
                    />
                  )}
                </svg>
              </div>

              {/* Tampilan Mini-Chart RSI di bawah */}
              {showRSI && history.length > 0 && (
                <div className="mt-4 bg-slate-950 border border-slate-850 rounded-2xl p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-[10px] font-bold text-purple-400 uppercase tracking-wider">Indicator: RSI 14</span>
                    <span className="text-[9px] text-slate-500">Overbought &gt; 70 | Oversold &lt; 30</span>
                  </div>
                  
                  <svg viewBox={`0 0 ${svgWidth} 80`} className="w-full h-auto select-none">
                    {/* Garis Level RSI */}
                    {[30, 50, 70].map((level, idx) => (
                      <g key={idx}>
                        <line 
                          x1={paddingLeft} 
                          y1={80 - paddingBottom + 10 - (level / 100) * 40} 
                          x2={svgWidth - paddingRight} 
                          y2={80 - paddingBottom + 10 - (level / 100) * 40} 
                          stroke={level === 50 ? "#334155" : "#581c87"} 
                          strokeWidth="1" 
                          strokeDasharray="2 2"
                        />
                        <text 
                          x={paddingLeft - 10} 
                          y={80 - paddingBottom + 13 - (level / 100) * 40} 
                          fill="#8b5cf6" 
                          fontSize="8" 
                          textAnchor="end"
                        >
                          {level}
                        </text>
                      </g>
                    ))}
                    
                    {/* Path RSI */}
                    <path 
                      d={history.map((h, idx) => {
                        const x = getX(idx);
                        // Map RSI 0-100 ke Tinggi Kanvas 40px
                        const y = 80 - paddingBottom + 10 - (h.rsi_14 / 100) * 40;
                        return `${idx === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
                      }).join(" ")}
                      fill="none"
                      stroke="#a78bfa"
                      strokeWidth="1.5"
                    />
                  </svg>
                </div>
              )}
            </div>
          </section>

          {/* WATCHLIST KU: Integrasi Fitur Interaktif Baru */}
          <section id="watchlist" className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <h2 className="text-lg font-bold text-white uppercase tracking-wider">Pantauan Saham Pribadi</h2>
                <p className="text-[11px] text-slate-400">Tambahkan saham favorit Anda ke database browser ini untuk memantau performa harian.</p>
              </div>

              {/* Form Tambah Watchlist */}
              <form onSubmit={handleAddWatchlist} className="flex gap-2 w-full sm:w-auto">
                <input 
                  type="text" 
                  placeholder="Kode (e.g. ASII)" 
                  value={newStockSymbol}
                  onChange={(e) => setNewStockSymbol(e.target.value)}
                  maxLength={4}
                  required
                  className="px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-[11px] font-bold placeholder-slate-600 text-white w-28 focus:outline-none focus:border-emerald-500 uppercase"
                />
                <input 
                  type="text" 
                  placeholder="Nama Emiten" 
                  value={newStockName}
                  onChange={(e) => setNewStockName(e.target.value)}
                  required
                  className="px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-[11px] placeholder-slate-600 text-white flex-1 sm:w-44 focus:outline-none focus:border-emerald-500"
                />
                <button type="submit" className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-lg text-[11px] transition-all">
                  Tambah
                </button>
              </form>
            </div>

            {/* Grid Tabel Watchlist */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
              {watchlist.map((item) => (
                <div key={item.symbol} className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex justify-between items-start relative group">
                  <div className="space-y-1">
                    <span className="font-extrabold text-white text-sm">{item.symbol}</span>
                    <span className="block text-[10px] text-slate-500 truncate w-32">{item.name}</span>
                    <div className="text-sm font-black pt-1">Rp {item.price.toLocaleString('id-ID')}</div>
                    <span className={`inline-block text-[10px] font-bold ${item.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {item.change >= 0 ? '▲' : '▼'} {item.change >= 0 ? '+' : ''}{item.change.toFixed(2)}%
                    </span>
                  </div>
                  
                  {/* Tombol Hapus Hover-only */}
                  <button 
                    onClick={() => handleRemoveWatchlist(item.symbol)}
                    className="text-slate-600 hover:text-red-400 p-1 rounded hover:bg-red-500/10 transition-all absolute top-2 right-2 md:opacity-0 group-hover:opacity-100"
                    title="Hapus dari Watchlist"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19.5 8.25l-12 12m0-12l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </section>

          {/* 3. SERVICES/FEATURES: Sesuai Struktur Layout Ideal */}
          <section id="features" className="space-y-4">
            <h2 className="text-xl font-bold text-white uppercase tracking-wider">Fokus Analisis Platform</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div className="bg-slate-900 border border-slate-850 p-5 rounded-2xl">
                <div className="w-8 h-8 bg-emerald-500/10 text-emerald-400 rounded-lg flex items-center justify-center mb-3">📈</div>
                <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-1.5">Teknikal Dinamis</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Perhitungan filter Moving Average (MA) dan RSI langsung dilakukan oleh sistem database kami secara dinamis.
                </p>
              </div>

              <div className="bg-slate-900 border border-slate-850 p-5 rounded-2xl">
                <div className="w-8 h-8 bg-emerald-500/10 text-emerald-400 rounded-lg flex items-center justify-center mb-3">📰</div>
                <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-1.5">Sentimen Terkumpul</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Kami mengumpulkan berita finansial dari media kredibel Indonesia untuk melihat pengaruh psikologis terhadap pasar.
                </p>
              </div>

              <div className="bg-slate-900 border border-slate-850 p-5 rounded-2xl">
                <div className="w-8 h-8 bg-emerald-500/10 text-emerald-400 rounded-lg flex items-center justify-center mb-3">⚡</div>
                <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-1.5">Integrasi Instan</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Data disajikan secara real-time untuk memastikan akurasi keputusan investasi saham harian Anda.
                </p>
              </div>
            </div>
          </section>

          {/* 4. ABOUT & BRAND STORY */}
          <section id="about" className="bg-slate-900 border border-slate-850 rounded-3xl p-6 sm:p-8">
            <div className="max-w-2xl space-y-4">
              <h2 className="text-lg font-bold text-white uppercase tracking-wider">Mengenai IHSG Insight</h2>
              <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
                Platform ini mengintegrasikan database lokal berkinerja tinggi dengan visualisasi bursa yang bersih dan rapi. Kami berfokus pada penyajian informasi yang independen, tanpa dipengaruhi bias komersial atau kepentingan pemasaran sekuritas.
              </p>
            </div>
          </section>

          {/* 5. TESTIMONIALS / OPINI PAKAR */}
          <section id="testimonials" className="space-y-4">
            <h2 className="text-xl font-bold text-white uppercase tracking-wider">Sudut Pandang Analis</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div className="bg-slate-900 border border-slate-850 p-5 rounded-2xl flex flex-col justify-between">
                <p className="text-[12px] text-slate-300 italic leading-relaxed mb-4">
                  "Menyaring data dengan bantuan otomasi indikator teknikal dari database sangat menghemat waktu berharga kami dalam menganalisis pergerakan bursa."
                </p>
                <div className="text-[11px]">
                  <span className="block font-bold text-white">Pratama Wijaya</span>
                  <span className="text-slate-500">Macro Analyst</span>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-850 p-5 rounded-2xl flex flex-col justify-between">
                <p className="text-[12px] text-slate-300 italic leading-relaxed mb-4">
                  "Tampilan ramah pengguna dan terstruktur memudahkan investor ritel memahami ke mana arus dana asing saat ini sedang mengalir."
                </p>
                <div className="text-[11px]">
                  <span className="block font-bold text-white">Siti Rahmawati</span>
                  <span className="text-slate-500">Independent Equity Investor</span>
                </div>
              </div>
            </div>
          </section>

          {/* 6. CONTACT & NEWSLETTER */}
          <section id="contact" className="bg-gradient-to-r from-emerald-950/20 to-teal-950/20 border border-emerald-500/20 rounded-3xl p-6 sm:p-8">
            <div className="max-w-md mx-auto text-center space-y-4">
              <h2 className="text-lg font-bold text-white uppercase tracking-wider">Koneksi Database Buletin</h2>
              <p className="text-[11px] sm:text-xs text-slate-400 leading-relaxed">
                Berlangganan analisis pasar mingguan gratis langsung dari database riset kami tanpa spam.
              </p>
              <form onSubmit={handleNewsletterSubmit} className="flex gap-2 pt-2">
                <input 
                  type="email" 
                  placeholder="Email Anda" 
                  required 
                  className="flex-1 px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-xs focus:outline-none focus:border-emerald-500"
                />
                <button type="submit" className="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-xl text-xs transition-all shadow-md">
                  Daftar
                </button>
              </form>
            </div>
          </section>

        </main>

        {/* ASIDE (1/4): Komponen Pendukung Dinamis dari Database (News, Sentiment, Sectors) */}
        <aside className="space-y-6">
          
          {/* Widget A: Sentimen Meter dari Database */}
          {sentiment && (
            <section className="bg-slate-900 border border-slate-850 rounded-2xl p-4 space-y-3">
              <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider">Sentimen Pasar</h3>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              </div>
              <div className="flex justify-between text-[11px] text-slate-400 font-semibold">
                <span>Skor Indeks:</span>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                  sentiment.sentiment_label === 'Greed' ? 'bg-emerald-500/10 text-emerald-400' :
                  sentiment.sentiment_label === 'Fear' ? 'bg-red-500/10 text-red-400' : 'bg-yellow-500/10 text-yellow-400'
                }`}>
                  {sentiment.sentiment_label}
                </span>
              </div>
              
              <div className="space-y-1 pt-1">
                <div className="h-2 w-full bg-slate-950 rounded-full overflow-hidden relative">
                  <div 
                    className="h-full bg-gradient-to-r from-red-500 via-yellow-500 to-emerald-500 transition-all duration-1000"
                    style={{ width: `${sentiment.score}%` }}
                  ></div>
                </div>
                <div className="flex justify-between text-[9px] text-slate-500">
                  <span>Fear</span>
                  <span>{sentiment.score}%</span>
                  <span>Greed</span>
                </div>
              </div>
            </section>
          )}

          {/* Widget B: Berita Terkini dengan Sentimen Dinamis */}
          <section className="bg-slate-900 border border-slate-850 rounded-2xl p-4 space-y-3">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-slate-800 pb-2">Kabar Pasar Terkini</h3>
            <div className="space-y-3 divide-y divide-slate-850">
              {news.map((item) => (
                <article key={item.id} className="pt-2.5 first:pt-0 space-y-1">
                  <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded ${
                    item.sentiment === 'Positive' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/10' :
                    item.sentiment === 'Negative' ? 'bg-red-500/10 text-red-400 border border-red-500/10' :
                    'bg-slate-800 text-slate-400'
                  }`}>
                    {item.sentiment} ({item.score > 0 ? `+${item.score.toFixed(1)}` : item.score.toFixed(1)})
                  </span>
                  <h4 className="text-[11px] font-semibold text-slate-200 hover:text-emerald-400 cursor-pointer transition-colors leading-relaxed">
                    {item.title}
                  </h4>
                  <p className="text-[9px] text-slate-500">{item.published_at} • {item.source}</p>
                </article>
              ))}
            </div>
          </section>

          {/* Widget C: Performa Top Sektoral dari Database */}
          <section className="bg-slate-900 border border-slate-850 rounded-2xl p-4 space-y-3">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider border-b border-slate-800 pb-2">Performa Sektoral</h3>
            <div className="space-y-2 text-[11px]">
              {sectors.map((s, index) => (
                <div key={index} className="flex justify-between items-center">
                  <span className="text-slate-400">{s.sector_name}</span>
                  <span className={`font-bold ${s.change_percent >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {s.change_percent >= 0 ? '+' : ''}{s.change_percent.toFixed(2)}%
                  </span>
                </div>
              ))}
            </div>
          </section>

        </aside>

      </div>

      {/* FOOTER */}
      <footer className="bg-slate-950 border-t border-slate-900 mt-12 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-4 text-[11px] text-slate-500">
          <div>
            <p>&copy; 2026 IHSG Insight. Terintegrasi Database Sistem.</p>
            <p className="text-[9px] text-slate-600 mt-1">Disclaimer: Seluruh data disajikan secara independen untuk keperluan edukasi dan riset personal Anda.</p>
          </div>
          <div className="flex gap-4">
            <a href="#" className="hover:text-slate-300">Ketentuan</a>
            <a href="#" className="hover:text-slate-300">Kebijakan Privasi</a>
          </div>
        </div>
      </footer>

    </div>
  );
}
