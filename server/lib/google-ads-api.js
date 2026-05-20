/**
 * Google Ads API — keyword data fetcher.
 *
 * Wraps `KeywordPlanIdeaService.generateKeywordIdeas` to return a flat
 * row shape that downstream callers (Python via subprocess/HTTP, or
 * other Node code) can consume directly.
 *
 * Output row:
 *   { keyword, volume, kd, cpc_low_krw, cpc_high_krw }
 *
 * Env vars (loaded by dotenv from project root .env):
 *   GOOGLE_ADS_DEVELOPER_TOKEN
 *   GOOGLE_ADS_CLIENT_ID
 *   GOOGLE_ADS_CLIENT_SECRET
 *   GOOGLE_ADS_REFRESH_TOKEN
 *   GOOGLE_ADS_CUSTOMER_ID
 *   GOOGLE_ADS_LOGIN_CUSTOMER_ID
 */
import "dotenv/config";
import { GoogleAdsApi, enums } from "google-ads-api";

// ---------------------------------------------------------------------------
// Env loading + validation. Missing vars throw at first use, not import time,
// so the test scripts can still import the module to inspect helpers.
// ---------------------------------------------------------------------------
const REQUIRED_ENV = [
  "GOOGLE_ADS_DEVELOPER_TOKEN",
  "GOOGLE_ADS_CLIENT_ID",
  "GOOGLE_ADS_CLIENT_SECRET",
  "GOOGLE_ADS_REFRESH_TOKEN",
  "GOOGLE_ADS_CUSTOMER_ID",
  "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
];

function readEnv() {
  const env = {};
  const missing = [];
  for (const key of REQUIRED_ENV) {
    const v = (process.env[key] || "").trim();
    if (!v || v.startsWith("여기에")) {
      missing.push(key);
    } else {
      env[key] = v;
    }
  }
  if (missing.length) {
    const err = new Error(
      `[google-ads-api] Missing env: ${missing.join(", ")}. ` +
        "Add them to .env at project root."
    );
    err.code = "ENV_MISSING";
    throw err;
  }
  // Customer IDs in google-ads-api must be digit-only (no dashes).
  env.GOOGLE_ADS_CUSTOMER_ID = env.GOOGLE_ADS_CUSTOMER_ID.replace(/-/g, "");
  env.GOOGLE_ADS_LOGIN_CUSTOMER_ID = env.GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace(
    /-/g,
    ""
  );
  return env;
}

// ---------------------------------------------------------------------------
// Geo / language constants (Google Ads resource IDs).
// Extend as more locales are needed.
// ---------------------------------------------------------------------------
const GEO_TARGETS = {
  US: "2840",
  KR: "2410",
  JP: "2392",
  GB: "2826",
  DE: "2276",
  CA: "2124",
  AU: "2036",
};

const LANGUAGE_TARGETS = {
  en: "1000",
  ko: "1012",
  ja: "1005",
  de: "1001",
  fr: "1002",
  es: "1003",
};

// ---------------------------------------------------------------------------
// Lazy-init client + customer (singletons across calls in one process).
// ---------------------------------------------------------------------------
let _client = null;
let _customer = null;

function getClient() {
  if (_client) return _client;
  const env = readEnv();
  _client = new GoogleAdsApi({
    client_id: env.GOOGLE_ADS_CLIENT_ID,
    client_secret: env.GOOGLE_ADS_CLIENT_SECRET,
    developer_token: env.GOOGLE_ADS_DEVELOPER_TOKEN,
  });
  return _client;
}

function getCustomer() {
  if (_customer) return _customer;
  const env = readEnv();
  _customer = getClient().Customer({
    customer_id: env.GOOGLE_ADS_CUSTOMER_ID,
    login_customer_id: env.GOOGLE_ADS_LOGIN_CUSTOMER_ID,
    refresh_token: env.GOOGLE_ADS_REFRESH_TOKEN,
  });
  return _customer;
}

// ---------------------------------------------------------------------------
// Numeric helpers.
// ---------------------------------------------------------------------------
const KRW_PER_USD = Number(process.env.KRW_PER_USD || 1350);

function microsToKrw(micros) {
  if (micros === null || micros === undefined) return 0;
  const usd = Number(micros) / 1_000_000;
  if (!Number.isFinite(usd) || usd <= 0) return 0;
  return Math.round(usd * KRW_PER_USD);
}

