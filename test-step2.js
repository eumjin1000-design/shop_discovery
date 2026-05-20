import { suggestKeywords } from './server/lib/google-suggest.js';
import { researchKeywords } from './server/lib/keyword-pipeline.js';

// Suggest 단독 테스트
const suggestions = await suggestKeywords('korean skincare');
console.log('Suggest 결과:', suggestions.length, '개');
console.log('샘플:', suggestions.slice(0, 5));

// 파이프라인 전체 테스트
console.time('pipeline');
const result = await researchKeywords(['korean skincare', 'snail mucin']);
console.timeEnd('pipeline');

console.log('\n총 키워드:', result.all.length);
console.log('보석 TOP 5:');
result.gems.slice(0, 5).forEach(g =>
  console.log(` ${g.keyword} | 검색량:${g.volume} | KD:${g.kd} | 점수:${g.score?.toFixed(0)}`)
);
console.log('메타:', result.metadata);
