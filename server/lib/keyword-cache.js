/**
 * SQLite-backed cache for Google Ads keyword data.
 *
 * Table: keyword_cache (keyword, geo, language, data JSON, fetched_at)
 * TTL: 30 days. Expired rows are returned as `null` by `get()` but kept in
 * the table until a future write overwrites them (or the user clears them).
 */
import Database from "better-sqlite3";
import path from "node:path";
import fs from "node:fs";

const DEFAULT_DB_PATH = path.resolve(process.cwd(), "seo-cache.db");
const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

const DDL_CREATE_TABLE =
  "CREATE TABLE IF NOT EXISTS keyword_cache (" +
  "  keyword TEXT NOT NULL," +
  "  geo TEXT NOT NULL," +
  "  language TEXT NOT NULL," +
  "  data TEXT NOT NULL," +
  "  fetched_at INTEGER NOT NULL," +
  "  PRIMARY KEY (keyword, geo, language)" +
  ")";

const DDL_CREATE_INDEX =
  "CREATE INDEX IF NOT EXISTS idx_kc_fetched_at " +
  "ON keyword_cache(fetched_at)";

let _db = null;
let _dbPath = DEFAULT_DB_PATH;

function getDb() {
  if (_db) return _db;
  const dir = path.dirname(_dbPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  _db = new Database(_dbPath);
  _db.pragma("journal_mode = WAL");
  _db.prepare(DDL_CREATE_TABLE).run();
  _db.prepare(DDL_CREATE_INDEX).run();
  return _db;
}

/** Override the default cache file path. Useful for tests. */
export function configure({ dbPath } = {}) {
  if (dbPath && dbPath !== _dbPath) {
    if (_db) _db.close();
    _db = null;
    _dbPath = path.resolve(dbPath);
  }
}

/**
 * @param {string} keyword
 * @param {string} geo       default "US"
 * @param {string} lang      default "en"
 * @param {number} maxAgeMs  freshness window, default 30d. Pass a shorter
 *                           value (e.g. 24h) for fast-moving data like
 *                           Keepa product prices.
 * @returns parsed cached value (any JSON) or null when missing/expired.
 */
export function get(keyword, geo = "US", lang = "en", maxAgeMs = TTL_MS) {
  const db = getDb();
  const row = db
    .prepare(
      "SELECT data, fetched_at FROM keyword_cache " +
        "WHERE keyword = ? AND geo = ? AND language = ?"
    )
    .get(String(keyword), String(geo), String(lang));
  if (!row) return null;
  if (Date.now() - Number(row.fetched_at) > maxAgeMs) return null;
  try {
    return JSON.parse(row.data);
  } catch {
    return null;
  }
}

/**
 * Upsert a keyword's cached payload. `data` is JSON-serialised.
 */
export function set(keyword, geo, lang, data) {
  const db = getDb();
  db.prepare(
    "INSERT OR REPLACE INTO keyword_cache " +
      "(keyword, geo, language, data, fetched_at) " +
      "VALUES (?, ?, ?, ?, ?)"
  ).run(
    String(keyword),
    String(geo || "US"),
    String(lang || "en"),
    JSON.stringify(data),
    Date.now()
  );
}

/**
 * Aggregate cache stats: total rows, how many have aged past TTL, and the
 * implied hit_rate (non-expired / total).
 */
export function stats() {
  const db = getDb();
  const total = db
    .prepare("SELECT COUNT(*) AS n FROM keyword_cache")
    .get().n;
  const expired = db
    .prepare(
      "SELECT COUNT(*) AS n FROM keyword_cache WHERE fetched_at < ?"
    )
    .get(Date.now() - TTL_MS).n;
  const hit_rate = total ? (total - expired) / total : 0;
  return { total, expired, hit_rate };
}

/** Remove rows older than TTL. Returns the number deleted. */
export function prune() {
  const db = getDb();
  const info = db
    .prepare("DELETE FROM keyword_cache WHERE fetched_at < ?")
    .run(Date.now() - TTL_MS);
  return info.changes || 0;
}

/** Close the DB handle. Idempotent; safe to call from tests or shutdown. */
export function close() {
  if (_db) {
    _db.close();
    _db = null;
  }
}
