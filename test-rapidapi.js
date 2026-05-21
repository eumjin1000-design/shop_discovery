import { getKeywordDataViaRapidAPI } from './server/lib/rapidapi-keywords.js';

console.log('=== RapidAPI 키워드 테스트 ===');
const results = await getKeywordDataViaRapidAPI(['korean skincare']);

console.log('총 키워드:', results.length);
console.log('보석 후보:');
results
  .filter((r) => r.volume >= 1000 && r.kd <= 30)
  .slice(0, 10)
  .forEach((r) =>
    console.log(`💎 ${r.keyword} | 검색량:${r.volume} | KD:${r.kd} | 점수:${(r.volume / (r.kd + 1)).toFixed(0)}`)
  );
