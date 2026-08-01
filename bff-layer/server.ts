import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import zlib from 'zlib';
import { WebBffRouter } from './web-bff/web.routes';
import { bffLoggingMiddleware } from './shared/bff.middleware';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware global
app.use(cors());
app.use(express.json());
app.use(bffLoggingMiddleware);

// PERF: kompresi gzip untuk respons JSON (zero-dependency, zlib bawaan Node).
// Respons >=1KB dikompres bila klien mendukung gzip -> hemat bandwidth hingga
// ~80% untuk jutaan klien mobile. Konten kecil dibiarkan polos (gzip overhead
// tidak sepadan).
app.use((req, res, next) => {
  const accepts = (req.headers['accept-encoding'] || '').toString();
  res.locals.supportsGzip = accepts.includes('gzip');
  const origJson = res.json.bind(res);
  res.json = (body: unknown) => {
    const payload = Buffer.from(JSON.stringify(body));
    if (res.locals.supportsGzip && payload.length > 1024) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Content-Encoding', 'gzip');
      res.setHeader('Vary', 'Accept-Encoding');
      const gz = zlib.gzipSync(payload);
      res.setHeader('Content-Length', String(gz.length));
      return res.end(gz);
    }
    return origJson(body);
  };
  next();
});

// Health check endpoint
app.get('/health', (_req, res) => {
  res.status(200).json({ status: 'ok', service: 'web-bff' });
});

// Routing utama Web BFF (prefix /api/web sesuai Nginx Gateway)
app.use('/api/web', WebBffRouter);

app.listen(PORT, () => {
  console.log(`[Web BFF] Server berjalan pada port ${PORT}`);
});
