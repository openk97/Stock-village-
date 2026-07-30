import { WebDashboardAggregateDTO, WebIHSGSummaryDTO, WebNewsDTO, WebSectorDTO } from "./web.dto";

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
}

interface SectorRaw {
  sector_name: string;
  change_percent: number;
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

export class WebBffService {
  // Definisikan alamat internal port microservices (Infrastructure Layer)
  // Catatan: endpoint /api/sectors disediakan oleh ihsg-data-service, bukan service terpisah,
  // sehingga tidak perlu SECTOR_SERVICE_URL yang berbeda (bug lama: mengarah ke port 8003 yang tidak ada).
  private readonly IHSG_SERVICE_URL = process.env.IHSG_SERVICE_URL || "http://localhost:8000/api";
  private readonly NEWS_SERVICE_URL = process.env.NEWS_SERVICE_URL || "http://localhost:8002/api";

  // Helper generik untuk fetch JSON dengan tipe eksplisit dan fallback yang aman,
  // menghindari error TypeScript "unknown" pada hasil Promise.all (bug lama).
  private async fetchJson<T>(url: string, fallback: T): Promise<T> {
    try {
      const res = await fetch(url);
      if (!res.ok) return fallback;
      return (await res.json()) as T;
    } catch {
      return fallback;
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
        this.fetchJson<IHSGRealtimeRaw>(`${this.IHSG_SERVICE_URL}/ihsg/realtime`, this.getFallbackRealtime()),
        this.fetchJson<any[]>(`${this.IHSG_SERVICE_URL}/ihsg/history?period=${period}`, []),
        this.fetchJson<NewsRaw[]>(`${this.NEWS_SERVICE_URL}/news`, []).then(res =>
          res.length > 0 ? res : this.fetchJson<NewsRaw[]>(`${this.IHSG_SERVICE_URL}/news`, [])
        ),
        this.fetchJson<SectorRaw[]>(`${this.IHSG_SERVICE_URL}/sectors`, []),
        this.fetchJson<SentimentRaw>(`${this.NEWS_SERVICE_URL}/sentiment`, { score: -1, sentiment_label: "" }).then(res =>
          res.score >= 0 ? res : this.fetchJson<SentimentRaw>(`${this.IHSG_SERVICE_URL}/sentiment`, { score: 50, sentiment_label: "Neutral" })
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
      const newsFormatted: WebNewsDTO[] = newsRes.slice(0, 5).map((n) => ({
        id: n.id,
        title: n.title,
        url: n.url,
        source: n.source,
        sentiment: n.sentiment,
        publishedAt: n.published_at
      }));

      // 3. Transformasi Sektoral & Menghitung apakah sektor mengalahkan kinerja IHSG harian (Outperform)
      const ihsgDailyChange = ihsgFormatted.changePercent;
      const sectorsFormatted: WebSectorDTO[] = sectorsRes.map((s) => ({
        name: s.sector_name,
        changePercent: s.change_percent,
        isOutperforming: s.change_percent > ihsgDailyChange
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
}
