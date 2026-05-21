# Shop Discovery — 시스템 아키텍처 (Claude AI용 종합 참조)

> 작성일: 2026-05-20 · 대상: 신규 Claude 세션이 이 프로젝트를 콜드로 이해
> 언어 정책: 코드 주석 = 영어 · 커밋 = 한국어 · AI 응답 = 한국어
> 파일 한도: 코드 파일 300줄 하드 한도 (`.md`/`.json` 제외)

---

## 1. 프로젝트 한 줄 요약

**드랍쇼핑 신규 샵 발굴 자동화 도구.** 카테고리 입력 → 7단계 분석 파이프라인 → 100점 Go/No-Go 판정 → Excel 리포트 + Spark 스크래퍼용 .txt 생성.

- 진입점 3개: CLI (`main.py`) + Streamlit GUI (`app.py`) + Node.js HTTP API (`server/index.js`)
- 호스팅: 로컬 PC + Streamlit Cloud
- 외부 도구 연동: Spark 스크래퍼(Electron 앱), spark_collector(별도 Node.js 도구)
- **Node.js 키워드 리서치 시스템** (Step 1-5): Google 검색량 우선 샵 선정 → Keepa 제품 소싱. 22번 섹션 참조.

---

## 2. 전체 데이터 흐름

```
[사용자] 카테고리 입력 (예: "Memory Foam Pillows")
   │
   ▼
[main.run_pipeline()] 7단계 분석
   ├─ 1. keyword_gen      → 키워드 8개 생성 (LLM fast)
   ├─ 2. trend_check      → 검색량/추세 (Keywords Everywhere or mock)
   ├─ 3. amazon_bsr       → BSR/경쟁 (Keepa or mock)
   ├─ 4. review_miner     → 평점/불만 (Keepa or mock + LLM)
   ├─ 5. intent_check     → 구매의도 + 연령대 (LLM fast)
   ├─ 6. margin_calc      → 단위 손익 (시드 mock)
   └─ 7. synthesizer      → 100점 스코어 → GO/WATCH/NO-GO
   │
   ▼
[PipelineResult] (불변 dataclass)
   │
   ├─→ [report_gen]     → 단일 분석 Excel
   ├─→ [batch_report]   → 배치 순위 Excel (광고/무광고 2개)
   ├─→ [shop_namer]     → GO 카테고리 샵 이름 5개 (LLM quality)
   └─→ [sourcing]       → 소싱 리스트 → sourcing_report → .xlsx + .txt
                                                              │
                                                              ▼
                                                  [Spark 또는 spark_collector]
                                                  실제 Amazon ASIN 수집
```

---

## 3. 디렉토리 구조

### 루트 진입점

| 파일 | 줄수 | 역할 |
|---|---|---|
| `app.py` | ~150 | Streamlit GUI 페이지 스크립트 |
| `app_render.py` | 230 | 결과 영역 렌더 헬퍼 (헤더/게이지/판정/스코어바/배치) |
| `app_go_tools.py` | 136 | GO 카테고리 도구 (샵이름 + 소싱 컨트롤) |
| `app_catalog_ui.py` | 150 | 카테고리 카드 그리드 + 통계 카드 |
| `app_bulk.py` | 181 | 대량 소싱 모드 UI (4-way radio) |
| `app_targeted_spark.py` | 95 | 🎯 이 카테고리 Spark URL 섹션 |
| `app_spark_ui.py` | - | Spark 임포트/병합 섹션 |
| `app_keepa_ui.py` | 158 | Keepa 배지 + 사이드바 토큰 모니터 + preflight 경고 |
| `app_keyword_research.py` | 194 | 키워드 리서치 페이지 (Node API 클라이언트) |
| `pages/1_🔍_키워드_리서치.py` | 21 | Streamlit 멀티페이지 래퍼 |
| `main.py` | - | CLI + run_pipeline/run_categories/run_all_curated |
| `make_icon.py` | - | Pillow로 데스크탑 아이콘 생성 (일회성) |

### 분석 파이프라인 (`modules/`)

