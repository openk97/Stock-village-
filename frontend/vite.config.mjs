/**
 * vite.config.js — Build frontend Stock Village.
 *
 * Tech-lead decision (D2): Vite dulu TANPA rewrite — bundling + minify +
 * asset hashing untuk file yang sudah ada (index.html + css + js klasik).
 * - base './' -> path relatif, hasil bisa di-serve dari subpath/CDN.
 * - build.outDir 'dist' -> output bersih.
 * - Script klasik (<script src="js/*.js">) TIDAK di-bundle (butuh type=module,
 *   berisiko mengubah scope global lib.js) — plugin di bawah menyalin folder
 *   js/ apa adanya ke dist/. CSS di-minify & diberi hash (cache-busting).
 * - Code-split/minify JS penuh dilakukan bertahap (strangler pattern) nanti.
 */
import { defineConfig } from 'vite';
import { copyFileSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

function copyDir(src, dest) {
  mkdirSync(dest, { recursive: true });
  for (const entry of readdirSync(src)) {
    const s = path.join(src, entry);
    const d = path.join(dest, entry);
    if (statSync(s).isDirectory()) copyDir(s, d);
    else copyFileSync(s, d);
  }
}

// Salin script klasik (lib.js/ui.js/app.js) + PWA (sw/manifest/icons) ke dist
// agar index.html hasil build tetap self-contained.
function copyClassicJs() {
  return {
    name: 'copy-classic-js',
    closeBundle() {
      copyDir('js', 'dist/js');
      for (const f of ['sw.js', 'manifest.webmanifest']) {
        copyFileSync(f, `dist/${f}`);
      }
      copyDir('icons', 'dist/icons');
    },
  };
}

export default defineConfig({
  root: '.',
  base: './',
  plugins: [copyClassicJs()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2018',
    minify: 'esbuild',
    cssCodeSplit: true,
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
});
