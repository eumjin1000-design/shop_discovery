# Shop Discovery — Gemini AI용 전체 시스템 설명서

> 작성일: 2026-05-21 · 대상: Gemini가 이 프로젝트 전체를 처음부터 이해
> 이 문서 하나로 시스템 전모를 파악할 수 있도록 self-contained로 작성됨.
> (Claude용 상세 참조는 `ARCHITECTURE.md`, 운영 규칙은 `CLAUDE.md`)

---

## 0. 한 문장 요약

**드랍쇼핑 신규 샵을 자동 발굴하는 도구.** 카테고리/키워드를 입력하면 → 시장성 분석(100점 Go/No-Go) → 소싱할 Amazon 상품 URL 생성 → Spark 스크래퍼로 실제 상품 수집 → Shopify 등록까지 이어지는 파이프라인.

---

## 1. 두 개의 독립 스택

이 프로젝트는 **언어가 다른 2개 시스템**으로 구성됩니다. 헷갈리지 마세요.

| 스택 | 언어 | 역할 | 진입점 |
|---|---|---|---|
| **메인 앱** | Python | 카테고리 분석 + 소싱 리스트 + GUI | `app.py` (Streamlit), `main.py` (CLI) |
| **키워드 리서치** | Node.js | Google 검색량 + Keepa 제품 소싱 + HTTP API | `server/index.js` (Express) |

- 두 스택은 **HTTP API로 느슨하게 연결**됩니다 (Streamlit이 `localhost:8787`의 Node API 호출).
- **자매 도구** `spark_collector` (D:\스파크배포용\, 별도 Node.js 프로젝트)는 생성된 URL로 실제 Amazon ASIN을 크롤링.

---

## 2. 전체 워크플로우 (사용자 관점)

```
[전략] Google 검색량 = 샵 선정 메인 기준 / Keepa = 제품 소싱 보조

1. 키워드 리서치 (Node.js, 선택)
   시드 키워드 → Google 검색량/KD → 보석 키워드(gems) → 어느 샵 만들지 결정

2. 카테고리 분석 (Python Streamlit)
   카테고리 입력 → 7단계 분석 → 100점 → GO/WATCH/NO-GO

3. 소싱 리스트 생성 (GO 카테고리)
   서브카테고리 × 상품 × 변형 × 페이지 → Amazon 검색 URL .txt

4. ASIN 수집 (spark_collector)
   .txt → Playwright 크롤링 → 실제 ASIN + BSR/가격/평점

5. Shopify 등록 → 콘텐츠 SEO → 첫 매출
```

---

## 3. Python 메인 앱 — 7단계 분석 파이프라인

`main.run_pipeline(category, target_market="US", currency="USD") → PipelineResult`

```
DiscoveryRequest(category)
 → [1] keyword_gen.generate_keywords   키워드 8개 (LLM)
 → [2] trend_check.check_trend         검색량/성장률/계절성 (Keywords Everywhere or mock)
 → [3] amazon_bsr.check_bsr            BSR·경쟁 리스팅 (Keepa or mock)
 → [4] review_miner.mine_reviews       평점·리뷰·불만테마 (Keepa+LLM or mock)
 → [5] intent_check.check_intent       구매의도 + 구매연령대 (LLM)
 → [6] margin_calc.calc_margin         단위 손익 (항상 시드 mock)
 → [7] synthesizer.synthesize          100점 → Verdict
 → PipelineResult
```

**데이터 우선순위**: 실 API → 실패 시 mock. mock은 `seeded_rng(태그, 카테고리)`로 카테고리당 항상 같은 값(재현 가능). 각 결과의 `notes`에 `[실데이터: Keepa]` / `[mock data]` 출처 표기.

### 100점 스코어링 (`synthesizer.py`)

| 항목 | 배점 | 산정 요약 |
|---|---|---|
| 마진/단위 경제성 💰 | **35** | 순마진 35%↑ 만점 (드랍쇼핑 핵심) |
| 검색 트렌드 📈 | 20 | 성장률 + 안정성, 계절성 -2 |
| 시장 및 경쟁(BSR) 🏪 | 20 | BSR 수요 12 + 경쟁 리스팅 8 |
| 리뷰 기회 ⭐ | 15 | 기존 평점 ~3.8/5에서 최대(불만족=기회) |
| 구매 의도 🛒 | 10 | 상업의도 + 문제인지도 |

판정: **≥70 GO** / 50-69 WATCH / <50 NO-GO

**광고/무광고 2종 가중치** (`ranking_modes.py`): 광고 없는 SEO 전략에선 마진 35→30, 시장 20→25로 재조정. 배치 순위 테이블에 두 순위 동시 표시.