| 파일 | 줄수 | 역할 |
|---|---|---|
| `models.py` | - | 불변 dataclass (DiscoveryRequest, Keyword, *Result, Verdict, PipelineResult, IntentResult.primary_age 등) |
| `llm.py` | 230 | 하이브리드 LLM (Claude→Gemini), 진단 로그, JSON 파서 (잘림 복원) |
| `util.py` | - | seeded_rng(시드 결정론적 RNG), clamp() |
| `timez.py` | - | KST 타임스탬프 (`stamp()`, `now_kst()`) |
| `curated_data.py` | - | CuratedCategory dataclass (name/margin/demand/competition/reason/age) + CURATED 20개 시드 |
| `categories.py` | - | 활성 카테고리 + AI 새목록 생성 + 분석 이력 + 배치 결과 영속화 |
| `category_ko.py` | 146 | 영문 카테고리명 → 한글 번역 (dict + LLM 폴백 + JSON 캐시) |
| `sources.py` | - | Keywords Everywhere + Keepa (10초 timeout, ThreadPoolExecutor) |
| `keyword_gen.py` | - | [1] 카테고리 → 키워드 N개 |
| `trend_check.py` | - | [2] 검색량/성장률/안정성/계절성 |
| `amazon_bsr.py` | - | [3] BSR·경쟁 리스팅 수 |
| `review_miner.py` | - | [4] 평균 평점·리뷰·불만 테마 |
| `intent_check.py` | 84 | [5] 상업적 의도·문제 인지도 + primary_age |
| `margin_calc.py` | - | [6] 단위 손익 (PLATFORM_FEES dict) |
| `synthesizer.py` | - | [7] 100점 스코어 → GO/WATCH/NO-GO |
| `verdict_ai.py` | - | (선택) Claude로 한국어 판정 요약 3-4문장 |
| `ranking_modes.py` | 56 | 광고/무광고 2종 가중치 (NO_AD_WEIGHTS) |
| `report_gen.py` | - | 단일 분석 Excel (Summary/Scorecard/Keywords/Details) |
| `batch_report.py` | 75 | 배치 순위 Excel (광고순위/무광고순위/EN/한글/총점/판정/breakdown) |
| `shop_namer.py` | - | GO 카테고리 샵 이름 5개 (LLM quality) |
| `sourcing.py` | 222 | SourcingRow + generate_sourcing_list(passes/pages 지원) |
| `sourcing_llm.py` | 154 | LLM 멀티패스 + 폴백 spec + normalize |
| `sourcing_nodes.py` | - | Amazon 브라우즈 노드 ID DB (75+ 카테고리) |
| `sourcing_report.py` | - | Excel(11열) + Spark 일괄입력 .txt 동시 생성 |
| `spark_urls.py` | 188 | Spark-네이티브 URL 빌더 (`build_search_url(page=N)`) |
| `bulk_sourcing.py` | 224 | 직접 ASIN 모드 + spark_query_list(pages 지원) |
| `dataset_lookup.py` | - | HF 데이터셋 카테고리 매핑 + SQLite 조회 |
| `dataset_categories.py` | - | HF 카테고리 키워드 매핑 |
| `dataset_verify.py` | - | ASIN GET-stream 검증 (404/CAPTCHA 제거) |
| `spark_import.py` | - | Spark 출력 .csv 임포트 |
| `keepa_status.py` | 172 | Keepa /token 폴링 + should_use_keepa 백오프 + 이력 + 비용추정 |
| `keepa_cache.py` | 71 | Keepa 결과 디스크 영속 캐시 (24h TTL, 재시작 생존) |

### Node.js 키워드 리서치 (`server/`)

