/**
 * Permission-fix matrix.
 *
 * Tries all sensible (customer_id, login_customer_id) combinations against
 * v20 generateKeywordIdeas, prints the verdict for each. The first ✅ is
 * the .env layout to use.
 */
import axios from 'axios';
import 'dotenv/config';

const BASE = 'https://googleads.googleapis.com/v20';
const DEV = process.env.GOOGLE_ADS_DEVELOPER_TOKEN;
const STANDALONE = '3036301113';   // direct-access account
const MANAGER    = '4572157919';   // Jin SEO Tools (manager=true)

async function token() {
  const r = await axios.post('https://oauth2.googleapis.com/token', {
    client_id:     process.env.GOOGLE_ADS_CLIENT_ID,
    client_secret: process.env.GOOGLE_ADS_CLIENT_SECRET,
    refresh_token: process.env.GOOGLE_ADS_REFRESH_TOKEN,
    grant_type:    'refresh_token',
  });
  return r.data.access_token;
}

async function probe(t, label, cid, login) {
  const headers = {
    Authorization:     `Bearer ${t}`,
    'developer-token': DEV,
    'Content-Type':    'application/json',
  };
  if (login) headers['login-customer-id'] = login;

  try {
    const r = await axios.post(`${BASE}/customers/${cid}:generateKeywordIdeas`, {
      keywordSeed: { keywords: ['korean skincare'] },
      geoTargetConstants: ['geoTargetConstants/2840'],
      language: 'languageConstants/1000',
      keywordPlanNetwork: 'GOOGLE_SEARCH',
    }, { headers });
    const n = r.data.results?.length || 0;
    const first = r.data.results?.[0];
    console.log(`\n✅ ${label}`);
    console.log(`   cid=${cid}  login=${login || '(omitted)'}`);
    console.log(`   results=${n}  first="${first?.text}"  vol=${first?.keywordIdeaMetrics?.avgMonthlySearches}`);
    return { ok: true, label, cid, login, n };
  } catch (e) {
    const detail = e.response?.data?.error?.details?.[0]?.errors?.[0];
    const code   = detail?.errorCode ? JSON.stringify(detail.errorCode) : '';
    const msg    = detail?.message || e.response?.data?.error?.message || e.message;
    console.log(`\n❌ ${label}`);
    console.log(`   cid=${cid}  login=${login || '(omitted)'}`);
    console.log(`   status=${e.response?.status}  code=${code}`);
    console.log(`   msg=${String(msg).slice(0, 160)}`);
    return { ok: false, label, cid, login, status: e.response?.status };
  }
}

const t = await token();
console.log('OAuth token acquired.');
console.log(`STANDALONE=${STANDALONE}  MANAGER=${MANAGER}`);

const matrix = [
  ['1A. CID=STANDALONE, login=(omitted)', STANDALONE, null],
  ['1B. CID=STANDALONE, login=STANDALONE', STANDALONE, STANDALONE],
  ['2A. CID=MANAGER,    login=MANAGER',    MANAGER,    MANAGER],
  ['2B. CID=MANAGER,    login=(omitted)',  MANAGER,    null],
  ['3.  CID=STANDALONE, login=MANAGER  (current, fails)', STANDALONE, MANAGER],
];

const summary = [];
for (const [label, cid, login] of matrix) {
  summary.push(await probe(t, label, cid, login));
}

console.log('\n=== 요약 ===');
for (const s of summary) {
  const tag = s.ok ? '✅' : `❌ ${s.status}`;
  console.log(`  ${tag.padEnd(8)} ${s.label}`);
}

const win = summary.find(s => s.ok);
console.log('\n=== 권장 .env ===');
if (win) {
  console.log(`GOOGLE_ADS_CUSTOMER_ID=${win.cid}`);
  if (win.login) {
    console.log(`GOOGLE_ADS_LOGIN_CUSTOMER_ID=${win.login}`);
  } else {
    console.log(`GOOGLE_ADS_LOGIN_CUSTOMER_ID=  (비워두기 또는 줄 자체 삭제)`);
    console.log('  ↑ axios 코드에서 헤더 자체를 빼야 함 (빈 문자열 전송도 거부될 수 있음)');
  }
} else {
  console.log('❌ 모든 조합 실패. 다음 단계:');
  console.log('   - Developer Token 등급 확인 (Test → Basic/Standard 승인 필요)');
  console.log('   - Google Ads 콘솔에서 OAuth 사용자 권한 점검');
}