---

## 4. LLM 하이브리드 (`modules/llm.py`)

- **모든 tier가 Claude 우선 → Gemini Flash 폴백** (사용자 Claude $100 크레딧 소진 목적)
- 모델: Claude `claude-sonnet-4-6`, Gemini `gemini-2.0-flash`
- `ask_json()` / `ask_text(tier="fast"|"quality")`
- 호출부는 `None` 반환 시 결정론적 폴백(휴리스틱/템플릿/mock). 예외 절대 전파 안 함.
- JSON 파서: 코드펜스 strip + 잘린 배열 복원(bracket-depth 트래커)
- 진단 로그: `[LLM][claude] {에러타입}` 형식으로 Cloud Logs에 노출

---

## 5. Keepa 통합 + 토큰 관리 (핵심)

Keepa = Amazon 상품 데이터(BSR/가격/평점/리뷰). **Pro 플랜 1 token/min** 제약이 커서 정교한 토큰 관리 적용.

### 4중 토큰 방어 구조

```
1. 사전 경고 (app_keepa_ui.preflight_banner)
   "이 작업 ~N토큰 든다, 현재 M토큰" 실행 전 표시
2. 디스크 캐시 (modules/keepa_cache.py, 24h)
   같은 카테고리/ASIN 재조회 = 0토큰 (재배포 생존)
3. 자동 백오프 (modules/keepa_status.should_use_keepa, <5토큰)
   토큰 부족 시 자동으로 mock 폴백
4. 실시간 모니터 (app_keepa_ui.render_sidebar)
   사이드바: 현재 잔량 + 회복 ETA + 시간대별 차트
```

### 토큰 최적화 (적용됨)

- `stats=90 → 30`: 호출당 ~30% 절감
- 스냅샷 샘플 20 → 15: ~25% 절감
- 디스크 캐시: 반복 작업 ~100% 절감
- Node.js 측 ASIN 24h 캐시

### Keepa stats.current 인덱스 (검증됨)

```
[0] Amazon price (cents, -1이면 [1] New로 폴백)
[3] BSR (sales rank)
[16] rating × 10
[17] review count
```

---

## 6. Node.js 키워드 리서치 시스템 (Step 1-5)

사용자 전략(Google 검색량 우선)을 코드화한 2단계 파이프라인.

### 데이터 흐름

```
[HTTP API] POST /api/keywords/research          ← server/routes/keywords.js
     ↓
[오케스트레이터] shop-pipeline.discoverShop
     │
     ├─ 1단계: Google 검색량 → 샵 선정
     │    keyword-pipeline.researchKeywords
     │      ├─ google-suggest (시드 → ~10개 확장, 무료)
     │      ├─ 데이터소스 (아래 우선순위)
     │      └─ keyword-cache (SQLite)
     │    → gems = opportunity(volume/(KD+1)) 랭킹
     │
     └─ 2단계: 선정 샵 → Keepa 제품 소싱 (top-N gems만)
          keepa-validator.validateKeywordsWithKeepa
          → 각 gem에 amazon_products[] (BSR≤50k)
```

### 키워드 데이터소스 우선순위 (중요)

```
1순위: RapidAPI "Google Keyword Insight" (rapidapi-keywords.js)
   - RAPIDAPI_KEY 있으면 사용
   - 시드 1개 → ~100-300개 키워드 확장 + volume/KD/CPC
   - Google Ads Basic Access 불필요 (즉시 사용)
   - 응답: {text, volume, competition_index(=KD), low_bid, high_bid, trend}

2순위: Google Ads API (google-ads-api.js)
   - Basic Access 승인 필요 (현재 대기 중)
   - RAPIDAPI_KEY 없을 때 폴백
```

`metadata.data_source` 필드가 어느 소스를 썼는지 표시.

### gems 기준

- opportunity_score = volume / (KD + 1)
- 보석 필터: **KD ≤ 30 AND volume ≥ 1000** (상위 50개)
- KD 배지: ≤30 💎 / ≤60 ⭐ / >60 🔴

### HTTP API 엔드포인트

| 엔드포인트 | 설명 |
|---|---|
| `GET /health` | liveness |
| `POST /api/keywords/research` | seeds → gems(+Keepa). body: `{seeds, market, language, validate_with_keepa, top_n}` |
| `GET /api/keywords/cache/stats` | 캐시 hit_rate |

응답 envelope: `{success, data}` 또는 `{success:false, error, code}`.
에러 코드: `VALIDATION_ERROR`(400) / `TIMEOUT`(504) / `INTERNAL_ERROR`(500).

