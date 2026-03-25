import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PORT = process.env.MD_EDITOR_PORT || 8081;

const MIME_TYPES = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain',
  '.md': 'text/markdown',
};

const server = createServer(async (req, res) => {
  try {
    // Limpiar URL
    let url = req.url === '/' ? '/index.html' : req.url;
    url = url.split('?')[0];
    
    // Prevenir directory traversal
    if (url.includes('..')) {
      res.writeHead(403);
      res.end('Forbidden');
      return;
    }
    
    const filePath = join(__dirname, url);
    const ext = extname(filePath);
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    
    const content = await readFile(filePath);
    
    res.writeHead(200, {
      'Content-Type': contentType,
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Access-Control-Allow-Origin': '*',
    });
    res.end(content);
    
  } catch (error) {
    if (error.code === 'ENOENT') {
      res.writeHead(404);
      res.end('File not found');
    } else {
      console.error('Error:', error);
      res.writeHead(500);
      res.end('Internal server error');
    }
  }
});

server.listen(PORT, () => {
  console.log(`🎨 MD/Mermaid Editor escuchando en http://localhost:${PORT}`);
  console.log(`🌐 Público: https://diagram.masamadremonterrey.com`);
});