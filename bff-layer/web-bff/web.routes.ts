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

export default router;
export const WebBffRouter = router;

