import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { WebBffRouter } from './web-bff/web.routes';
import { bffLoggingMiddleware } from './shared/bff.middleware';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware global
app.use(cors());
app.use(express.json());
app.use(bffLoggingMiddleware);

// Health check endpoint
app.get('/health', (_req, res) => {
  res.status(200).json({ status: 'ok', service: 'web-bff' });
});

// Routing utama Web BFF (prefix /api/web sesuai Nginx Gateway)
app.use('/api/web', WebBffRouter);

app.listen(PORT, () => {
  console.log(`[Web BFF] Server berjalan pada port ${PORT}`);
});
