/**
 * Keyword research pipeline.
 *
 * Flow:
 *   1. Fan-out each seed via Google Suggest (10-20 variants/seed).
 *   2. Dedup across seeds → master keyword list.
 *   3. Cache lookup (30-day TTL). Hits skip the API.
 *   4. Batch-call Google Ads for misses. Graceful fallback to volume=0/kd=0
 *      when Developer Token is Explorer-grade (Basic not yet approved).
 *   5. Persist results into cache.
 *   6. Compute opportunity_score = Volume / (KD + 1).
 *   7. Filter "gems": KD <= 30 AND Volume >= 1000 (top 50, score desc).
 *   8. Return { gems[], all[], metadata }.
 */
import { suggestKeywords } from "./google-suggest.js";
import { getKeywordData } from "./google-ads-api.js";
import { get as cacheGet, set as cacheSet } from "./keyword-cache.js";

const ADS_BATCH_SIZE = 20; // generateKeywordIdeas hard cap per request
const GEM_MAX_KD = 30;
const GEM_MIN_VOLUME = 1000;
const GEMS_TOP_N = 50;

/**
 * @param {string[]} seeds   base queries (1..N)
 * @param {object}   options
 * @param {string}   options.geo    default "US"
 * @param {string}   options.lang   default "en"
 * @param {boolean}  options.cache  default true — flip to false to force API
 * @returns {Promise<{gems, all, metadata}>}
 */
export async function researchKeywords(seeds, options = {}) {
  const start = Date.now();
  const geo = String(options.geo || "US").toUpperCase();
  const lang = String(options.lang || "en").toLowerCase();
  const useCache = options.cache !== false;

  const seedList = (seeds || [])
    .map((s) => String(s || "").trim())
    .filter(Boolean);
  if (seedList.length === 0) {
    return _emptyResult(start);
  }

  // 1-2. Expand seeds via Suggest, then dedup.
  const expanded = await _expandSeeds(seedList, geo.toLowerCase(), lang);
  const master = _dedupKeywords([...seedList, ...expanded]);

  // 3. Cache lookup. Cached payload was stored via `cacheSet(kw, geo, lang,
  //    row)` so we expect a single row object back per key.
  const cachedRows = {}; // kw_lower -> row
  const misses = [];
  if (useCache) {
    for (const kw of master) {
      const hit = cacheGet(kw, geo, lang);
      if (hit && typeof hit === "object" && hit.keyword !== undefined) {
        cachedRows[kw.toLowerCase()] = hit;
      } else {
        misses.push(kw);
      }
    }
  } else {
    misses.push(...master);
  }

  // 4. API call for misses (batched, graceful fallback on any error).
  let apiCalls = 0;
  const freshRows = {}; // kw_lower -> row (zeroed if API failed)
  for (let i = 0; i < misses.length; i += ADS_BATCH_SIZE) {
    const batch = misses.slice(i, i + ADS_BATCH_SIZE);
    apiCalls += 1;

    let rows = [];
    try {
      rows = (await getKeywordData(batch, geo, lang)) || [];
    } catch (err) {
      // Explorer token / quota / auth / network all funnel here. Pipeline
      // continues with zero-filled rows so downstream code is uniform.
      console.warn(
        `[keyword-pipeline] API fallback (${err.code || "?"}): ${err.message}`
      );
      rows = [];
    }

    for (const row of rows) {
      const key = String(row.keyword || "").toLowerCase();
      if (key) freshRows[key] = _normalizeRow(row);
    }
    // Guarantee one entry per requested keyword even when the API omitted
    // it (no-data) or threw entirely. Synth a zero row so opportunity-score
    // math doesn't blow up later.
    for (const kw of batch) {
      const key = kw.toLowerCase();
      if (!freshRows[key]) freshRows[key] = _zeroRow(kw);
    }
  }

  // 5. Persist fresh rows into cache.
  if (useCache) {
    for (const key of Object.keys(freshRows)) {
      cacheSet(key, geo, lang, freshRows[key]);
    }
  }

  // 6. Merge cached + fresh, compute opportunity score.
  const all = [];
  for (const kw of master) {
    const key = kw.toLowerCase();
    const row = cachedRows[key] || freshRows[key] || _zeroRow(kw);
    const score = _opportunityScore(row.volume, row.kd);
    all.push({ ...row, keyword: row.keyword || kw, score });
  }

  // 7. Sort + filter gems.
  const gems = all
    .filter((r) => r.kd <= GEM_MAX_KD && r.volume >= GEM_MIN_VOLUME)
    .sort((a, b) => b.score - a.score)
    .slice(0, GEMS_TOP_N);

  // 8. Done.
  return {
    gems,
    all,
    metadata: {
      total: all.length,
      cached_count: Object.keys(cachedRows).length,
      api_calls: apiCalls,
      gem_count: gems.length,
      elapsed_ms: Date.now() - start,
    },
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
async function _expandSeeds(seeds, country, lang) {
  if (seeds.length === 0) return [];
  const results = await Promise.all(
    seeds.map((s) => suggestKeywords(s, country, lang))
  );
  return results.flat();
}

function _dedupKeywords(list) {
  const seen = new Set();
  const out = [];
  for (const raw of list) {
    const kw = String(raw || "").trim();
    if (!kw) continue;
    const key = kw.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(kw);
  }
  return out;
}

function _opportunityScore(volume, kd) {
  const v = Number(volume) || 0;
  const k = Number(kd) || 0;
  return v / (k + 1);
}

function _normalizeRow(row) {
  return {
    keyword: String(row.keyword || "").trim(),
    volume: Number(row.volume) || 0,
    kd: Number(row.kd) || 0,
    cpc_low: Number(row.cpc_low ?? row.cpc_low_krw ?? 0) || 0,
    cpc_high: Number(row.cpc_high ?? row.cpc_high_krw ?? 0) || 0,
  };
}

function _zeroRow(kw) {
  return { keyword: kw, volume: 0, kd: 0, cpc_low: 0, cpc_high: 0 };
}

function _emptyResult(start) {
  return {
    gems: [],
    all: [],
    metadata: {
      total: 0,
      cached_count: 0,
      api_calls: 0,
      gem_count: 0,
      elapsed_ms: Date.now() - start,
    },
  };
}
