/**
 * config.ts — Konfigurasi terpusat lapisan BFF.
 * QUICK WIN (refactor aman): URL service & timeout yang sebelumnya hardcode
 * di web.service.ts dipindah ke sini. Nilai default IDENTIK, sehingga tidak
 * mengubah perilaku; semua bisa di-override lewat environment variable.
 */
export const config = {
  // URL internal microservices (Infrastructure Layer)
  // news-service (8002) sudah dihapus -- berita & sentimen dari ihsg-data-service.
  ihsgServiceUrl: process.env.IHSG_SERVICE_URL || "http://localhost:8000/api",

  // Batas waktu (ms) untuk setiap request upstream. fetch bawaan Node TIDAK
  // punya timeout default -- tanpa ini, request bisa menggantung tanpa batas
  // saat upstream lambat/down.
  fetchTimeoutMs: Number(process.env.BFF_FETCH_TIMEOUT_MS || 8000),

  // Port BFF (dibaca server.ts)
  port: Number(process.env.BFF_PORT || 3000),
};
