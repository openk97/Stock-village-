import { Request, Response, NextFunction } from 'express';

/**
 * Middleware untuk mencatat waktu respons pelayanan request (Logging Middleware)
 */
export function bffLoggingMiddleware(req: Request, res: Response, next: NextFunction) {
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    console.log(`[BFF LOG] ${req.method} ${req.originalUrl} - ${res.statusCode} (${duration}ms)`);
  });
  next();
}
