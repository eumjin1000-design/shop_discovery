/**
 * Google Ads API permission diagnostic.
 *
 * Pinpoints exactly why v20 returns 403 by:
 *   1. Showing the full error body for generateKeywordIdeas (Google usually
 *      embeds an `errors[].errorCode` enum like USER_PERMISSION_DENIED,
 *      DEVELOPER_TOKEN_*, AUTHORIZATION_ERROR.* that reveals the cause).
 *   2. Calling listAccessibleCustomers WITHOUT login-customer-id — tells us
 *      which customer IDs the OAuth user actually owns/manages.
 *   3. Querying customers/{CID} via searchStream so we can see whether the
 *      target ID is a Manager (MCC) or a Client account.
 *   4. Querying customer_client under the LOGIN customer to map the parent
 *      → child relationship (or detect that there isn't one).
 */
import axios from 'axios';
import 'dotenv/config';

const BASE = 'https://googleads.googleapis.com/v20';
const CID = process.env.GOOGLE_ADS_CUSTOMER_ID;
const LOGIN = process.env.GOOGLE_ADS_LOGIN_CUSTOMER_ID;
const DEV = process.env.GOOGLE_ADS_DEVELOPER_TOKEN;

function pad(label) { return label.padEnd(38); }

async function token() {
  const r = await axios.post('https://oauth2.googleapis.com/token', {
    client_id:     process.env.GOOGLE_ADS_CLIENT_ID,
    client_secret: process.env.GOOGLE_ADS_CLIENT_SECRET,
    refresh_token: process.env.GOOGLE_ADS_REFRESH_TOKEN,
    grant_type:    'refresh_token',
  });
  return r.data.access_token;
}

function hdr(t, withLogin = true) {
  const h = {
    Authorization:     `Bearer ${t}`,
    'developer-token': DEV,
    'Content-Type':    'application/json',
  };
  if (withLogin && LOGIN) h['login-customer-id'] = LOGIN;
  return h;
}

function printErr(label, e) {
  console.log(`\n${pad(label)} ❌ status=${e.response?.status}`);
  const body = e.response?.data;
  if (typeof body === 'string') {
    console.log('  raw:', body.slice(0, 200));
  } else if (body) {
    console.log(JSON.stringify(body, null, 2));
  } else {
    console.log('  err:', e.message);
  }
}

console.log('=== 환경 ===');
console.log(`CUSTOMER_ID       : ${CID}`);
console.log(`LOGIN_CUSTOMER_ID : ${LOGIN}`);
console.log(`DEVELOPER_TOKEN   : ${DEV?.slice(0, 6)}...${DEV?.slice(-4)} (len=${DEV?.length})`);
console.log(`SAME(login==cust) : ${String(CID) === String(LOGIN)}`);

const t = await token();
console.log('\nOAuth token acquired.');

// ---------------------------------------------------------------------------
// 1. generateKeywordIdeas full error body
// ---------------------------------------------------------------------------
console.log('\n=== 1. generateKeywordIdeas (full error body) ===');
try {
  const r = await axios.post(`${BASE}/customers/${CID}:generateKeywordIdeas`, {
    keywordSeed: { keywords: ['korean skincare'] },
    geoTargetConstants: ['geoTargetConstants/2840'],
    language: 'languageConstants/1000',
    keywordPlanNetwork: 'GOOGLE_SEARCH',
  }, { headers: hdr(t) });
  console.log(`✅ unexpected success: ${r.data.results?.length} results`);
} catch (e) {
  printErr('generateKeywordIdeas', e);
}

// ---------------------------------------------------------------------------
// 2. listAccessibleCustomers — what does this OAuth user actually own?
// ---------------------------------------------------------------------------
console.log('\n=== 2. listAccessibleCustomers ===');
try {
  const r = await axios.get(`${BASE}/customers:listAccessibleCustomers`,
    { headers: hdr(t, false) });
  const names = r.data.resourceNames || [];
  console.log(`✅ ${names.length} accessible customer(s):`);
  for (const n of names) console.log(`   - ${n}`);
  console.log(`\n  Target CID ${CID} included? ${names.some(n => n.endsWith('/' + CID))}`);
  console.log(`  Login CID  ${LOGIN} included? ${names.some(n => n.endsWith('/' + LOGIN))}`);
} catch (e) {
  printErr('listAccessibleCustomers', e);
}

// ---------------------------------------------------------------------------
// 3. customer info — is CID a Manager (MCC) or a Client?
// ---------------------------------------------------------------------------
console.log('\n=== 3. customer info (manager?) — under LOGIN context ===');
try {
  const r = await axios.post(`${BASE}/customers/${LOGIN}/googleAds:searchStream`, {
    query: `
      SELECT customer.id, customer.descriptive_name, customer.manager,
             customer.currency_code, customer.status, customer.test_account
      FROM customer
    `,
  }, { headers: hdr(t) });
  const rows = (r.data[0]?.results || r.data.results || []).slice(0, 5);
  for (const row of rows) {
    console.log(`   id=${row.customer?.id}  manager=${row.customer?.manager}  test=${row.customer?.testAccount}  name="${row.customer?.descriptiveName}"  status=${row.customer?.status}`);
  }
  if (!rows.length) console.log('   (no rows returned)');
} catch (e) {
  printErr('customer searchStream', e);
}

// ---------------------------------------------------------------------------
// 4. customer_client — does LOGIN manage CID?
// ---------------------------------------------------------------------------
console.log('\n=== 4. customer_client (parent→child map) ===');
try {
  const r = await axios.post(`${BASE}/customers/${LOGIN}/googleAds:searchStream`, {
    query: `
      SELECT customer_client.client_customer, customer_client.id,
             customer_client.level, customer_client.manager,
             customer_client.test_account, customer_client.status,
             customer_client.descriptive_name
      FROM customer_client
      WHERE customer_client.level <= 1
    `,
  }, { headers: hdr(t) });
  const rows = (r.data[0]?.results || r.data.results || []);
  console.log(`✅ ${rows.length} child(ren) under ${LOGIN}:`);
  for (const row of rows.slice(0, 15)) {
    const cc = row.customerClient || {};
    const flag = String(cc.id) === String(CID) ? ' ← TARGET CID' : '';
    console.log(`   id=${cc.id}  lvl=${cc.level}  manager=${cc.manager}  test=${cc.testAccount}  status=${cc.status}  "${cc.descriptiveName}"${flag}`);
  }
  const found = rows.some(r => String(r.customerClient?.id) === String(CID));
  console.log(`\n  Target CID ${CID} found under ${LOGIN}? ${found}`);
} catch (e) {
  printErr('customer_client searchStream', e);
}

console.log('\n=== 진단 끝 ===');
