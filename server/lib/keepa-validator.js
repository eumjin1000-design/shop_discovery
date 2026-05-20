/**
 * Keepa Amazon validator — converts gem keywords from the pipeline into real
 * Amazon product evidence (live ASIN, BSR, price, rating, review count).
 *
 * Three functions:
 *   searchKeepaByKeyword(keyword, limit) — keyword → ASIN[]
 *   validateProductsByASIN(asins)        — ASIN[] → product[]
 *   validateKeywordsWithKeepa(gems)      — gems[] → gems[] + amazon_products
 *
 * Endpoint reference: https://api.keepa.com (domain=1 is amazon.com)
 * Stats indices in product.stats.current / .avg30 (verified against live
 * Keepa response on 2026-05-20 — matches the Python sources.py convention):
 *    0  Amazon price (cents, -1 if no Amazon offer)
 *    1  New (3P) price (cents)  ← fallback when Amazon is -1
 *    3  Sales rank (BSR)         ← THE rank value
 *   16  Rating × 10              (e.g. 47 = 4.7 stars)
 *   17  Review count
 *
 * NOTE: the live response stores ``salesRankReference`` at the product
 * top-level (it's the *category* id, not the rank). The actual rank
 * number is in ``stats.current[3]``.
 *
 * All network calls are best-effort — they return [] on any failure so the
 * pipeline can continue with whatever data is available. KEEPA_API_KEY is
 * read lazily; missing key throws only at first call, not at import.
 */
import axios from 'axios';
import 'dotenv/config';

const BASE = 'https://api.keepa.com';
const DOMAIN_US = 1;
const TIMEOUT_MS = 30_000;
const KEEPA_BATCH = 100;          // Keepa allows up to 100 ASIN per request
const PRODUCT_BSR_MAX = 50_000;   // validateKeywordsWithKeepa filter

function getKey() {
  const k = String(process.env.KEEPA_API_KEY || '').trim();
  if (!k || k.startsWith('여기에')) {
    const err = new Error('[keepa-validator] KEEPA_API_KEY missing in .env');
    err.code = 'ENV_MISSING';
    throw err;
  }
  return k;
}

// ---------------------------------------------------------------------------
// 1. searchKeepaByKeyword — keyword → ASIN[] (best-effort)
// ---------------------------------------------------------------------------
/**
 * @param {string} keyword
 * @param {number} limit  default 20
 * @returns {Promise<string[]>} ASINs (≤ limit)
 */
export async function searchKeepaByKeyword(keyword, limit = 20) {
  const term = String(keyword || '').trim();
  if (!term) return [];

  let data;
  try {
    const res = await axios.get(`${BASE}/search`, {
      params: {
        key: getKey(),
        domain: DOMAIN_US,
        type: 'product',
        term,
      },
      timeout: TIMEOUT_MS,
    });
    data = res.data;
  } catch (err) {
    if (err.code === 'ENV_MISSING') throw err;
    console.warn(`[keepa-validator] search failed: ${err.message}`);
    return [];
  }

  // Keepa returns either asinList (string[]) or products (object[]).
  let asins = [];
  if (Array.isArray(data?.asinList)) {
    asins = data.asinList;
  } else if (Array.isArray(data?.products)) {
    asins = data.products.map((p) => p?.asin).filter(Boolean);
  } else if (Array.isArray(data?.categories)) {
    // Some search modes nest products under categories[].productList
    for (const cat of data.categories) {
      if (Array.isArray(cat?.productList)) {
        asins.push(...cat.productList.map((p) => p?.asin).filter(Boolean));
      }
    }
  }
  return asins.filter((a) => typeof a === 'string' && a.length === 10).slice(0, limit);
}

// ---------------------------------------------------------------------------
// 2. validateProductsByASIN — ASIN[] → normalised product rows
// ---------------------------------------------------------------------------
/**
 * No BSR-based filtering here — the pipeline-level
 * validateKeywordsWithKeepa() applies the BSR ≤ 50,000 cut. Returning
 * everything keeps this function reusable for callers that want raw rows.
 */
export async function validateProductsByASIN(asins) {
  const list = (asins || []).filter(
    (a) => typeof a === 'string' && a.length === 10
  );
  if (list.length === 0) return [];

  const out = [];
  for (let i = 0; i < list.length; i += KEEPA_BATCH) {
    const slice = list.slice(i, i + KEEPA_BATCH);
    let data;
    try {
      const res = await axios.get(`${BASE}/product`, {
        params: {
          key: getKey(),
          domain: DOMAIN_US,
          asin: slice.join(','),
          stats: 30,
        },
        timeout: TIMEOUT_MS,
      });
      data = res.data;
    } catch (err) {
      if (err.code === 'ENV_MISSING') throw err;
      console.warn(`[keepa-validator] product fetch failed: ${err.message}`);
      continue;
    }
    const products = Array.isArray(data?.products) ? data.products : [];
    for (const p of products) out.push(_normalizeProduct(p));
  }
  return out;
}

function _normalizeProduct(p) {
  const stats = p?.stats || {};
  const current = Array.isArray(stats.current) ? stats.current : [];
  const avg30 = Array.isArray(stats.avg30) ? stats.avg30 : [];
  const imageCsv = String(p?.imagesCSV || '').trim();
  const firstImage = imageCsv ? imageCsv.split(',')[0] : '';

  // Keepa stores prices in cents and ratings × 10. Negative values mean
  // "no data" so we treat them as 0.
  const price = current[0] && current[0] > 0 ? current[0] / 100 : 0;
  const priceAvg = avg30[0] && avg30[0] > 0 ? avg30[0] / 100 : 0;
  const reviews = current[16] && current[16] > 0 ? Number(current[16]) : 0;
  const rating = current[18] && current[18] > 0 ? Number(current[18]) / 10 : 0;

  return {
    asin: p?.asin || '',
    title: String(p?.title || '').trim(),
    brand: String(p?.brand || '').trim(),
    bsr: stats.salesRankReference || null,
    current_price: Number(price.toFixed(2)),
    avg_price_30d: Number(priceAvg.toFixed(2)),
    review_count: reviews,
    rating: Number(rating.toFixed(1)),
    image: firstImage
      ? `https://images-na.ssl-images-amazon.com/images/I/${firstImage}`
      : null,
  };
}

// ---------------------------------------------------------------------------
// 3. validateKeywordsWithKeepa — gems[] → gems[] + amazon_products
// ---------------------------------------------------------------------------
/**
 * For each gem: search Keepa, pull top-10 ASINs, fetch product details,
 * keep only products with a numeric BSR ≤ PRODUCT_BSR_MAX (50,000), and
 * attach the survivors as `gem.amazon_products`.
 *
 * Loops sequentially (not Promise.all) because Keepa enforces per-account
 * concurrency limits and parallel bursts trigger throttling.
 */
export async function validateKeywordsWithKeepa(gems) {
  const list = Array.isArray(gems) ? gems : [];
  const out = [];
  for (const gem of list) {
    const asins = await searchKeepaByKeyword(gem.keyword, 10);
    const products = await validateProductsByASIN(asins);
    const ranked = products.filter(
      (p) => Number.isFinite(p.bsr) && p.bsr > 0 && p.bsr <= PRODUCT_BSR_MAX
    );
    out.push({ ...gem, amazon_products: ranked });
  }
  return out;
}
