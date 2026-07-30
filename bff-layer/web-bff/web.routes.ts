import { Router } from 'express';
import { WebBffController } from './web.controller';

const router = Router();
const controller = new WebBffController();

// Mengarahkan lalu lintas GET /api/web/dashboard ke controller aggregator BFF
router.get('/dashboard', controller.getWebDashboard);

export default router;
export const WebBffRouter = router;
