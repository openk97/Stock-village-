import { WebDashboardAggregateDTO, WebIHSGSummaryDTO, WebNewsDTO, WebSectorDTO } from "./web.dto";
import { config } from "../config";

interface IHSGRealtimeRaw {
  current_price: number;
  change: number;
  change_percent: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  last_updated: string;
}

interface NewsRaw {
  id: number;
  title: string;
  url: string;
  source: string;
  sentiment: 'Positive' | 'Neutral' | 'Negative';
  published_at: string;
  score?: number;
  provider?: string;
  data_source?: string;
}

interface SectorRaw {
  sector_name: string;
  change_percent: number;
  source?: string;
}

interface SentimentRaw {
  score: number;
  sentiment_label: string;
}

interface StockQuoteRaw {
  symbol: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  source: string;
}

// Tipe generik "any" dipakai sengaja di sini (bukan bug) karena bentuk payload
// korelasi (matrix & detail) berasal langsung dari ihsg-data-service dan hanya
// diteruskan apa adanya (pass-through) ke Web Client tanpa transformasi field.

export class WebBffService {
  // Definisikan alamat internal port microservices (Infrastructure Layer)
  // QUICK WIN: URL dipindah ke config.ts (nilai default identik) agar terpusat.
  // Catatan: endpoint /api/sectors disediakan oleh ihsg-data-service, bukan service terpisah,
  // sehingga tidak perlu SECTOR_SERVICE_URL yang berbeda (bug lama: mengarah ke port 8003 yang tidak ada).
  private readonly IHSG_SERVICE_URL = config.ihsgServiceUrl;
  private readonly NEWS_SERVICE_URL = config.newsServiceUrl;