| 파일 | 줄수 | 역할 |
|---|---|---|
| `server/index.js` | 49 | Express 5 서버 엔트리 (/health + 라우터 마운트) |
| `server/routes/keywords.js` | 140 | POST /research + GET /cache/stats |
| `server/lib/rapidapi-keywords.js` | 98 | **RapidAPI Google Keyword Insight (1순위 소스, 즉시 사용)** |
| `server/lib/google-ads-api.js` | ~45 | Google Ads generateKeywordIdeas (2순위 폴백, Basic Access 필요) |
| `server/lib/google-suggest.js` | 98 | Google 무료 autocomplete 키워드 확장 |
| `server/lib/keyword-cache.js` | 129 | SQLite 키워드/ASIN 캐시 (maxAgeMs 파라미터) |
| `server/lib/keyword-pipeline.js` | 209 | 8단계 파이프라인 → gems (opportunity 랭킹) |
| `server/lib/keepa-validator.js` | 253 | Keepa 검색+제품 (24h 캐시 + 백오프) |
| `server/lib/shop-pipeline.js` | 87 | 2단계: Google 검색량 선정 → Keepa 소싱 |

### 테스트

| 파일 | 역할 |
|---|---|
| `tests/test_category_annotation.py` | 괄호 누수 방지 회귀 (8개) |
| `tests/test_pages_passes.py` | passes/pages 확장 회귀 (12개) |

### 영속 파일 (gitignored)

```
generated_categories.json    AI 새목록
generated_categories.bak.json 직전 백업
analysis_history.json        {카테고리: 판정}
analysis_history.bak.json    직전 백업
batch_results.json           마지막 배치 순위 경량 데이터
category_ko_cache.json       한글 번역 캐시
output/*.xlsx                생성된 리포트
output/*.txt                 Spark 일괄입력
amazon_reviews.db            HF 데이터셋 SQLite (~1GB, 로컬만)
.env                         API 키 (실제 사용 중)
```

---

## 4. 7단계 파이프라인 상세

```python
DiscoveryRequest(category, target_market="US", currency="USD")
 → keyword_gen.generate_keywords(req, n=8)         → tuple[Keyword]
 → trend_check.check_trend(cat, keywords)          → TrendResult
 → amazon_bsr.check_bsr(cat, keywords)             → BSRResult
 → review_miner.mine_reviews(cat, keywords)        → ReviewResult
 → intent_check.check_intent(cat, keywords)        → IntentResult (primary_age 포함)
 → margin_calc.calc_margin(cat, currency)          → MarginResult
 → synthesizer.synthesize(...)                     → Verdict
 → PipelineResult(request, keywords, *results, verdict)
```

**데이터 소스 우선순위**: 실 API → mock. 각 Result.notes에 `[실데이터: Keepa]` 또는 `[mock data — set ..._API_KEY]` 표기.

**배치 함수**:
- `run_categories(names, progress=None)` — 지정 카테고리 순차 실행 + ETA 콜백
- `run_all_curated(progress, only_unanalyzed)` — 전체 또는 미분석분만

---

## 5. 스코어링 (100점, `synthesizer.py`)

### 기본 (광고 활용) 가중치

| 항목 | 영문 키 | 한글 라벨 | 배점 | 산정 |
|---|---|---|---|---|
| 마진 | Margin / unit economics | 마진/단위 경제성 💰 | **35** | `clamp(net_margin_pct / 0.35) * 35` |
| 트렌드 | Search trend | 검색 트렌드 📈 | **20** | 성장 14 + 안정성 6, 계절성 -2 |
| 시장 | Market & competition (BSR) | 시장 및 경쟁(BSR) 🏪 | **20** | 수요(BSR) 12 + 경쟁(리스팅) 8 |
| 리뷰 | Review opportunity | 리뷰 기회 ⭐ | **15** | `clamp(1 - |rating-3.8|/1.5) * 15` |
| 의도 | Purchase intent | 구매 의도 🛒 | **10** | 상업×7 + 문제인지도×3 |

**판정**: ≥70 GO / 50-69 WATCH / <50 NO-GO

### 무광고 가중치 (`ranking_modes.NO_AD_WEIGHTS`)

| 항목 | 광고 | 무광고 | 변화 |
|---|---|---|---|
| 마진 | 35 | **30** | -5 |
| 트렌드 | 20 | 20 | - |
| 시장 | 20 | **25** | +5 |
| 리뷰 | 15 | 15 | - |
| 의도 | 10 | 10 | - |

