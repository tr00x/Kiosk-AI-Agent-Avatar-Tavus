import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import http from 'http';

// Plugin: HTTP → HTTPS redirect on port 5174
function httpsRedirect() {
  return {
    name: 'https-redirect',
    configureServer() {
      const redirectServer = http.createServer((req, res) => {
        const host = (req.headers.host || 'localhost:5173').replace(/:\d+$/, ':5173');
        res.writeHead(301, { Location: `https://${host}${req.url}` });
        res.end();
      });
      redirectServer.listen(5174, '0.0.0.0', () => {
        console.log('  ➜  HTTP redirect: http://localhost:5174 → https://localhost:5173');
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), httpsRedirect()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    https: {
      key: fs.readFileSync('./certs/localhost+2-key.pem'),
      cert: fs.readFileSync('./certs/localhost+2.pem'),
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/tools': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
