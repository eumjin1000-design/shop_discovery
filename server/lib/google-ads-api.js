import 'dotenv/config';
import axios from 'axios';

const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const ADS_BASE  = 'https://googleads.googleapis.com/v19';

async function getAccessToken() {
  const { data } = await axios.post(TOKEN_URL, {
    client_id:     process.env.GOOGLE_ADS_CLIENT_ID,
    client_secret: process.env.GOOGLE_ADS_CLIENT_SECRET,
    refresh_token: process.env.GOOGLE_ADS_REFRESH_TOKEN,
    grant_type:    'refresh_token',
  });
  return data.access_token;
}

export async function getKeywordData(keywords, geo = 'US', lang = 'en') {
  const GEO  = { US: '2840', KR: '2410', GB: '2826' };
  const LANG = { en: '1000', ko: '1012' };
  const accessToken = await getAccessToken();
  const url = `${ADS_BASE}/customers/${process.env.GOOGLE_ADS_CUSTOMER_ID}:generateKeywordIdeas`;
  const { data } = await axios.post(url, {
    keywordSeed:        { keywords },
    geoTargetConstants: [`geoTargetConstants/${GEO[geo] || '2840'}`],
    language:           `languageConstants/${LANG[lang] || '1000'}`,
    keywordPlanNetwork: 'GOOGLE_SEARCH',
  }, {
    headers: {
      Authorization:       `Bearer ${accessToken}`,
      'developer-token':   process.env.GOOGLE_ADS_DEVELOPER_TOKEN,
      'login-customer-id': process.env.GOOGLE_ADS_LOGIN_CUSTOMER_ID,
      'Content-Type':      'application/json',
    },
  });
  return (data.results || []).map(r => {
    const m = r.keywordIdeaMetrics || {};
    return {
      keyword:  r.text,
      volume:   Number(m.avgMonthlySearches  || 0),
      kd:       Number(m.competitionIndex    || 0),
      cpc_low:  Number(m.lowTopOfPageBidMicros  || 0) / 1_000_000,
      cpc_high: Number(m.highTopOfPageBidMicros || 0) / 1_000_000,
    };
  });
}
