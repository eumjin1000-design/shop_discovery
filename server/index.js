/**
 * HTTP API server for the shop_discovery Node.js keyword/sourcing system.
 *
 * Thin Express app — all logic lives in server/lib/*. Routes are mounted
 * per-domain under server/routes/*. Start with:
 *
 *     node server/index.js          (or npm run serve)
 *
 * Port: env PORT, default 8787.
 */
import 'dotenv/config';
import { pathToFileURL } from 'node:url';
import express from 'express';

import keywordsRouter from './routes/keywords.js';

const app = express();
app.use(express.json({ limit: '1mb' }));

// Liveness probe.
app.get('/health', (_req, res) => {
  res.json({ ok: true, ts: Date.now() });
});

// Domain routers.
app.use('/api/keywords', keywordsRouter);

// 404 fallback in the API namespace (consistent envelope).
app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: `경로를 찾을 수 없습니다: ${req.method} ${req.path}`,
    code: 'NOT_FOUND',
  });
});

const PORT = Number(process.env.PORT || 8787);

// Only listen when run directly (not when imported). pathToFileURL normalises
// Windows paths (backslashes + drive letter) so the comparison works there too.
const runDirectly =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (runDirectly) {
  app.listen(PORT, () => {
    console.log(`[server] listening on http://localhost:${PORT}`);
  });
}

export { app, PORT };
