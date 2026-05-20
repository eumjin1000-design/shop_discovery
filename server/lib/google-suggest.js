/**
 * Google Suggest — keyword expansion via the public autocomplete endpoint.
 *
 * No auth needed. Returns the suggestions Google Search would show for a
 * given seed query. The keyword-pipeline fans seeds out into 10-20
 * long-tail variants here before sending them to Google Ads for metrics.
 *
 * Endpoint shape (client=firefox returns JSON instead of JSONP):
 *   [ query, [sug1, sug2, ...], [...], [...] ]
 */
import axios from "axios";

const ENDPOINT = "http://suggestqueries.google.com/complete/search";
const TIMEOUT_MS = 5000;

/**
 * Fetch autocomplete suggestions for a single seed.
 *
 * @param {string} seed    base query, e.g. "korean skincare"
 * @param {string} country ISO 3166 alpha-2 code, e.g. "us" (case-insensitive)
 * @param {string} lang    ISO 639 code, e.g. "en"
 * @returns {Promise<string[]>} unique suggestions (seed itself excluded).
 *          Returns [] on any network/parse error (best-effort, never throws).
 */
export async function suggestKeywords(seed, country = "us", lang = "en") {
  const q = String(seed || "").trim();
  if (!q) return [];

  let data;
  try {
    const res = await axios.get(ENDPOINT, {
      params: {
        client: "firefox",
        q,
        gl: String(country || "us").toLowerCase(),
        hl: String(lang || "en").toLowerCase(),
      },
      timeout: TIMEOUT_MS,
    });
    data = res.data;
  } catch {
    return [];
  }

  // Defensive parse: response shape is fixed by Google but we treat it as
  // untrusted input so a sudden format change just returns [].
  const list = Array.isArray(data) && Array.isArray(data[1]) ? data[1] : [];
  const seen = new Set();
  const out = [];
  const seedLower = q.toLowerCase();
  for (const item of list) {
    const s = String(item || "").trim();
    if (!s) continue;
    const key = s.toLowerCase();
    if (key === seedLower || seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

/**
 * Batch helper: fan out multiple seeds in parallel and dedup across them.
 *
 * @returns {Promise<{bySeed: Object<string, string[]>, all: string[]}>}
 *          `bySeed[seed]` is the raw suggestion list for that seed.
 *          `all` is seeds + every suggestion, deduped, original order.
 */
export async function suggestKeywordsBatch(seeds, country = "us", lang = "en") {
  const cleaned = (seeds || [])
    .map((s) => String(s || "").trim())
    .filter(Boolean);
  if (cleaned.length === 0) return { bySeed: {}, all: [] };

  const results = await Promise.all(
    cleaned.map((s) => suggestKeywords(s, country, lang))
  );

  const bySeed = {};
  const seen = new Set();
  const all = [];
  for (let i = 0; i < cleaned.length; i++) {
    const seed = cleaned[i];
    bySeed[seed] = results[i];
    if (!seen.has(seed.toLowerCase())) {
      seen.add(seed.toLowerCase());
      all.push(seed);
    }
    for (const s of results[i]) {
      const key = s.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        all.push(s);
      }
    }
  }
  return { bySeed, all };
}
