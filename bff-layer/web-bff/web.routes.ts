import { Router } from 'express';
import { WebBffController } from './web.controller';

const router = Router();
const controller = new WebBffController();

// Mengarahkan lalu lintas GET /api/web/dashboard ke controller aggregator BFF
router.get('/dashboard', controller.getWebDashboard);

// Realtime IHSG ringan (polling 30s frontend -- pengganti fetch dashboard penuh)
router.get('/ihsg/realtime', controller.getIhsgRealtime);

// Mengarahkan lalu lintas GET /api/web/stocks/quotes ke controller kutipan harga saham
router.get('/stocks/quotes', controller.getStockQuotes);

// Mengarahkan lalu lintas GET /api/web/stocks/profile ke controller profil lengkap saham
router.get('/stocks/profile', controller.getStockProfile);

// Mengarahkan lalu lintas GET /api/web/datasource/status ke controller status sumber data
router.get('/datasource/status', controller.getDatasourceStatus);

// Mengarahkan lalu lintas GET /api/web/correlation/matrix & /detail ke controller korelasi
router.get('/correlation/matrix', controller.getCorrelationMatrix);
router.get('/correlation/detail', controller.getCorrelationDetail);
router.get('/correlation/leadlag', controller.getCorrelationLeadLag);

// Mengarahkan lalu lintas GET /api/web/analysis/wyckoff ke controller analisis Wyckoff/VPA
router.get('/analysis/wyckoff', controller.getWyckoffAnalysis);

// Mengarahkan lalu lintas GET /api/web/screener/* ke controller screener sinyal riil
router.get('/screener/analyze', controller.getScreenerAnalyze);
router.get('/screener/scan', controller.getScreenerScan);
router.get('/screener/stockpick', controller.getStockPick);

// Mengarahkan lalu lintas GET /api/web/market/* ke controller data pasar (marquee & breadth)
router.get('/market/marquee', controller.getMarketMarquee);
router.get('/market/breadth', controller.getMarketBreadth);

export default router;
export const WebBffRouter = router;