### 실행

```bash
npm run serve          # node server/index.js → http://localhost:8787
node test-rapidapi.js  # RapidAPI 단독 테스트
node test-step5.js     # HTTP API 통합 테스트
```

---

## 7. 소싱 리스트 생성 (`modules/sourcing.py`)

`generate_sourcing_list(category, n_subs, n_variants, passes, pages, verify_urls)`

```
LLM이 서브카테고리 생성 (passes회 호출, dedup)
  ↓
서브 × 5상품 × n_variants × pages 행
  ↓
.xlsx (11열) + .txt (카테고리|서브카테고리|URL, Spark 입력용)
```

- Amazon URL: 노드ID 있으면 `s?keywords=...&rh=n:노드,AFN,Prime&c=ts&s=review-count-rank`, 없으면 `s?k=...`
- `&page=N`으로 페이지 사전 확장 (Spark가 페이지네이션 불필요)
- 🚀 정확도 최대 프리셋: 서브 15 · 변형 10 · 페이지 5 → 최대 750 URL

---

## 8. 데이터 백업 / 복원 (앱 업데이트 생존)

**문제**: 영속 JSON 파일들이 gitignore라 Streamlit Cloud 새 컨테이너 배포 시 소실 가능.

**해결** (`app_backup_ui.py` + `categories.export_all_state/import_all_state`):

```
🗂️ 데이터 백업 / 복원 (분석 폼 위 익스팬더)
   ↩ 이전 목록 복원      — *.bak.json 인앱 복원 (같은 컨테이너 내)
   💾 전체 백업 다운로드  — 5개 파일을 단일 JSON으로 (재배포 생존) ⭐
   📤 백업 파일 복원      — 그 JSON 업로드 → 전체 복구
```

→ 다운로드/업로드만이 재배포 후 100% 복원 보장 (파일이 사용자 PC에 있으므로).

---

## 9. Streamlit GUI 구조

### 메인 페이지 (`app.py`)

```
1. 헤더 — 🐙 샵 디스커버리 + LLM 배지 + 🪙 Keepa 토큰 배지
2. 사이드바 — 🪙 Keepa 토큰 모니터 (잔량/차트/백오프 상태)
3. 통계 카드 3열 — 전체/GO/분석완료
4. 카테고리 카드 그리드 (3열, 이모지+★등급+연령배지) + ↩ 이전 목록 복원 + ✨ AI 새목록
5. 🗂️ 백업/복원 익스팬더
6. 버튼 — 🎲 랜덤 / ▷ 전체 분석 (preflight 토큰 경고)
7. 단일 분석 폼
8. 분석 결과 — 게이지 + 스코어카드 + 전략기준 + GO 도구(샵이름/소싱/Spark)
9. 배치 순위 테이블 — 광고/무광고 2순위 + EN/한글 카테고리
```

### 서브 페이지 (`pages/`)

- `pages/1_🔍_키워드_리서치.py` — Node API 호출 키워드 리서치 (Streamlit 멀티페이지, 사이드바 네비)
  - ⚠️ localhost API라 **로컬 전용** (Cloud에선 연결 실패 안내)

---

## 10. 외부 API / 환경변수 (`.env`)

```
# Python 메인 앱
ANTHROPIC_API_KEY        Claude Sonnet
GOOGLE_API_KEY           Gemini Flash (무료)
GEMINI_MODEL             gemini-2.0-flash (선택)
KEEPA_API_KEY            Keepa (Pro, Amazon BSR/가격/평점)
KW_EVERYWHERE_API_KEY    Keywords Everywhere (검색량)

# Node.js 키워드 시스템
RAPIDAPI_KEY             RapidAPI Google Keyword Insight (검색량/KD, 즉시 사용)
RAPIDAPI_KEYWORD_HOST    google-keyword-insight1.p.rapidapi.com
GOOGLE_ADS_DEVELOPER_TOKEN  Google Ads (Basic Access 대기 중, RapidAPI로 대체)
GOOGLE_ADS_CLIENT_ID / _SECRET / _REFRESH_TOKEN
GOOGLE_ADS_CUSTOMER_ID / _LOGIN_CUSTOMER_ID
KEYWORD_API_BASE         Streamlit→Node API 베이스 (기본 localhost:8787)
```

`여기에...`로 시작하는 값 = "미설정"으로 취급.
모든 API 키 없어도 작동 (mock/폴백).

---

## 11. 핵심 파일 맵 (빠른 참조)

### Python (`modules/` + 루트)

