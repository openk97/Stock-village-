import { Router } from 'express';
import { WebBffController } from './web.controller';

const router = Router();
const controller = new WebBffController();

// Mengarahkan lalu lintas GET /api/web/dashboard ke controller aggregator BFF
router.get('/dashboard', controller.getWebDashboard);

// Mengarahkan lalu lintas GET /api/web/stocks/quotes ke controller kutipan harga saham
router.get('/stocks/quotes', controller.getStockQuotes);

// Mengarahkan lalu lintas GET /api/web/correlation/matrix & /detail ke controller korelasi
router.get('/correlation/matrix', controller.getCorrelationMatrix);
router.get('/correlation/detail', controller.getCorrelationDetail);
router.get('/correlation/leadlag', controller.getCorrelationLeadLag);

// Mengarahkan lalu lintas GET /api/web/analysis/wyckoff ke controller analisis Wyckoff/VPA
router.get('/analysis/wyckoff', controller.getWyckoffAnalysis);

export default router;
export const WebBffRouter = router;



