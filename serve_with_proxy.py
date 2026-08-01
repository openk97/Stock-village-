#!/usr/bin/env python3
"""
serve_with_proxy.py — Server statis untuk frontend/ yang meneruskan /api/*
ke BFF (port 3000 default). Dipakai oleh start_all.sh supaya aplikasi bisa
dibuka dari browser/HP dengan data LIVE (bukan mode demo).

Contoh:  python3 serve_with_proxy.py --port 8080 --bff http://localhost:3000
"""
import argparse
import http.server
import socketserver
import sys
import urllib.request

FRONTEND_DIR = None   # diisi dari argumen
BFF_BASE = None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            url = BFF_BASE + self.path
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    body = resp.read()
                    self.send_response(resp.status)
                    self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                    self.send_header("Content-Length", str(len(body)))
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
        # Semua request lain dilayani sebagai file statis dari frontend/
        return super().do_GET()

    def log_message(self, fmt, *args):
        sys.stderr.write("[frontend] " + fmt % args + "\n")


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
