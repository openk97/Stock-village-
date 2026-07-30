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

/**
 * Middleware untuk memvalidasi Token Akses (Authentication Middleware)
 * Melindungi rute sensitif seperti penyimpanan portfolio saham pribadi
 */
export function bffAuthMiddleware(req: Request, res: Response, next: NextFunction) {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({
      success: false,
      message: "Akses ditolak. Token otentikasi Bearer JWT tidak ditemukan."
    });
  }

  const token = authHeader.split(' ')[1];

  try {
    // Di sini biasanya dilakukan verifikasi token JWT asli dengan kunci rahasia
    // const decoded = jwt.verify(token, process.env.JWT_SECRET);
    // req.user = decoded;
    
    // Simulasi verifikasi sukses untuk keperluan testing/pembangunan
    if (token === "valid-token-ihsg-insight") {
      next();
    } else {
      throw new Error("Token tidak terdaftar.");
    }
  } catch (error) {
    return res.status(403).json({
      success: false,
      message: "Akses ditolak. Token kadaluwarsa atau tidak valid."
    });
  }
}
