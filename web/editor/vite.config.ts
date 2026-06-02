import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  base: '/editor/',
  build: {
    outDir: path.resolve(__dirname, '../editor-dist'),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/editor': 'http://localhost:8080',
      '/cities': 'http://localhost:8080',
      '/poi': 'http://localhost:8080',
      '/trip': 'http://localhost:8080',
    },
  },
});