| 파일 | 역할 |
|---|---|
| `app.py` / `main.py` | Streamlit GUI / CLI 진입점 |
| `app_render.py` | 결과 렌더 (게이지/스코어바/배치테이블) |
| `app_go_tools.py` | GO 도구 (샵이름 + 소싱 컨트롤) |
| `app_keepa_ui.py` | Keepa 배지/사이드바/preflight |
| `app_backup_ui.py` | 백업/복원 UI |
| `app_keyword_research.py` | 키워드 리서치 페이지 (Node API 클라이언트) |
| `modules/synthesizer.py` | 100점 스코어 → Verdict |
| `modules/sourcing.py` + `sourcing_llm.py` | 소싱 리스트 생성 |
| `modules/sources.py` | Keepa/Keywords Everywhere (timeout + 백오프) |
| `modules/keepa_status.py` | 토큰 폴링/백오프/이력/비용추정 |
| `modules/keepa_cache.py` | Keepa 결과 디스크 캐시 (24h) |
| `modules/categories.py` | 카테고리 목록 + 이력 + 백업 export/import |
| `modules/category_ko.py` | 영문→한글 번역 |
| `modules/ranking_modes.py` | 광고/무광고 2종 가중치 |

### Node.js (`server/`)

| 파일 | 역할 |
|---|---|
| `server/index.js` | Express 5 서버 엔트리 |
| `server/routes/keywords.js` | API 라우트 2개 |
| `server/lib/rapidapi-keywords.js` | RapidAPI 검색량/KD (1순위 소스) |
| `server/lib/google-ads-api.js` | Google Ads (2순위 폴백) |
| `server/lib/google-suggest.js` | 무료 키워드 확장 |
| `server/lib/keyword-pipeline.js` | gems 파이프라인 |
| `server/lib/keepa-validator.js` | Keepa 제품 검증 |
| `server/lib/shop-pipeline.js` | 2단계 오케스트레이터 |
| `server/lib/keyword-cache.js` | SQLite 캐시 |

---

## 12. 알려진 제약 / 현재 상태

| 항목 | 상태 |
|---|---|
| **margin_calc** | 항상 mock (실 소싱가 미연동, 35점 비중이라 실데이터화가 최우선 개선) |
| **Google Ads API** | Basic Access 승인 대기 (2026-05-20 신청) → RapidAPI로 우회 중 |
| **RapidAPI** | 무료 BASIC = **월 20회** 한도. 소진 시 429(~31일 리셋). 신규 키/업그레이드 필요. 코드는 검증 완료 |
| **Keepa** | Pro 1 token/min — 캐시+백오프로 최소 사용 |
| **키워드 리서치 페이지** | localhost API라 로컬 전용 (Cloud 미지원) |
| **HF dataset** | 2023-09 기준, ASIN ~30% 단종 가능 |

---

## 13. 명령어 모음

```bash
# Python 메인 앱
streamlit run app.py            # GUI
python main.py "memory foam pillow"   # CLI
python -m pytest tests/ -q      # 회귀 테스트 (20개)

# Node.js 키워드 시스템
npm run serve                   # API 서버 (localhost:8787)
node test-rapidapi.js           # RapidAPI 테스트
node test-step5.js              # API 통합 테스트

# Git (Cloud 자동 재배포)
git add -A && git commit -m "..." && git push origin main
```

---

## 14. 사용자(jin) 컨텍스트

- 드랍쇼핑 솔로 운영자, 미국 타겟
- 5개 샵 계획 (광고 없이 시작 → 매출 후 광고)
- 전략: **Google 검색량 = 샵 선정 메인 / Keepa = 제품 소싱 보조**
- 현재 1순위 카테고리: Memory Foam Pillows (88.1점 GO)
- 자매 도구: spark_collector (ASIN 크롤러), ShopCloner (Shopify 임포트)
- Cloud 배포: `shopdiscovery-w4vh6puhwewxiqfv9ksouj.streamlit.app`
- Git: `eumjin1000-design/shop_discovery`

---

## 15. Gemini가 작업 요청받으면

1. 이 문서 + `ARCHITECTURE.md` + `CLAUDE.md` 통독
2. 코드 파일은 **300줄 하드 한도** (`.md`/`.json` 제외) — 넘으면 모듈 분리
3. 코드 주석 = 영어, 커밋 = 한국어, 응답 = 한국어
4. 새 기능 → 회귀 테스트(`tests/`) 추가
5. API 키는 `.env`에서만 로드 (하드코딩 금지)
6. Keepa 호출 전 `should_use_keepa()` 백오프 체크
7. 푸시 후 Cloud 1-2분 재배포 대기

---

문서 끝.