// Map Google's competition_index (0-100) or competition enum to a KD-style
// 0-100 score. competition_index is already on the right scale when present.
function competitionToKd(index, level) {
  if (typeof index === "number" && Number.isFinite(index)) {
    return Math.max(0, Math.min(100, Math.round(index)));
  }
  const fromEnum = { LOW: 25, MEDIUM: 50, HIGH: 75 };
  const key = typeof level === "string" ? level.toUpperCase() : level;
  return fromEnum[key] ?? 50;
}

function normalizeMetrics(item) {
  const m = item.keyword_idea_metrics || {};
  return {
    keyword: String(item.text || "").trim(),
    volume: Number(m.avg_monthly_searches || 0),
    kd: competitionToKd(m.competition_index, m.competition),
    cpc_low_krw: microsToKrw(m.low_top_of_page_bid_micros),
    cpc_high_krw: microsToKrw(m.high_top_of_page_bid_micros),
  };
}

// ---------------------------------------------------------------------------
// Error classification → throws with a clear category prefix so callers can
// branch on err.code instead of regex-matching the message.
// ---------------------------------------------------------------------------
function classifyAndThrow(err) {
  const raw = err?.errors?.[0]?.error_code || {};
  const msg = String(err?.message || err);
  const codes = Object.keys(raw).join(",");

  if (codes.includes("QUOTA") || /quota/i.test(msg)) {
    const e = new Error(
      `[google-ads-api] Quota exceeded: ${msg}. Retry after the quota window resets.`
    );
    e.code = "QUOTA";
    throw e;
  }
  if (
    codes.includes("AUTHENTICATION") ||
    codes.includes("AUTHORIZATION") ||
    /UNAUTHENTICATED|PERMISSION_DENIED|invalid_grant|refresh_token/i.test(msg)
  ) {
    const e = new Error(
      `[google-ads-api] Auth error: ${msg}. Check refresh token + customer IDs.`
    );
    e.code = "AUTH";
    throw e;
  }
  if (
    /ECONNRESET|ETIMEDOUT|ENOTFOUND|ECONNREFUSED|network|fetch failed/i.test(
      msg
    )
  ) {
    const e = new Error(
      `[google-ads-api] Network error: ${msg}. Retry after a minute.`
    );
    e.code = "NETWORK";
    throw e;
  }
  const e = new Error(`[google-ads-api] ${msg}`);
  e.code = "UNKNOWN";
  e.cause = err;
  throw e;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
/**
 * Fetch keyword metrics from Google Ads.
 *
 * @param {string[]} keywords  — seed keywords (1..20 recommended per call)
 * @param {string}   geo       — geo code, default "US"
 * @param {string}   lang      — language code, default "en"
 * @returns {Promise<Array<{keyword,volume,kd,cpc_low_krw,cpc_high_krw}>>}
 */
export async function getKeywordData(keywords, geo = "US", lang = "en") {
  if (!Array.isArray(keywords) || keywords.length === 0) return [];
  const cleaned = keywords
    .map((k) => String(k || "").trim())
    .filter(Boolean)
    .slice(0, 20);
  if (cleaned.length === 0) return [];

  const env = readEnv();
  const customer = getCustomer();

  const geoId = GEO_TARGETS[geo] || GEO_TARGETS.US;
  const langId = LANGUAGE_TARGETS[lang] || LANGUAGE_TARGETS.en;

  try {
    const response = await customer.keywordPlanIdeas.generateKeywordIdeas({
      customer_id: env.GOOGLE_ADS_CUSTOMER_ID,
      language: `languageConstants/${langId}`,
      geo_target_constants: [`geoTargetConstants/${geoId}`],
      include_adult_keywords: false,
      keyword_plan_network:
        enums.KeywordPlanNetwork.GOOGLE_SEARCH_AND_PARTNERS,
      keyword_seed: { keywords: cleaned },
    });

    const wanted = new Set(cleaned.map((s) => s.toLowerCase()));
    const rows = [];
    for (const item of response || []) {
      const row = normalizeMetrics(item);
      if (!row.keyword) continue;
      if (!wanted.has(row.keyword.toLowerCase())) continue;
      rows.push(row);
    }
    return rows;
  } catch (err) {
    classifyAndThrow(err);
  }
}

// Helpers exported for tests / introspection.
export const __internals = {
  readEnv,
  microsToKrw,
  competitionToKd,
  normalizeMetrics,
  GEO_TARGETS,
  LANGUAGE_TARGETS,
};