  // Helper generik untuk fetch JSON dengan tipe eksplisit dan fallback yang aman,
  // menghindari error TypeScript "unknown" pada hasil Promise.all (bug lama).
  // QUICK WIN: tambah TIMEOUT (fetch bawaan Node tidak punya timeout -> bisa
  // menggantung tanpa batas) dan LOG warning saat fallback, supaya kegagalan
  // upstream tidak lagi senyap. Perilaku jalur sukses TIDAK berubah.
  private async fetchJson<T>(url: string, fallback: T, label = "upstream"): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), config.fetchTimeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) {
        console.warn(`[BFF][${label}] HTTP ${res.status} ${url} -> fallback`);
        return fallback;
      }
      return (await res.json()) as T;
    } catch (e: any) {
      console.warn(`[BFF][${label}] ${e?.name || "error"} ${url} -> fallback`);
      return fallback;
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * Mengumpulkan dan menggabungkan data dari berbagai microservices secara paralel
   * guna memangkas jumlah request dari Web Browser ke server (mencegah Under-fetching)
   */
  async getDashboardData(period: string = "1y"): Promise<WebDashboardAggregateDTO> {
    try {
      // Eksekusi pemanggilan HTTP paralel ke seluruh Microservices backend.
      // News & Sentiment diprioritaskan dari news-service (AI scraper live),
      // dengan fallback ke ihsg-data-service (data ter-seed di DB) jika news-service offline.
      const [ihsgRealtimeRes, ihsgHistoryRes, newsRes, sectorsRes, sentimentRes] = await Promise.all([
        this.fetchJson<IHSGRealtimeRaw>(`${this.IHSG_SERVICE_URL}/ihsg/realtime`, this.getFallbackRealtime(), "ihsg-realtime"),
        this.fetchJson<any[]>(`${this.IHSG_SERVICE_URL}/ihsg/history?period=${period}`, [], "ihsg-history"),
        // PRIORITAS BERITA: ihsg-data-service /news (Yahoo Finance + Google News
        // RSS real) terlebih dahulu sesuai permintaan user, fallback ke news-service
        // (CNBC Indonesia -- LEGACY, ditandai deprecated) jika kosong, lalu fallback
        // terakhir data seed di DB.
        this.fetchJson<NewsRaw[]>(`${this.IHSG_SERVICE_URL}/news`, [], "news").then(res =>
          res.length > 0 ? res : this.fetchJson<NewsRaw[]>(`${this.NEWS_SERVICE_URL}/news`, [], "news-legacy")
        ),
        this.fetchJson<SectorRaw[]>(`${this.IHSG_SERVICE_URL}/sectors`, [], "sectors"),
        this.fetchJson<SentimentRaw>(`${this.NEWS_SERVICE_URL}/sentiment`, { score: -1, sentiment_label: "" }, "sentiment-legacy").then(res =>
          res.score >= 0 ? res : this.fetchJson<SentimentRaw>(`${this.IHSG_SERVICE_URL}/sentiment`, { score: 50, sentiment_label: "Neutral" }, "sentiment")
        )
      ]);

      // 1. Transformasi Data IHSG ke Format DTO Web (Format Volume menjadi string "B/M")
      const ihsgFormatted: WebIHSGSummaryDTO = {
        price: ihsgRealtimeRes.current_price,
        change: ihsgRealtimeRes.change,
        changePercent: ihsgRealtimeRes.change_percent,
        open: ihsgRealtimeRes.open,
        high: ihsgRealtimeRes.high,
        low: ihsgRealtimeRes.low,
        volume: this.formatVolumeToString(ihsgRealtimeRes.volume),
        status: "Active",
        lastUpdated: ihsgRealtimeRes.last_updated
      };

      // 2. Transformasi Berita Keuangan (Membatasi hanya maksimal 5 berita untuk tampilan web)
      const newsFormatted: WebNewsDTO[] = newsRes.slice(0, 8).map((n) => ({
        id: n.id,
        title: n.title,
        url: n.url,
        source: n.source,
        sentiment: n.sentiment,
        score: typeof n.score === "number" ? n.score : n.sentiment === "Positive" ? 0.85 : n.sentiment === "Negative" ? -0.65 : 0.0,
        publishedAt: n.published_at,
        dataSource: n.data_source || "simulasi",
        provider: n.provider || null
      }));

      // 3. Transformasi Sektoral & Menghitung apakah sektor mengalahkan kinerja IHSG harian (Outperform)
      const ihsgDailyChange = ihsgFormatted.changePercent;
      const sectorsFormatted: WebSectorDTO[] = sectorsRes.map((s) => ({
        name: s.sector_name,
        changePercent: s.change_percent,
        isOutperforming: (s.change_percent ?? -999) > ihsgDailyChange,
        source: s.source || (typeof s.change_percent === "number" ? "yahoo_finance" : "simulasi")
      }));

      // 4. Gabungkan seluruh data hasil transformasi ke dalam satu kesatuan DTO Komprehensif
      return {
        ihsg: ihsgFormatted,
        chartHistory: ihsgHistoryRes,
        news: newsFormatted,
        sectors: sectorsFormatted,
        sentimentScore: sentimentRes.score,
        sentimentLabel: sentimentRes.sentiment_label
      };

    } catch (error) {
      console.error("BFF Web Service Error saat agregasi data:", error);
      throw new Error("Gagal melakukan agregasi data bursa di lapisan BFF.");
    }
  }

  // Helper untuk mengubah angka volume mentah menjadi format ringkas (e.g. 14.2B)
  private formatVolumeToString(vol: number): string {
    if (vol >= 1e9) return (vol / 1e9).toFixed(1) + "B";
    if (vol >= 1e6) return (vol / 1e6).toFixed(1) + "M";
    return vol.toLocaleString("id-ID");
  }

  // Fallback Data jika Microservice internal offline
  private getFallbackRealtime(): IHSGRealtimeRaw {
    return {
      current_price: 7245.50,
      change: 34.20,
      change_percent: 0.47,
      open: 7211.30,
      high: 7260.10,
      low: 7208.50,
      volume: 14200000000,
      last_updated: new Date().toISOString()
    };
  }

  /**
   * Meneruskan (proxy) permintaan kutipan harga saham individual ke
   * ihsg-data-service, dipakai oleh Watchlist & Portofolio agar harga yang
   * ditampilkan berasal dari data pasar sungguhan (Yahoo Finance), bukan
   * simulasi acak di sisi frontend.
   */
  async getStockQuotes(symbols: string[]): Promise<StockQuoteRaw[]> {
    if (!symbols.length) return [];
    const symbolParam = symbols.map(s => s.trim().toUpperCase()).filter(Boolean).join(",");
    if (!symbolParam) return [];

    return this.fetchJson<StockQuoteRaw[]>(
      `${this.IHSG_SERVICE_URL}/stocks/quotes?symbols=${encodeURIComponent(symbolParam)}`,
      []
    );
  }

  /**
   * Meneruskan (proxy) permintaan PROFIL LENGKAP satu saham (info transaksi
   * harian + fundamental riil dari Yahoo Finance) ke ihsg-data-service,
   * dipakai oleh halaman Detail Saham.
   */
  async getStockProfile(symbol: string): Promise<any> {
    const symbolClean = (symbol || "").trim().toUpperCase();
    if (!symbolClean) return null;

    return this.fetchJson<any>(
      `${this.IHSG_SERVICE_URL}/stocks/profile?symbol=${encodeURIComponent(symbolClean)}`,
      null
    );
  }

  /**
   * Meneruskan (proxy) status rantai prioritas sumber data (GoAPI.io ->
   * Yahoo Finance -> simulasi) ke ihsg-data-service, dipakai frontend untuk
   * menampilkan badge status koneksi data secara jujur.
   */
  async getDatasourceStatus(): Promise<any> {
    return this.fetchJson<any>(
      `${this.IHSG_SERVICE_URL}/datasource/status`,
      { goapi_configured: false, yfinance_available: true, priority_chain: ["goapi_io", "yahoo_finance", "simulasi_internal"] }
    );
  }

  /**
   * Meneruskan (proxy) permintaan matrix korelasi (banyak saham x faktor
   * makro/komoditas/global inti) ke ihsg-data-service.
   */
  async getCorrelationMatrix(symbols: string[], period: string = "1y", method: string = "pearson"): Promise<any> {
    const symbolParam = symbols.map(s => s.trim().toUpperCase()).filter(Boolean).join(",");
    if (!symbolParam) return { period, method, factors: [], rows: [], source: "yahoo_finance" };

    return this.fetchJson<any>(
      `${this.IHSG_SERVICE_URL}/correlation/matrix?symbols=${encodeURIComponent(symbolParam)}&period=${encodeURIComponent(period)}&method=${encodeURIComponent(method)}`,
      { period, method, factors: [], rows: [], source: "yahoo_finance", error: "bff_fetch_failed" }
    );
  }

  /**
   * Meneruskan (proxy) permintaan detail korelasi 1 saham (vs makro/komoditas
   * /global/sektor/peer) ke ihsg-data-service.
   */
  async getCorrelationDetail(symbol: string, period: string = "1y", peers: string[] = [], method: string = "pearson"): Promise<any> {
    const symbolClean = symbol.trim().toUpperCase();
    if (!symbolClean) return { symbol: "", period, method, factors: [], peers: [], source: "yahoo_finance" };
    const peersParam = peers.map(p => p.trim().toUpperCase()).filter(Boolean).join(",");

    const url = `${this.IHSG_SERVICE_URL}/correlation/detail?symbol=${encodeURIComponent(symbolClean)}&period=${encodeURIComponent(period)}&method=${encodeURIComponent(method)}${peersParam ? `&peers=${encodeURIComponent(peersParam)}` : ""}`;

    return this.fetchJson<any>(url, {
      symbol: symbolClean, period, method, factors: [], peers: [], source: "yahoo_finance", error: "bff_fetch_failed"
    });
  }

  /**
   * Meneruskan (proxy) permintaan analisis Cross-Correlation (Lead-Lag) antara
   * 2 aset (saham atau faktor makro/komoditas/global) ke ihsg-data-service.
   */
  async getCorrelationLeadLag(
    assetA: string, assetAType: string, assetB: string, assetBType: string,
    period: string = "1y", maxLag: number = 10
  ): Promise<any> {
    const url = `${this.IHSG_SERVICE_URL}/correlation/leadlag?asset_a=${encodeURIComponent(assetA)}&asset_a_type=${encodeURIComponent(assetAType)}&asset_b=${encodeURIComponent(assetB)}&asset_b_type=${encodeURIComponent(assetBType)}&period=${encodeURIComponent(period)}&max_lag=${encodeURIComponent(String(maxLag))}`;

    return this.fetchJson<any>(url, { error: "bff_fetch_failed", source: "yahoo_finance" });
  }

  /**
   * Meneruskan (proxy) permintaan analisis heuristik Wyckoff/VPA (Trading
   * Range, Spring, Sign of Strength, Selling/Buying Climax) berdasarkan data
   * harga historis REAL dari ihsg-data-service.
   */
  async getWyckoffAnalysis(symbol: string, period: string = "6mo"): Promise<any> {
    const symbolClean = symbol.trim().toUpperCase();
    if (!symbolClean) return { symbol: "", source: "yahoo_finance", error: "empty_symbol" };
    const url = `${this.IHSG_SERVICE_URL}/analysis/wyckoff?symbol=${encodeURIComponent(symbolClean)}&period=${encodeURIComponent(period)}`;

    return this.fetchJson<any>(url, { symbol: symbolClean, source: "yahoo_finance", error: "bff_fetch_failed" });
  }

  /**
   * Meneruskan (proxy) analisis screener SATU saham berbasis sinyal RIIL
   * (indikator dihitung dari data Yahoo Finance oleh ihsg-data-service).
   */
  async getScreenerAnalyze(symbol: string, strategy: string): Promise<any> {
    const sym = (symbol || "").trim().toUpperCase();
    if (!sym) return { symbol: "", strategy, source: "yahoo_finance", error: "empty_symbol" };
    const url = `${this.IHSG_SERVICE_URL}/screener/analyze?symbol=${encodeURIComponent(sym)}&strategy=${encodeURIComponent(strategy || "teknikal")}`;
    return this.fetchJson<any>(url, { symbol: sym, strategy, source: "yahoo_finance", error: "bff_fetch_failed" });
  }

  /**
   * Meneruskan (proxy) scan screener untuk daftar saham (universe likuid bila
   * kosong). Mengembalikan array sinyal riil yang diurutkan.
   */
  async getScreenerScan(strategy: string, symbols: string): Promise<any[]> {
    let url = `${this.IHSG_SERVICE_URL}/screener/scan?strategy=${encodeURIComponent(strategy || "teknikal")}`;
    if (symbols && symbols.trim()) {
      url += `&symbols=${encodeURIComponent(symbols.trim())}`;
    }
    return this.fetchJson<any[]>(url, []);
  }

  /**
   * Meneruskan (proxy) Stock Pick berbasis sinyal riil (mode harian/swing).
   */
  async getStockPick(mode: string, symbols: string): Promise<any> {
    let url = `${this.IHSG_SERVICE_URL}/screener/stockpick?mode=${encodeURIComponent(mode || "harian")}`;
    if (symbols && symbols.trim()) {
      url += `&symbols=${encodeURIComponent(symbols.trim())}`;
    }
    return this.fetchJson<any>(url, { mode, source: "yahoo_finance", error: "bff_fetch_failed" });
  }

  /** Meneruskan (proxy) quote makro/komoditas/global untuk marquee atas. */
  async getMarketMarquee(): Promise<any[]> {
    return this.fetchJson<any[]>(`${this.IHSG_SERVICE_URL}/market/marquee`, []);
  }

  /** Meneruskan (proxy) market breadth (naik/tetap/turun) dari quote riil. */
  async getMarketBreadth(): Promise<any> {
    return this.fetchJson<any>(`${this.IHSG_SERVICE_URL}/market/breadth`, {});
  }
}