→ SEO/콘텐츠 전략에서는 경쟁 낮은 카테고리 우선. 점수 재계산은 `ranking_modes.no_ad_score(breakdown)`.

---

## 6. LLM 하이브리드 전략 (`modules/llm.py`)

### Tier 시스템

```python
_TIER_ORDER = {
    "fast":    (_call_claude, _call_gemini),   # Claude → Gemini 폴백
    "quality": (_call_claude, _call_gemini),   # 둘 다 Claude 우선
}
```

- 모든 tier가 **Claude 우선 + Gemini 폴백** (사용자 Claude $100 크레딧 활용)
- `tier="fast"` 사용처: keyword_gen, review_miner, intent_check, sourcing, generate_new_categories, category_ko
- `tier="quality"` 사용처: shop_namer, verdict_ai

### 모델

- Claude: `claude-sonnet-4-6`
- Gemini: `gemini-2.0-flash` (env `GEMINI_MODEL`로 오버라이드)

### 진단 로그 (Streamlit Cloud Logs 패널)

```
[LLM][claude] APITimeoutError: ...
[LLM][claude] RateLimitError: ...
[LLM][claude] AuthenticationError: ...
[LLM][claude] empty response (stop_reason=max_tokens)
[LLM][gemini] ...
[LLM][json] parse failed (preview): ...
[LLM][json] all strategies failed (text_len=N, starts=..., ends=...)
```

### JSON 파서 (`_extract_json` + `_repair_truncated_array`)

3단계 복원:
1. 코드펜스 strip (닫는 ``` 없어도 OK)
2. 첫 array/object 추출
3. 잘린 배열 복원 — bracket-depth 트래커로 마지막 완전 element 찾아 `]`로 닫음

---

## 7. GUI 레이아웃 (`app.py` 흐름)

1. **헤더** (`render_header`) — 🐙 샵 디스커버리 + LLM 배지
2. **통계 카드 3열** — 📦 전체 / ✅ GO / 🔬 분석 완료
3. **카테고리 영역**:
   - `render_list_header` — ↩ 복원 / ✨ AI 새목록 + amber 경고
   - 🎯 카테고리 선정 기준 (타겟 연령) 드롭다운
   - `render_category_grid` — 3열 카드 (이모지 + ★등급 + 연령 배지)
4. **버튼 행** — 🎲 랜덤 / ▷ 전체 분석 / 청크별 분석
5. **단일 분석 폼** — 카테고리 + 타겟시장 + 통화 + 🔍 분석 실행
6. **결과 영역**:
   - `render_verdict_panel` — 게이지 + 큰 점수 + GO/WATCH/NO-GO 배지
   - AI 요약 (`verdict_ai`)
   - 구매 연령대 표시
   - 스코어카드 (`factor_bar` 5개)
   - 키워드 / 모듈 상세 / 스코어카드 미리보기 익스팬더
   - ⬇️ Excel 리포트
   - 📌 내 전략 기준 (SEO/대량업로드/블로그/영상)
   - `render_go_tools(result)` (GO만):
     - 🏷️ 샵 이름 5개
     - 📦 소싱 리스트 (서브카테고리×상품×변형×페이지×패스)
     - 🎯 이 카테고리 Spark URL (변형×페이지×브로드)
     - Spark 임포트 섹션
7. **배치 결과 테이블** — 광고순위 / 무광고순위 / EN / 한글 / 광고총점 / 무광고총점 / 판정 / 5개 항목 점수

---

## 8. 소싱 리스트 생성 (핵심 기능)

### `generate_sourcing_list(category, n_subs, n_variants, passes, pages, verify_urls)`

```
LLM 호출 (passes회) → 서브카테고리 dedup → 폴백 보강
  ↓
각 서브 × 5상품 × n_variants × pages 행 생성
  ↓
SourcingRow(subcategory, base_product, variant, brand, keyword,
           est_price, amazon_node_id, asin, review_count, page)
  ↓
