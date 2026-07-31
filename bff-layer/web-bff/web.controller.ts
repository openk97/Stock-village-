import { Request, Response } from 'express';
import { WebBffService } from './web.service';

export class WebBffController {
  private bffService = new WebBffService();

  /**
   * Menangani request Dashboard Utama dari Web Client
   * Mengembalikan payload agregasi komprehensif tunggal
   */
  getWebDashboard = async (req: Request, res: Response): Promise<void> => {
    try {
      // Dapatkan query parameter 'period' untuk filter jangka waktu chart (default: '1y')
      const period = (req.query.period as string) || "1y";
      
      // Ambil data agregasi dari service BFF
      const dashboardData = await this.bffService.getDashboardData(period);
      
      // Kembalikan response sukses 200 dengan payload DTO yang bersih
      res.status(200).json({
        success: true,
        message: "Data agregasi bursa IHSG untuk Web Client berhasil dikompilasi.",
        data: dashboardData
      });
    } catch (error: any) {
      console.error("Controller Error in getWebDashboard:", error);
      res.status(500).json({
        success: false,
        message: "Terjadi kesalahan internal di lapisan BFF saat memproses request web.",
        error: error.message
      });
    }
  };

  /**
   * Menangani request kutipan harga saham individual (untuk Watchlist &
   * Portofolio) dari Web Client. Menerima query param "symbols" dipisah koma,
   * contoh: /api/web/stocks/quotes?symbols=BBCA,BBRI,TLKM
   */
  getStockQuotes = async (req: Request, res: Response): Promise<void> => {
    try {
      const symbolsParam = (req.query.symbols as string) || "";
      const symbols = symbolsParam.split(",").map(s => s.trim()).filter(Boolean);

      if (symbols.length === 0) {
        res.status(400).json({
          success: false,
          message: "Parameter 'symbols' wajib diisi, contoh: ?symbols=BBCA,BBRI"
        });
        return;
      }

      const quotes = await this.bffService.getStockQuotes(symbols);

      res.status(200).json({
        success: true,
        message: "Kutipan harga saham berhasil diambil.",
        data: quotes
      });
    } catch (error: any) {
      console.error("Controller Error in getStockQuotes:", error);
      res.status(500).json({
        success: false,
        message: "Terjadi kesalahan internal saat mengambil kutipan harga saham.",
        error: error.message
      });
    }
  };

  /**
   * Menangani request matrix korelasi (banyak saham x faktor makro/komoditas
   * /global inti) dari Web Client.
   * Contoh: /api/web/correlation/matrix?symbols=BBCA,BBRI,TLKM&period=6mo
   */
  getCorrelationMatrix = async (req: Request, res: Response): Promise<void> => {
    try {
      const symbolsParam = (req.query.symbols as string) || "";
      const symbols = symbolsParam.split(",").map(s => s.trim()).filter(Boolean);
      const period = (req.query.period as string) || "1y";

      if (symbols.length === 0) {
        res.status(400).json({
          success: false,
          message: "Parameter 'symbols' wajib diisi, contoh: ?symbols=BBCA,BBRI"
        });
        return;
      }

      const matrix = await this.bffService.getCorrelationMatrix(symbols, period);

      res.status(200).json({
        success: true,
        message: "Matrix korelasi berhasil dihitung.",
        data: matrix
      });
    } catch (error: any) {
      console.error("Controller Error in getCorrelationMatrix:", error);
      res.status(500).json({
        success: false,
        message: "Terjadi kesalahan internal saat menghitung matrix korelasi.",
        error: error.message
      });
    }
  };

  /**
   * Menangani request detail korelasi 1 saham (vs makro/komoditas/global/
   * sektor/peer) dari Web Client.
   * Contoh: /api/web/correlation/detail?symbol=BBCA&period=6mo&peers=BBRI,BMRI
   */
  getCorrelationDetail = async (req: Request, res: Response): Promise<void> => {
    try {
      const symbol = (req.query.symbol as string) || "";
      const period = (req.query.period as string) || "1y";
      const peersParam = (req.query.peers as string) || "";
      const peers = peersParam.split(",").map(s => s.trim()).filter(Boolean);

      if (!symbol.trim()) {
        res.status(400).json({
          success: false,
          message: "Parameter 'symbol' wajib diisi, contoh: ?symbol=BBCA"
        });
        return;
      }

      const detail = await this.bffService.getCorrelationDetail(symbol, period, peers);

      res.status(200).json({
        success: true,
        message: "Detail korelasi berhasil dihitung.",
        data: detail
      });
    } catch (error: any) {
      console.error("Controller Error in getCorrelationDetail:", error);
      res.status(500).json({
        success: false,
        message: "Terjadi kesalahan internal saat menghitung detail korelasi.",
        error: error.message
      });
    }
  };
}

