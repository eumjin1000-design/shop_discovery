/**
 * Keyword research API routes.
 *
 *   POST /api/keywords/research      seeds → gems (+ optional Keepa sourcing)
 *   GET  /api/keywords/cache/stats   keyword-cache hit-rate summary
 *
 * Response envelope (uniform):
 *   success: true  → { success: true, data: {...} }
 *   success: false → { success: false, error: "...", code: "..." }
 *
 * Error codes: VALIDATION_ERROR (400) · TIMEOUT (504) · INTERNAL_ERROR (500)
 */
import express from 'express';

import { researchKeywords } from '../lib/keyword-pipeline.js';
import { validateKeywordsWithKeepa } from '../lib/keepa-validator.js';
import { stats as cacheStats } from '../lib/keyword-cache.js';

const router = express.Router();

const MAX_SEEDS = 20;
const RESEARCH_TIMEOUT_MS = 120_000;
const DEFAULT_TOP_N = 5;

/** Reject if `promise` doesn't settle within `ms`. */
function withTimeout(promise, ms) {
  let timer;
  const timeout = new Promise((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error('TIMEOUT')), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

// ---------------------------------------------------------------------------
// POST /api/keywords/research
// ---------------------------------------------------------------------------
router.post('/research', async (req, res) => {
  const body = req.body || {};
  const { seeds, market, language, validate_with_keepa, top_n } = body;

  // --- validation ---
  if (!Array.isArray(seeds) || seeds.length === 0) {
    return res.status(400).json({
      success: false,
      error: 'seeds 필드가 필요합니다 (비어있지 않은 배열).',
      code: 'VALIDATION_ERROR',
    });
  }
  const cleanSeeds = seeds
    .map((s) => String(s || '').trim())
    .filter(Boolean)
    .slice(0, MAX_SEEDS);
  if (cleanSeeds.length === 0) {
    return res.status(400).json({
      success: false,
      error: 'seeds에 유효한 문자열이 없습니다.',
      code: 'VALIDATION_ERROR',
    });
  }

  const geo = String(market || 'US').toUpperCase();
  const lang = String(language || 'en').toLowerCase();
  const topN = Number.isFinite(top_n) ? Math.max(1, top_n) : DEFAULT_TOP_N;

  try {
    // Phase 1: Google search-volume research (no Keepa here).
    const result = await withTimeout(
      researchKeywords(cleanSeeds, { geo, lang, validate_with_keepa: false }),
      RESEARCH_TIMEOUT_MS
    );

    // Phase 2 (optional): Keepa sourcing on the TOP-N gems only (token-frugal).
    let gems = result.gems;
    let keepa_validated = false;
    if (validate_with_keepa === true && gems.length > 0) {
      const head = await withTimeout(
        validateKeywordsWithKeepa(gems.slice(0, topN)),
        RESEARCH_TIMEOUT_MS
      );
      gems = [...head, ...gems.slice(topN)];
      keepa_validated = true;
    }

    const google_volume_available =
      result.gems.some((g) => g.volume > 0) ||
      result.all.some((k) => Number(k.volume) > 0);

    return res.json({
      success: true,
      data: {
        gems,
        all: result.all,
        metadata: {
          ...result.metadata,
          keepa_validated,
          top_n: validate_with_keepa === true ? topN : 0,
          google_volume_available,
        },
      },
    });
  } catch (err) {
    if (err && err.message === 'TIMEOUT') {
      return res.status(504).json({
        success: false,
        error: '요청이 120초를 초과했습니다.',
        code: 'TIMEOUT',
      });
    }
    return res.status(500).json({
      success: false,
      error: String(err?.message || err),
      code: 'INTERNAL_ERROR',
    });
  }
});

// ---------------------------------------------------------------------------
// GET /api/keywords/cache/stats
// ---------------------------------------------------------------------------
router.get('/cache/stats', (_req, res) => {
  try {
    const s = cacheStats();
    return res.json({
      success: true,
      data: {
        total: s.total,
        expired: s.expired,
        hit_rate: `${Math.round((s.hit_rate || 0) * 100)}%`,
      },
    });
  } catch (err) {
    return res.status(500).json({
      success: false,
      error: String(err?.message || err),
      code: 'INTERNAL_ERROR',
    });
  }
});

export default router;
