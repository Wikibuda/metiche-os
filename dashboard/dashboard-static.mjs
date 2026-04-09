import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PORT = process.env.DASHBOARD_PORT || 5063;
const HTML_FILE = join(__dirname, 'admin-dashboard-lab.html');

const server = createServer(async (req, res) => {
  try {
    // Solo servir el archivo HTML para cualquier ruta
    const content = await readFile(HTML_FILE, 'utf-8');
    
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
    });
    res.end(content);
    
  } catch (error) {
    console.error('Error:', error);
    res.writeHead(500);
    res.end('Internal server error');
  }
});

server.listen(PORT, () => {
  console.log(`📊 Dashboard estático escuchando en puerto ${PORT}`);
  console.log(`🌐 Público: https://dashboard.masamadremonterrey.com`);
});
