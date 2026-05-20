import { discoverShop } from './server/lib/shop-pipeline.js';

console.log('=== 2단계 샵 발굴 파이프라인 ===');
console.log('1단계: Google 검색량 → 샵 선정');
console.log('2단계: 선정 샵 → Keepa 제품 소싱\n');

console.time('discoverShop');
const result = await discoverShop(['memory foam pillow', 'cervical pillow'], {
  geo: 'US',
  lang: 'en',
  topN: 5,
});
console.timeEnd('discoverShop');

console.log('\n--- 메타데이터 ---');
console.log(result.metadata);

console.log('\n--- 샵 후보 (Google 검색량 순) ---');
result.shop_candidates.forEach((c, i) => {
  console.log(
    `${i + 1}. ${c.keyword} | 검색량:${c.volume} | KD:${c.kd} | ` +
    `점수:${c.score?.toFixed(0)} | 소싱가능 상품:${c.amazon_products?.length || 0}개`
  );
  c.amazon_products?.slice(0, 2).forEach((p) =>
    console.log(`     └ ${p.asin} BSR:${p.bsr} $${p.current_price} ⭐${p.rating}`)
  );
});

console.log(`\n총 키워드 풀: ${result.all_keywords.length}개`);
console.log(
  result.metadata.google_volume_available
    ? '✅ Google 검색량 데이터 활성 (Basic Access 승인됨)'
    : '⚠️ Google 검색량 0 — Basic Access 승인 전 (승인 후 자동 활성)'
);
