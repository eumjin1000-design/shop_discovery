/**
 * Shop discovery pipeline — 2-phase, Google-volume-first.
 *
 * Workflow (the order matters and is the whole point of this module):
 *
 *   PHASE 1 — Shop selection by Google search volume
 *     researchKeywords(seeds) expands seeds via Suggest, pulls Google Ads
 *     volume/KD, ranks "gems" by opportunity = volume / (KD + 1). These
 *     gems ARE the candidate shop/category signals — high search demand,
 *     low competition. This is the primary selection criterion.
 *
 *   PHASE 2 — Product sourcing for the selected shop (Keepa)
 *     For only the TOP-N gems (token-frugal — Keepa is the expensive,
 *     rate-limited resource), validateKeywordsWithKeepa attaches real
 *     Amazon products (ASIN, BSR ≤ 50k, price, rating, reviews).
 *
 * Net result: a ranked list of shop candidates, each already carrying the
 * concrete Amazon products you'd source if you pick it.
 *
 * Google Ads not yet Basic-approved → Phase 1 volumes are 0 (gems empty),
 * so Phase 2 is skipped gracefully. Once approved, the same call fills in.
 */
import { researchKeywords } from './keyword-pipeline.js';
import { validateKeywordsWithKeepa } from './keepa-validator.js';

const DEFAULT_TOP_N = 10; // how many top gems to source via Keepa

/**
 * @param {string[]} seeds  base category keywords (e.g. ["memory foam pillow"])
 * @param {object}   options
 * @param {string}   options.geo            default "US"
 * @param {string}   options.lang           default "en"
 * @param {number}   options.topN           gems to source via Keepa (default 10)
 * @param {boolean}  options.skipKeepa      true → Phase 1 only (no sourcing)
 * @returns {Promise<{shop_candidates, all_keywords, metadata}>}
 */
export async function discoverShop(seeds, options = {}) {
  const start = Date.now();
  const geo = String(options.geo || 'US').toUpperCase();
  const lang = String(options.lang || 'en').toLowerCase();
  const topN = Number.isFinite(options.topN) ? options.topN : DEFAULT_TOP_N;

  // ----- PHASE 1: Google search volume → ranked gems -----
  const research = await researchKeywords(seeds, {
    geo,
    lang,
    validate_with_keepa: false, // we control Keepa explicitly in phase 2
  });

  const topGems = research.gems.slice(0, Math.max(0, topN));

  // ----- PHASE 2: Keepa product sourcing for the top gems only -----
  let shopCandidates = topGems;
  let keepaSourced = false;
  if (!options.skipKeepa && topGems.length > 0) {
    try {
      shopCandidates = await validateKeywordsWithKeepa(topGems);
      keepaSourced = true;
    } catch (err) {
      console.warn(
        `[shop-pipeline] Keepa sourcing skipped (${err.code || '?'}): ${err.message}`
      );
      shopCandidates = topGems.map((g) => ({ ...g, amazon_products: [] }));
    }
  } else {
    shopCandidates = topGems.map((g) => ({ ...g, amazon_products: [] }));
  }

  // Sourcing-readiness summary: how many candidates actually have products.
  const withProducts = shopCandidates.filter(
    (c) => Array.isArray(c.amazon_products) && c.amazon_products.length > 0
  ).length;

  return {
    shop_candidates: shopCandidates,
    all_keywords: research.all,
    metadata: {
      phase1_total_keywords: research.metadata.total,
      phase1_gem_count: research.metadata.gem_count,
      phase2_sourced_top_n: topGems.length,
      phase2_with_products: withProducts,
      keepa_sourced: keepaSourced,
      google_volume_available: research.gems.some((g) => g.volume > 0),
      elapsed_ms: Date.now() - start,
    },
  };
}
