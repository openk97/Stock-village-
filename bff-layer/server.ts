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
app.use(cors({ origin: process.env.CORS_ORIGIN ? process.env.CORS_ORIGIN.split(',') : '*' }));
app.use(express.json({ limit: '1mb' }));
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

// Health check sederhana (liveness)
app.get('/health', (_req, res) => {
  res.status(200).json({ status: 'ok', service: 'web-bff' });
});

// Readiness agregat: ping tiap upstream dengan timeout singkat.
// Dipakai orchestrator/nginx; gagal 1 dependency -> 503 (orchestrator
// menarik traffic hingga pulih).
app.get('/healthz', async (_req, res) => {
  const deps: Record<string, string> = {};
  const timeout = 3000; // ms
  const probe = async (name: string, url: string) => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeout);
    try {
      const r = await fetch(url, { signal: ctrl.signal });
      deps[name] = r.ok ? 'ok' : `http_${r.status}`;
    } catch (e: any) {
      deps[name] = `error:${e?.name || 'fetch'}`;
    } finally {
      clearTimeout(t);
    }
  };
  const ihsgUrl = process.env.IHSG_SERVICE_URL || 'http://localhost:8000/api';
  await Promise.all([
    probe('ihsg-data-service', `${ihsgUrl.replace(/\/api$/, '')}/healthz`),
  ]);
  const ready = Object.values(deps).every(v => v === 'ok');
  res.status(ready ? 200 : 503).json({ status: ready ? 'ok' : 'degraded', deps });
});

// Routing utama Web BFF (prefix /api/web sesuai Nginx Gateway)
app.use('/api/web', WebBffRouter);

app.listen(PORT, () => {
  console.log(`[Web BFF] Server berjalan pada port ${PORT}`);
});
