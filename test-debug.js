import axios from 'axios';
import 'dotenv/config';

console.log('=== Access Token 발급 ===');
let token;
try {
  const r = await axios.post('https://oauth2.googleapis.com/token', {
    client_id:     process.env.GOOGLE_ADS_CLIENT_ID,
    client_secret: process.env.GOOGLE_ADS_CLIENT_SECRET,
    refresh_token: process.env.GOOGLE_ADS_REFRESH_TOKEN,
    grant_type:    'refresh_token',
  });
  token = r.data.access_token;
  console.log('✅ 성공:', token.slice(0,30)+'...');
} catch(e) {
  console.log('❌ 실패:', e.response?.data);
  process.exit(1);
}

console.log('\n=== Keyword API 호출 ===');
const url = `https://googleads.googleapis.com/v19/customers/${process.env.GOOGLE_ADS_CUSTOMER_ID}:generateKeywordIdeas`;
console.log('URL:', url);

try {
  const r = await axios.post(url, {
    keywordSeed: { keywords: ['korean skincare'] },
    geoTargetConstants: ['geoTargetConstants/2840'],
    language: 'languageConstants/1000',
    keywordPlanNetwork: 'GOOGLE_SEARCH',
  }, {
    headers: {
      Authorization:       `Bearer ${token}`,
      'developer-token':   process.env.GOOGLE_ADS_DEVELOPER_TOKEN,
      'login-customer-id': process.env.GOOGLE_ADS_LOGIN_CUSTOMER_ID,
      'Content-Type':      'application/json',
    },
  });
  console.log('✅ 결과:', r.data.results?.length, '개');
  console.log('첫 번째:', r.data.results?.[0]?.text);
} catch(e) {
  console.log('❌ Status:', e.response?.status);
  console.log('❌ Error:', JSON.stringify(e.response?.data, null, 2));
}