sourcing_report.write_sourcing_report:
  - .xlsx: 11열 (서브카테고리·브랜드·상품명·변형·AmazonURL·예상가격·키워드·ASIN·리뷰수·노드ID)
  - .txt: 카테고리|서브카테고리|URL (Spark 일괄입력용, dedup됨)
```

### URL 빌더 (`spark_urls.build_search_url`)

```
노드 ID 있음 + page=1:
  https://www.amazon.com/s?keywords={kw}
    &rh=n%3A{node}%2Cp_n_has_afn_offer%3A1%2Cp_85%3A2470955011
    &c=ts&s=review-count-rank

노드 ID 있음 + page>=2: 위 + &page=N

노드 ID 없음 + page=1:
  https://www.amazon.com/s?k={kw}&s=review-count-rank

노드 ID 없음 + page>=2: 위 + &page=N
```

### 기본값

```python
DEFAULT_SUBS = 6
DEFAULT_VARIANTS = 5
DEFAULT_PASSES = 1
DEFAULT_PAGES = 1
PRODUCTS_N = 5  # 고정
```

### 🚀 정확도 최대 프리셋

`서브 15 · 변형 10 · 페이지 5 · 1패스` → 최대 750 URL

---

## 9. 외부 API 통합

### `.env` (모두 선택, 없으면 mock/폴백)

```
ANTHROPIC_API_KEY=...            # Claude Sonnet
GOOGLE_API_KEY=...               # Gemini Flash (무료 티어)
GEMINI_MODEL=gemini-2.0-flash    # 선택
KEEPA_API_KEY=...                # Keepa (현재 활성)
KW_EVERYWHERE_API_KEY=...        # Keywords Everywhere
```

### Streamlit Cloud Secrets (TOML)

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
GOOGLE_API_KEY = "AIza..."
KEEPA_API_KEY = "..."
KW_EVERYWHERE_API_KEY = "..."
```

### Keepa Timeout (`sources.py`)

```python
def _with_timeout(fn, timeout=10.0):
    # ThreadPoolExecutor.submit().result(timeout=10)
    # shutdown(wait=False) — Cloud hang 방지
```

---

## 10. 카테고리 목록 관리 (`categories.py`)

- `all_categories()` — `generated_categories.json` 있으면 그것만, 없으면 시드 CURATED 20개
- `MAX_CATEGORIES = 20`
- `generate_new_categories(n=20, replace=True, target_age="")`:
  - LLM이 트렌딩 카테고리 생성, exclude = 시드 ∪ 활성 ∪ 이력
  - `target_age` (예: "40-60"): 해당 연령대 niche 우선
  - `replace=True`: 직전 목록·이력 백업 → 새 목록 교체 → 이력 초기화
- `restore_previous_list()` — 백업에서 복원
- `record_decisions({name: decision})` — 분석 결과 저장
- `save/load/clear_batch_results()` — 배치 순위 영속화

---

## 11. 한글 번역 (`category_ko.py`)

### 우선순위 체인

```
1. 빌트인 dict (40개: 시드 CURATED 20 + 40-60 타겟 AI 생성 20)
2. JSON 캐시 (category_ko_cache.json, 영구 보관)
3. LLM 호출 (Claude → Gemini, max_tokens=80, ~1초)
4. 영문명 그대로 폴백 (UI 안 깨짐)
```

### 사용처

- `batch_report` — Excel "카테고리(한글)" 컬럼
- `app_render.render_batch` — 테이블 + 1위 추천 메시지

---

## 12. 자매 도구 — spark_collector

