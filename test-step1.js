/**
 * Step 1 smoke test:
 *   1. Hit Google Ads with 2 seed keywords.
 *   2. Cache the result under "korean skincare / US / en".
 *   3. Read it back and check the hit + summary stats.
 *
 * Run:   node test-step1.js
 *
 * Success criteria (from the brief):
 *   { keyword: 'korean skincare', volume: 50000, kd: 100 } (or similar shape)
 *   캐시 hit: true
 *   캐시 통계: { total: 1, expired: 0 }
 */
import { getKeywordData } from "./server/lib/google-ads-api.js";
import { get, set, stats, close } from "./server/lib/keyword-cache.js";

async function main() {
  console.log("--- Step 1 smoke test ---");

  const seeds = ["korean skincare", "snail mucin"];
  console.log(`Fetching ${seeds.length} seed keywords from Google Ads...`);

  let data;
  try {
    data = await getKeywordData(seeds, "US", "en");
  } catch (err) {
    console.error(`API call failed [${err.code || "?"}]: ${err.message}`);
    process.exitCode = 1;
    return;
  }

  console.log(`API 결과 (총 ${data.length}개, 상위 3개):`);
  console.log(data.slice(0, 3));

  set("korean skincare", "US", "en", data);
  const cached = get("korean skincare", "US", "en");
  console.log("캐시 hit:", !!cached);

  console.log("캐시 통계:", stats());

  close();
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exitCode = 1;
});
