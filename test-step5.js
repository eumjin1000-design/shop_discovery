import axios from 'axios';

const BASE = `http://localhost:${process.env.PORT || 8787}`;

console.log('=== 기본 키워드 리서치 ===');
const r1 = await axios.post(`${BASE}/api/keywords/research`, {
  seeds: ['korean skincare', 'snail mucin'],
  market: 'US',
  language: 'en',
});
console.log('성공:', r1.data.success);
console.log('총 키워드:', r1.data.data.all.length);
console.log('보석:', r1.data.data.gems.length);
console.log('메타:', r1.data.data.metadata);

console.log('\n=== Keepa 포함 테스트 ===');
const r2 = await axios.post(`${BASE}/api/keywords/research`, {
  seeds: ['memory foam pillow'],
  validate_with_keepa: true,
  top_n: 3,
});
console.log('성공:', r2.data.success);
console.log('첫 번째 gem:', r2.data.data.gems[0]);

console.log('\n=== 캐시 통계 ===');
const r3 = await axios.get(`${BASE}/api/keywords/cache/stats`);
console.log(r3.data);

console.log('\n=== 에러 처리 테스트 ===');
try {
  await axios.post(`${BASE}/api/keywords/research`, {});
} catch (e) {
  console.log('에러 코드:', e.response?.data?.code);
  console.log('에러 메시지:', e.response?.data?.error);
}
