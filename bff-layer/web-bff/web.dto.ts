// Data Transfer Object (DTO) khusus untuk Web Client
// BFF membatasi dan menata format agar pas dengan kebutuhan visual Next.js / Web Dashboard

export interface WebIHSGSummaryDTO {
  price: number;
  change: number;
  changePercent: number;
  open: number;
  high: number;
  low: number;
  volume: string; // Volume dikonversi ke format string ringkas (e.g. "14.2B") khusus untuk Web
  status: string; // Status bursa (e.g., "Active", "Closed")
  lastUpdated: string;
}

export interface WebNewsDTO {
  id: number;
  title: string;
  url: string;
  source: string;
  sentiment: 'Positive' | 'Neutral' | 'Negative';
  publishedAt: string;
  score?: number;
  dataSource?: string; // "yahoo_google_news" = real RSS, "simulasi" = seed demo
  provider?: string | null;
}

export interface WebSectorDTO {
  name: string;
  changePercent: number;
  isOutperforming: boolean; // Dihitung di BFF jika performa sektor > performa IHSG harian
  source?: string; // "yahoo_finance" (riil) | "simulasi" (seed demo)
}

// Representasi agregasi halaman utama (Home Dashboard) khusus Web
// Gabungan data ini mencegah Client melakukan multi-fetching (under-fetching issue)
export interface WebDashboardAggregateDTO {
  ihsg: WebIHSGSummaryDTO;
  chartHistory: any[];
  news: WebNewsDTO[];
  sectors: WebSectorDTO[];
  sentimentScore: number;
  sentimentLabel: string;
}
