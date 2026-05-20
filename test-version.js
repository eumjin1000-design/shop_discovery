import axios from 'axios';
import 'dotenv/config';

const r = await axios.post('https://oauth2.googleapis.com/token', {
  client_id:     process.env.GOOGLE_ADS_CLIENT_ID,
  client_secret: process.env.GOOGLE_ADS_CLIENT_SECRET,
  refresh_token: process.env.GOOGLE_ADS_REFRESH_TOKEN,
  grant_type:    'refresh_token',
});
const token = r.data.access_token;
const CID = process.env.GOOGLE_ADS_CUSTOMER_ID;

console.log('=== 버전별 테스트 ===');
for (const ver of ['v20', 'v19', 'v18', 'v17', 'v16']) {
  const url = `https://googleads.googleapis.com/${ver}/customers/${CID}:generateKeywordIdeas`;
  try {
    const res = await axios.post(url, {
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
    console.log(`✅ ${ver}: 결과 ${res.data.results?.length}개`);
    console.log(`   첫 번째: ${res.data.results?.[0]?.text}`);
  } catch(e) {
    const msg = e.response?.data?.error?.message || e.response?.data?.toString().slice(0,50) || e.message;
    console.log(`❌ ${ver}: ${e.response?.status} - ${msg}`);
  }
}
