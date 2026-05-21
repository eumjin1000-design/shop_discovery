/**
 * RapidAPI "Google Keyword Insight" data source.
 *
 * Drop-in alternative to google-ads-api.js that works WITHOUT Google Ads
 * Basic Access — returns real search volume + competition index (KD) right
 * away. One seed keyword expands into ~100-300 related keywords, each with
 * volume / competition / CPC bids, so a single call replaces both the
 * Suggest expansion AND the Google Ads metrics lookup.
 *
 * Output row matches google-ads-api.js exactly (+ bonus `trend`):
 *   { keyword, volume, kd, cpc_low, cpc_high, trend }
 *
 * Env (loaded by dotenv):
 *   RAPIDAPI_KEY            RapidAPI application key (never hardcoded)
 *   RAPIDAPI_KEYWORD_HOST   default "google-keyword-insight1.p.rapidapi.com"
 */
import 'dotenv/config';
import axios from 'axios';

const DEFAULT_HOST = 'google-keyword-insight1.p.rapidapi.com';
const ENDPOINT = '/keysuggest/';
const TIMEOUT_MS = 30_000;

function _host() {
  return (process.env.RAPIDAPI_KEYWORD_HOST || DEFAULT_HOST).trim();
}

function _key() {
  const k = String(process.env.RAPIDAPI_KEY || '').trim();
  return (!k || k.startsWith('여기에')) ? null : k;
}

function _normalize(item) {
  return {
    keyword: String(item?.text || '').trim(),
    volume: Number(item?.volume) || 0,
    kd: Number(item?.competition_index) || 0,
    cpc_low: Number(item?.low_bid) || 0,
    cpc_high: Number(item?.high_bid) || 0,
    trend: Number(item?.trend) || 0,
  };
}

/**
 * Fetch keyword data for the FIRST seed (RapidAPI expands it into many).
 *
 * @param {string[]} keywords  only keywords[0] is used as the expansion seed
 * @param {string}   geo       location code, e.g. "US"
 * @param {string}   lang      language code, e.g. "en"
 * @returns {Promise<Array<{keyword,volume,kd,cpc_low,cpc_high,trend}>>}
 *          [] on missing key / network / parse error (graceful fallback).
 */
export async function getKeywordDataViaRapidAPI(keywords, geo = 'US', lang = 'en') {
  const key = _key();
  if (!key) {
    console.warn('[rapidapi-keywords] skipped: RAPIDAPI_KEY not set');
    return [];
  }
  const seed = (Array.isArray(keywords) ? keywords : [keywords])
    .map((k) => String(k || '').trim())
    .filter(Boolean)[0];
  if (!seed) return [];

  let data;
  try {
    const res = await axios.get(`https://${_host()}${ENDPOINT}`, {
      params: { keyword: seed, location: String(geo || 'US').toUpperCase(),
                lang: String(lang || 'en').toLowerCase() },
      headers: {
        'X-RapidAPI-Key': key,
        'X-RapidAPI-Host': _host(),
      },
      timeout: TIMEOUT_MS,
    });
    data = res.data;
  } catch (err) {
    const status = err?.response?.status;
    console.warn(`[rapidapi-keywords] request failed${status ? ` (HTTP ${status})` : ''}: ${err.message}`);
    return [];
  }

  // Response is a flat array of keyword objects.
  const list = Array.isArray(data) ? data
             : Array.isArray(data?.keywords) ? data.keywords
             : [];
  const seen = new Set();
  const out = [];
  for (const item of list) {
    const row = _normalize(item);
    const k = row.keyword.toLowerCase();
    if (!k || seen.has(k)) continue;
    seen.add(k);
    out.push(row);
  }
  return out;
}

export const __internals = { _normalize, _host, ENDPOINT };
