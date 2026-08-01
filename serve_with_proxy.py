#!/usr/bin/env python3
"""
serve_with_proxy.py — Server statis untuk frontend/ yang meneruskan /api/*
ke BFF (port 3000 default). Dipakai oleh start_all.sh supaya aplikasi bisa
dibuka dari browser/HP dengan data LIVE (bukan mode demo).

PERF:
- gzip untuk aset statis (html/css/js) & JSON API bila klien mendukungnya
  (hemat ~75% bandwidth -- app.js 460KB -> ~120KB).
- Cache-Control: aset yang jarang berubah (lib.js/app.js/styles.css) di-cache
  browser; index.html no-cache agar pembaruan langsung terlihat.

Contoh:  python3 serve_with_proxy.py --port 8080 --bff http://localhost:3000
"""
import argparse
import gzip
import http.server
import os
import socketserver
import sys
import urllib.request

FRONTEND_DIR = None   # diisi dari argumen
BFF_BASE = None

# Ekstensi yang aman untuk cache browser (berubah jarang)
LONG_CACHE_EXTS = {".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".woff2"}
COMPRESSIBLE_EXTS = {".html", ".css", ".js", ".json", ".svg", ".txt"}


def _compress(body: bytes, accept: str) -> tuple:
    """Kembalikan (body, encoding) — gzip bila klien mendukung & ukuran layak."""
    if "gzip" in accept and len(body) > 1024:
        gz = gzip.compress(body, 6)
        if len(gz) < len(body):
            return gz, "gzip"
    return body, None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            url = BFF_BASE + self.path
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    body = resp.read()
                    accept = self.headers.get("Accept-Encoding", "")
                    body, enc = _compress(body, accept)
                    self.send_response(resp.status)
                    self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                    self.send_header("Content-Length", str(len(body)))
                    if enc:
                        self.send_header("Content-Encoding", enc)
                        self.send_header("Vary", "Accept-Encoding")
                    self.send_header("Cache-Control", "no-cache")  # data live
                    self.end_headers()
                    self.wfile.write(body)
            except Exception as e:
                self.send_response(502)
                body = ('{"error":"proxy error: %s"}' % str(e)).encode()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        # File statis dari frontend/
        return super().do_GET()

    def send_head(self):
        # Override untuk menambah gzip + cache headers pada file statis
        path = self.translate_path(self.path)
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            accept = self.headers.get("Accept-Encoding", "")
            # sw.js TIDAK dikompres: engine service worker menangani script SW yang
            # ter-gzip secara inkonsisten (bisa menyebabkan registrasi menggantung).
            skip_compress = os.path.basename(path) == "sw.js"
            if ext in COMPRESSIBLE_EXTS and not skip_compress:
                try:
                    with open(path, "rb") as f:
                        body = f.read()
                    body, enc = _compress(body, accept)
                    ctype = self.guess_type(path)
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    if enc:
                        self.send_header("Content-Encoding", enc)
                        self.send_header("Vary", "Accept-Encoding")
                    if ext in LONG_CACHE_EXTS:
                        self.send_header("Cache-Control", "public, max-age=3600")
                    else:
                        self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    return _BytesReader(body)
                except OSError:
                    pass
        return super().send_head()

    def log_message(self, fmt, *args):
        sys.stderr.write("[frontend] " + fmt % args + "\n")


class _BytesReader:
    """Pembungkus byte agar bisa dikonsumsi SimpleHTTPRequestHandler."""

    def __init__(self, data):
        self._data = data
        self._pos = 0

    def read(self, n=-1):
        if n < 0 or n > len(self._data) - self._pos:
            n = len(self._data) - self._pos
        out = self._data[self._pos:self._pos + n]
        self._pos += n
        return out

    def close(self):
        pass


def main():
    global FRONTEND_DIR, BFF_BASE
    parser = argparse.ArgumentParser(description="Static server + /api proxy untuk frontend Stock Village")
    parser.add_argument("--port", type=int, default=8080, help="Port frontend (default 8080)")
    parser.add_argument("--bff", default="http://localhost:3000", help="Base URL BFF (default http://localhost:3000)")
    parser.add_argument("--dir", default=None, help="Direktori frontend (default: folder ini + /frontend)")
    args = parser.parse_args()

    import os
    if args.dir:
        FRONTEND_DIR = args.dir
    else:
        FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
    BFF_BASE = args.bff.rstrip("/")

    if not os.path.isdir(FRONTEND_DIR):
        sys.exit(f"Folder frontend tidak ditemukan: {FRONTEND_DIR}")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", args.port), Handler) as httpd:
        print(f"Frontend  : {FRONTEND_DIR}")
        print(f"Proxy /api -> {BFF_BASE}")
        print(f"Listening : http://0.0.0.0:{args.port}  (Ctrl+C untuk berhenti)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
