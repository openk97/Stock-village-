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
}