**위치**: `D:\스파크배포용\spark_collector\` (별도 Node.js 프로젝트)

**역할**: shop_discovery가 생성한 .txt를 입력받아 실제 Amazon ASIN 수집

**구조**:
```
bin/spark_collector.js (241줄)   CLI 진입점
src/parser.js (110줄)            .txt 파싱
src/captcha-detector.js (167줄)  차단 감지 (6개 패턴)
src/failure-tracker.js (83줄)    연속 실패 자동 중단
src/lock.js (197줄)              .lock + blocked.flag
src/checkpoint.js (116줄)        재개 가능
src/output-writer.js (258줄)     결과 4개 파일 + 즉시 flush
src/crawler.js (293줄)           Playwright 핵심
src/stage-runner.js (296줄)      3단계 오케스트레이션
src/stage-ui.js (54줄)           UI 헬퍼
test/*.test.js                   122개 테스트
```

**3단계 자동 진행**:
- Stage 1: 25 URL × 인스턴스 1 × 간격 3초
- Stage 2: 100 URL × 인스턴스 2 × 간격 2.5초
- Stage 3: 전체 × 인스턴스 4 × 간격 2초

**안전장치**:
- 인스턴스 ≤4 하드캡, 간격 ≥2초
- CAPTCHA/403/503 + "Sorry! Something went wrong!" 감지
- 5회 연속 실패 → sleep+test, 10회 → abort
- blocked.flag 영구 차단 추적 (사용자 수동 삭제)

---

## 13. 워크플로우 — 새 샵 시작 시

```
1. Streamlit GUI 접속
   └─→ ✨ AI 새목록 또는 시드 CURATED 사용

2. 카테고리 선택 → 단일 분석 실행
   └─→ GO 판정 받으면 다음 단계

3. 📦 소싱 리스트 생성 (🚀 정확도 최대 권장)
   └─→ .xlsx + .txt 다운로드

4. .txt를 spark_collector로 전송
   cd D:\스파크배포용\spark_collector
   node bin\spark_collector.js {path-to-txt}
   └─→ asins.txt, results.csv 생성

5. results.csv → Shopify 임포트 (ShopCloner 또는 수동)

6. 상품 페이지 SEO 최적화 → 첫 매출
```

---

## 14. 한계 / 알려진 이슈

1. **margin_calc는 항상 mock** — AliExpress/CJ 소싱가 미연동 (35점 비중이라 임팩트 큼)
2. **데이터셋 미매핑 카테고리** — `s?k=` 일반 검색 URL만 생성 (Prime/AFN 필터 없음)
3. **HF dataset 2023-09 기준** — ASIN 30%는 단종 가능 (verify_urls 옵션으로 완화)
4. **Streamlit Cloud SQLite 부재** — 직접 ASIN 모드는 로컬 PC만 가능
5. **광고 없는 전략** — 5개 동시 운영 비현실적 (월 85-125시간 노동)

---

## 15. 다음 개발 우선순위 (가능)

1. margin_calc 실데이터 (AliExpress 소싱가 + Shopify 수수료)
2. 소싱 키워드 Keywords Everywhere 실검증·정렬
3. 영상 홍보 잠재력 (이미지/영상 분석 모듈)
4. 단위 테스트 확장 (현재 20개 → 50개+)
5. `google-genai` 패키지 마이그레이션 (현재 deprecated 경고)
6. K-Beauty 같은 카테고리는 KD(Keyword Difficulty) 통합 검토

---

## 16. 핵심 명령어

```bash
# 로컬 GUI
streamlit run app.py

# 로컬 CLI
python main.py "memory foam pillow"
python main.py  # 인자 없으면 프롬프트

# 테스트
python -m pytest tests/ -q

# Cloud 푸시 (자동 재배포)
git add -A && git commit -m "..." && git push origin main

# 패키지 설치
pip install -r requirements.txt
```

---

## 17. 커밋 컨벤션

```
fix(llm): 한 줄 요약 (한국어)

상세 설명...

🐙 Autopus <noreply@autopus.co>
```

타입: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`

---

## 18. 최근 주요 변경 (2026-05-17 ~ 2026-05-21)

| 날짜 | 커밋 | 변경 |
|---|---|---|
| 05-17 | passes/pages 기능 | sourcing_llm.py 분리 + bracket-depth JSON 복원 |
| 05-17 | LLM 진단 로그 | `[LLM][provider] {error}` 로그 노출 |
| 05-18 | 한글 병기 | category_ko.py 신규 (dict + LLM + 캐시) |
| 05-18 | 광고/무광고 2개 순위 | ranking_modes.py 신규 (NO_AD_WEIGHTS) |
| 05-18 | JSON 파서 강화 | `_repair_truncated_array` (bracket depth tracker) |
| 05-18 | spark_collector | 별도 Node.js 도구 신규 (외부 디렉토리) |
| 05-20 | Keepa 토큰 UI | 헤더 배지 + 사이드바 모니터 + 자동 백오프 + preflight 경고 |
| 05-20 | Keepa 토큰 최적화 | 디스크 캐시(24h) + stats=30 + 샘플 15 → 토큰 40-100% 절감 |
| 05-20~21 | Node.js 키워드 시스템 | Step 1-5: Google Ads + Suggest + 캐시 + Keepa + 2단계 파이프라인 + HTTP API |
| 05-21 | 키워드 리서치 GUI | Streamlit 멀티페이지 탭 (Node API 클라이언트) |
| 05-21 | RapidAPI 데이터소스 | rapidapi-keywords.js 신규 (1순위, Basic Access 우회). 무료 월 20회 한도 |
| 05-21 | 백업/복원 | app_backup_ui.py + export/import_all_state (재배포 생존) |
| 05-21 | GEMINI.md | Gemini용 전체 시스템 설명서 |

---

## 19. 신규 Claude 세션이 처음 할 일

1. **이 ARCHITECTURE.md + CLAUDE.md 통독**
2. `git log --oneline -10` — 최근 변경 확인
3. `python -m pytest tests/ -q` — 회귀 통과 확인
4. `streamlit run app.py` — UI 동작 확인
5. 작업 시작

새 기능 추가 시:
- 모듈 분리 우선 (300줄 한도)
- 회귀 테스트 추가 (`tests/`)
- 커밋은 Lore format + 🐙 Autopus 서명
- 푸시 후 Cloud 1-2분 재배포 대기

---

## 20. 사용자(jin) 컨텍스트

- 드랍쇼핑 솔로 운영자, 미국 타겟
- 5개 샵 계획 (광고 없이 시작 → 매출 발생 후 광고)
- 현재 우선순위: Memory Foam Pillows (88.1점, 1순위 GO)
- 자매 도구 보유: spark_collector (D 드라이브), ShopCloner (?)
- Cloud 배포 중: `shopdiscovery-w4vh6puhwewxiqfv9ksouj.streamlit.app`
- 깃 저장소: `eumjin1000-design/shop_discovery`
- Claude 크레딧 $100 활용 중 (Claude-first tier 설정)
- 전략 결정: **Google 검색량 = 샵 선정 메인 기준**, Keepa = 제품 소싱 보조 (최소 사용)
- Google Ads Basic Access 신청 완료 (2026-05-20, 1-3일 승인 대기)

---

## 22. Node.js 키워드 리서치 시스템 (Step 1-5)

별도 Node.js 스택. 사용자 전략(Google 검색량 우선)을 코드화한 2단계 워크플로우.

### 데이터 흐름

```
[HTTP API] POST /api/keywords/research        ← Step 5 (Express)
     ↓
[오케스트레이터] shop-pipeline.discoverShop    ← Step 4
     │
     ├─ [1단계] Google 검색량 → 샵 선정
     │    keyword-pipeline.researchKeywords    ← Step 2
     │      ├─ google-suggest (시드 확장)
     │      ├─ fetchKeywordData (volume/KD):
     │      │    1순위 rapidapi-keywords (즉시) / 2순위 google-ads-api (Basic 대기)
     │      └─ keyword-cache (SQLite, 30d)     ← Step 1
     │    → gems = opportunity(volume/(KD+1)) 랭킹
     │      (RapidAPI는 시드 1개→~292개 확장분도 후보 풀에 병합)
     │
     └─ [2단계] 선정 샵 → Keepa 제품 소싱 (top-N gems만)
          keepa-validator.validateKeywordsWithKeepa  ← Step 3
            └─ ASIN 24h 캐시 + 토큰 백오프(<5)
          → 각 gem에 amazon_products[] (BSR≤50k)
```

### HTTP API (`server/`)

| 엔드포인트 | 설명 |
|---|---|
| `GET /health` | liveness |
| `POST /api/keywords/research` | seeds → gems(+Keepa). body: `{seeds, market, language, validate_with_keepa, top_n}` |
| `GET /api/keywords/cache/stats` | 캐시 hit_rate |

응답 envelope: `{success, data}` / `{success:false, error, code}`.
에러 코드: `VALIDATION_ERROR`(400) · `TIMEOUT`(504) · `INTERNAL_ERROR`(500).

### gems 기준

- opportunity_score = volume / (KD + 1)
- gem 필터: **KD ≤ 30 AND volume ≥ 1000** (상위 50개)
- KD 배지: ≤30 💎 / ≤60 ⭐ / >60 🔴

### 실행

```bash
npm run serve          # node server/index.js → http://localhost:8787
node test-step5.js     # API 통합 테스트
```

### .env (Node.js 추가 키)

```
RAPIDAPI_KEY                   # RapidAPI Google Keyword Insight (1순위, 즉시)
RAPIDAPI_KEYWORD_HOST          # google-keyword-insight1.p.rapidapi.com
GOOGLE_ADS_DEVELOPER_TOKEN     # Google Ads (2순위 폴백, Basic Access 필요)
GOOGLE_ADS_CLIENT_ID
GOOGLE_ADS_CLIENT_SECRET
GOOGLE_ADS_REFRESH_TOKEN
GOOGLE_ADS_CUSTOMER_ID
GOOGLE_ADS_LOGIN_CUSTOMER_ID
KEYWORD_API_BASE               # Streamlit→Node API 베이스 (기본 localhost:8787)
```

### 영속 파일 (gitignored)

```
seo-cache.db              SQLite 키워드/ASIN 캐시
keepa_data_cache.json     Keepa 결과 디스크 캐시 (Python측)
keepa_token_history.json  토큰 이력 (사이드바 차트)
node_modules/             (package-lock.json도 무시)
```

### 키워드 데이터소스 우선순위 (`fetchKeywordData`)

```
1순위: RapidAPI Google Keyword Insight (RAPIDAPI_KEY 있으면)
   - 시드 1개 → ~100-300개 확장 + volume/KD/CPC/trend
   - Basic Access 불필요 (즉시 사용)
   - 응답: {text→keyword, volume, competition_index→kd, low_bid, high_bid, trend}
2순위: Google Ads API (RAPIDAPI_KEY 없을 때)
   - Basic Access 승인 필요
metadata.data_source = "rapidapi" / "google_ads"
```

### 알려진 제약

- **RapidAPI 무료 BASIC 플랜 = 월 20회 한도**. 소진 시 429 + ~31일 후 리셋.
  대안: 플랜 업그레이드 / 신규 키 / Google Ads Basic Access 대기.
  (코드는 검증 완료 — API 정상 도달 확인, 막힌 건 할당량뿐)
- **Google Ads Basic Access 승인 전**: volume=0, gems 비어있음. 승인 시 자동 활성.
- **localhost API**: Streamlit Cloud는 localhost:8787 도달 불가 → 키워드 리서치 페이지는 **로컬 전용**. Cloud에선 ConnectionError 안내 메시지.
- **Keepa 1 token/min** (Pro): 백오프 + 캐시로 최소 사용. 자세한 운영은 21번.

### 검증 상태 (2026-05-21)

| 항목 | 결과 |
|---|---|
| Step 1-5 구조 | ✅ 전부 작동 |
| Suggest 확장 | ✅ (Google Ads 없이도) |
| Google Ads volume | ⏳ Basic Access 승인 대기 (volume=0) |
| Keepa 소싱 | ✅ (인덱스 검증 완료, 토큰 한도 내) |
| HTTP API + GUI | ✅ (로컬, success/total/배너 확인) |

---

문서 끝.
