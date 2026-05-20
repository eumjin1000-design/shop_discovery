import {
  searchKeepaByKeyword,
  validateProductsByASIN,
  validateKeywordsWithKeepa,
} from './server/lib/keepa-validator.js';

// 테스트 1: ASIN 검색
console.log('=== Keepa 키워드 검색 ===');
const asins = await searchKeepaByKeyword('korean skincare', 5);
console.log('ASIN 수:', asins.length);
console.log('ASINs:', asins);

// 테스트 2: 상품 상세 조회
if (asins.length > 0) {
  console.log('\n=== 상품 상세 조회 ===');
  const products = await validateProductsByASIN(asins);
  products.slice(0, 2).forEach(p =>
    console.log(`${p.asin} | BSR:${p.bsr} | $${p.current_price} | 리뷰:${p.review_count}`)
  );
}

// 테스트 3: 파이프라인 통합
console.log('\n=== 파이프라인 통합 테스트 ===');
const mockGems = [
  { keyword: 'hydrocolloid pimple patches', volume: 50000, kd: 4, score: 10000 },
  { keyword: 'korean skincare brands', volume: 500000, kd: 16, score: 29411 },
];
const validated = await validateKeywordsWithKeepa(mockGems);
validated.forEach(g => {
  console.log(`\n💎 ${g.keyword}`);
  g.amazon_products?.slice(0, 2).forEach(p =>
    console.log(`   BSR:${p.bsr} | $${p.current_price} | ⭐${p.rating} (${p.review_count}리뷰)`)
  );
});
