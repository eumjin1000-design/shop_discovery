# Shop Discovery — 드랍쇼핑 신규 샵 발굴 자동화

> 카테고리 입력 → 7단계 분석 파이프라인 → 100점 Go/No-Go 판정 → Excel 리포트.
> 추가로: 20개(또는 AI 생성 20개) 카테고리 일괄/부분 배치 분석, GO 카테고리에 대한 샵 이름·150개 소싱 리스트 자동 생성.
> CLI(`main.py`) + Streamlit GUI(`app.py`) 두 가지 진입점.

언어 정책: 코드 주석 = 영어, 커밋 = 한국어, AI 응답 = 한국어. 파일당 300줄 하드 한도(`.md`/`.json` 제외).

---

## 1. 실행

```bash
# CLI
python main.py "wireless earbuds"      # 인자로 카테고리
python main.py                          # 인자 없으면 프롬프트
# → 콘솔 ASCII 스코어카드 + output/shop_discovery_<slug>_<ts>.xlsx

# GUI
streamlit run app.py                    # (PATH 문제 시 python -m streamlit run app.py)
```

의존성: `pip install -r requirements.txt`
(`anthropic`, `google-generativeai`, `keepa`, `requests`, `beautifulsoup4`, `openpyxl`, `python-dotenv`, `streamlit`; `pandas`는 streamlit이 가져옴)

`.env` (모두 선택 — 없으면 mock/폴백):
```
ANTHROPIC_API_KEY=...            # Claude Sonnet
GOOGLE_API_KEY=...               # Gemini Flash (무료 티어)
GEMINI_MODEL=gemini-2.0-flash    # (선택) Gemini 모델 오버라이드
KEEPA_API_KEY=...                # Keepa — Amazon BSR/평점 실데이터 (현재 .env에서 # 주석 처리됨)
KW_EVERYWHERE_API_KEY=...        # Keywords Everywhere — 실 검색량/추세
```
`여기에...`로 시작하는 placeholder 값 = "미설정"으로 취급.

---

## 2. 파일 맵

```
main.py                    파이프라인 오케스트레이션(run_pipeline / run_categories / run_all_curated) + CLI + 콘솔 출력
app.py                     Streamlit 페이지 스크립트(레이아웃 흐름 + 단일 분석 폼 + 배치 버튼 + 결과 렌더 호출)
app_render.py              결과 영역 렌더 헬퍼(헤더, 게이지, 판정 패널, 스코어바, 배치 테이블, 전략 패널, GO 도구, Excel)
                           └ 소싱 블록: 슬라이더 2개(서브카테고리 수 2~10, 변형 수 1~10), 세션키 sourcing_res,
                             generate_sourcing_list(category, n_subs, n_variants) 호출, Excel + Spark .txt 다운로드 버튼
app_catalog_ui.py          카테고리 영역 렌더 헬퍼(통계 카드, 목록 헤더+관리 버튼+amber 배너, 카드 그리드, 이모지 매핑)
make_icon.py               Pillow로 데스크톱 아이콘(icon.ico) 생성 — 일회성 유틸
modules/
  models.py                불변 데이터클래스: DiscoveryRequest, Keyword, TrendResult, BSRResult, ReviewResult,
                           IntentResult, MarginResult, ScoreLine, Verdict, PipelineResult
  llm.py                   하이브리드 LLM: ask_json/ask_text(tier="fast"|"quality"), provider_label(), any_available()
  util.py                  seeded_rng(*parts) (카테고리 시드 결정론적 RNG), clamp()
  curated_data.py          CuratedCategory 데이터클래스 + 시드 CURATED 20개(이름·margin/demand/competition 1~3·reason)
  categories.py            활성 카테고리 목록 관리 + AI 새목록 생성 + 분석 이력 + 배치 결과 영속화
  sources.py               외부 데이터: keyword_volumes()(Keywords Everywhere), google_trends()(pytrends — 키 없는 Google Trends, vol=관심도 추정), keepa_snapshot()(Keepa) — 실패 시 None
  keyword_gen.py    [1]    카테고리 → 키워드 N개
  trend_check.py    [2]    키워드 검색량/성장률/안정성/계절성
  amazon_bsr.py     [3]    Amazon 베스트셀러 랭크·경쟁 리스팅 수
  review_miner.py   [4]    기존 상품 평균 평점·리뷰 수·불만 테마
  intent_check.py   [5]    상업적 구매 의도·문제 인지도
  margin_calc.py    [6]    단위 손익(소싱가·판매가·배송·수수료·광고비 → 순마진)
  synthesizer.py    [7]    100점 스코어카드 → GO/WATCH/NO-GO + 한 줄 요약
  verdict_ai.py            (선택) Claude로 한국어 판정 요약 3~4문장 생성 — GUI 단일 결과에만, 배치엔 미사용
  report_gen.py            단일 분석 Excel(Summary·Scorecard·Keywords·Details 시트)
  batch_report.py          배치 순위 Excel(Ranking 시트 1장) — 행-딕트 리스트 입력
  shop_namer.py            GO 카테고리용 샵 이름 5개(영어·기억 쉬움·.com 가능) — tier="quality"
  sourcing.py              소싱 리스트 생성. generate_sourcing_list(category, n_subs=6, n_variants=5).
                           SourcingRow 9필드. 변형 풀 10종. 총 행 = n_subs×5×n_variants.
                           노드 ID 결정 순서: ①LLM이 USER_PROMPT 후보 목록에서 선택 → ②_guess_node 로컬
                           폴백(NODE_DB ~75항목) → ③키워드 검색 URL 폴백(node='1000').
                           _guess_node: 단어 완전일치 2점 / 부분일치 1점 / GENERIC_WORDS 0.5점 페널티.
                           _get_node_candidates: 동일 채점으로 상위 5개 추출 → LLM 프롬프트에 주입.
                           Amazon URL = 노드 검색(rh=n%3A{node}+Prime+리뷰순), 노드 없으면 키워드 폴백. — tier="fast"
  sourcing_report.py       write_sourcing_report(result, shop_name, out_dir). Excel 11열:
                           #·서브카테고리·브랜드·상품명·변형·AmazonURL·예상가격·키워드·ASIN·리뷰수·노드ID.
                           Spark 일괄입력 .txt 파일 동시 생성 (카테고리|서브카테고리|URL 형식, .xlsx와 같은 stem).
```

영속 파일(프로젝트 루트, 모두 `.gitignore`):
`generated_categories.json`(AI 새목록), `analysis_history.json`(`{카테고리:판정}`), `batch_results.json`(마지막 배치 순위 경량 데이터), `*.bak.json`(AI 새목록 시 직전 목록·이력 자동 백업), `output/*.xlsx`, `icon_preview.png`.

---

## 3. 분석 파이프라인 (`main.run_pipeline(category, target_market="US", currency="USD") -> PipelineResult`)

```
DiscoveryRequest
 → keyword_gen.generate_keywords(req, n=8)         → tuple[Keyword]      LLM(fast); 없으면 템플릿("best {c}", "{c} for home"…)
 → trend_check.check_trend(cat, keywords)          → TrendResult        Keywords Everywhere(실 절대 검색량) → Google Trends(pytrends, 키 없음·관심도 기반 추정·실 추세) → 시드 mock 순. 구글 애즈 API 포기 후 Trends가 메인 구글 신호
   (TrendResult.keywords가 검색량 채워진 키워드로 교체됨)
 → amazon_bsr.check_bsr(cat, keywords)            → BSRResult          Keepa 있으면 실 best/median rank·경쟁 리스팅; 없으면 시드 mock
 → review_miner.mine_reviews(cat, keywords)       → ReviewResult       Keepa 있으면 실 평균 평점·리뷰 수(부정비율=평점에서 추정); 불만 테마는 LLM(fast); 없으면 시드 mock
 → intent_check.check_intent(cat, keywords)       → IntentResult       LLM(fast); 없으면 키워드 어휘 휴리스틱(buy/price/best… vs how to/fix/vs…)
 → margin_calc.calc_margin(cat, currency)         → MarginResult       항상 시드 mock(소싱가 uniform 3~28, 마크업 2.2~4x, 마켓수수료 15%, 광고비 12~45%)
 → synthesizer.synthesize(cat, trend, bsr, review, intent, margin) → Verdict
 → PipelineResult(request, keywords, trend, bsr, review, intent, margin, verdict)
```

데이터 소스 우선순위는 **실 API → mock**. mock은 `util.seeded_rng("<tag>", category)`로 카테고리당 항상 같은 값(재현 가능). 각 *Result의 `notes` 문자열에 `[실데이터: Keepa]` / `[mock data — set ..._API_KEY]` 식으로 출처 표기.

배치 함수:
- `run_categories(names: list[str], progress=None)` — 지정 카테고리만 순차 실행, 완료 후 `categories.record_decisions({name:decision})`, 점수 내림차순 정렬 반환. `progress(done, total, name, eta_secs)` 콜백(ETA=실측 평균 외삽).
- `run_all_curated(progress=None, only_unanalyzed=False)` — `run_categories`의 thin wrapper(전체 또는 미분석분만).

---

## 4. Go/No-Go 스코어링 (100점, `synthesizer.py`)

| 항목(영문 키 → GUI 한글 라벨, 아이콘) | 배점 | 산정 |
|---|---|---|
| `Margin / unit economics` → 마진/단위 경제성 💰 | 35 | `clamp(net_margin_pct / 0.35) * 35` — 순마진 35%↑ 만점, 0% 이하 0 (드랍쇼핑 성패 핵심) |
| `Search trend` → 검색 트렌드 📈 | 20 | 성장 `clamp((growth-0.8)/0.6)*14` (0.8x→1.4x YoY) + 안정성 `stability*6`, 계절성이면 −2 |
| `Market & competition (BSR)` → 시장 및 경쟁(BSR) 🏪 | 20 | 수요(best_rank: <1k=12 / <5k=9 / <10k=6 / <30k=3 / else=1) + 경쟁(competing_listings: <1.5k=8 / <5k=6 / <10k=4 / <25k=2 / else=1) |
| `Review opportunity` → 리뷰 기회 ⭐ | 15 | `clamp(1 - |avg_rating-3.8|/1.5) * 15` — 기존 평점 ~3.8/5에서 최대(불만족=기회), 양끝 감점 |
| `Purchase intent` → 구매 의도 🛒 | 10 | `clamp(commercial_intent*7 + problem_awareness*3, 0, 10)` |

판정: **총점 ≥ 70 → GO** / **50–69 → WATCH** / **< 50 → NO-GO**.
`Verdict.summary` = 결정론적 한 줄(가장 강한/약한 요인 + verb). GUI는 그 아래 `verdict_ai.ai_verdict_summary()`로 Claude 3~4문장 요약을 추가(키 있을 때만, 카테고리+판정+점수 키로 세션 캐시).

---

## 5. LLM 하이브리드 전략 (`modules/llm.py`)

- `tier="fast"` (기본): **Gemini Flash(무료) → Claude Sonnet → None**. 사용처: keyword_gen, review_miner(불만 테마), intent_check, sourcing, generate_new_categories.
- `tier="quality"`: **Claude Sonnet → Gemini Flash → None**. 사용처: shop_namer, verdict_ai.
- 호출부는 `None`을 받으면 반드시 결정론적 폴백(휴리스틱/템플릿/시드 mock)으로 처리. 모든 provider 호출은 try/except로 감싸 절대 예외 전파 안 함.
- `ask_json(prompt, *, tier, max_tokens)` — JSON 파싱(코드펜스/첫 균형 블록 추출 폴백). `ask_text(...)` — 평문.
- `provider_label()` → "Gemini Flash(무료) + Claude Sonnet" 등(헤더 배지). `any_available()` → 둘 중 하나라도 있으면 True.
- ⚠️ `google-generativeai`는 deprecated 경고 출력(요청 패키지명 유지). 필요 시 `google-genai`로 교체 가능.

---

## 6. GUI 레이아웃 (`app.py` 흐름)

1. **헤더** (`ui.render_header`) — 왼쪽 `🐙 샵 디스커버리` + 부제, 오른쪽 LLM 배지(`🤖 Gemini Flash(무료) + Claude Sonnet` / 없으면 `⚠️ 없음 (mock 데이터)`).
2. **통계 카드 3열** (`catalog.render_stats`) — 📦 전체 카테고리 / ✅ GO 판정 수 / 🔬 분석 완료 수.
3. **카테고리 영역**:
   - `catalog.render_list_header` — `📂 카테고리 목록` 라벨(좌) + `↩ 이전 목록 복원`(백업 없으면 disabled) + `✨ AI 새목록`(우). 아래 amber 경고 배너(`#fff8e1`): "'AI 새목록' 생성 시 분석 이력 초기화 / 자동 백업되어 복원 가능".
   - `catalog.render_category_grid(..., cols=3)` — 3열 카드: 우상단 GO/WATCH/NO-GO(또는 "미분석") 배지 → 큰 이모지(46px, 이름 키워드로 매핑, 폴백 🛒) → 이름 → `마진 ★★☆ · 수요 ★★★`. 카드 아래 "선택" 버튼 클릭 → 선택(파란 테두리+연파랑 배경, 버튼 "✓ 선택됨"), `st.rerun()`.
   - 선택된 카테고리면 `💡 이름 ✅분석완료 — ★등급 + reason` 캡션 + `📋 카테고리 N개` 표 익스팬더.
4. **버튼 행** — `🎲 랜덤 추천`(secondary, 좌) · `▷ 전체 N개 자동 분석`(primary/빨강, 우). 아래 `⏳ 10개 단위로 나눠 분석` 익스팬더에 청크 버튼(`1~10번`, `11~20번`…). 청크/전체 완료마다: `pipeline_rows`로 경량화 → 기존 누적과 이름 기준 병합 → 점수순 정렬 → `batch_results.json` 저장 → `st.rerun()` → `ui.render_batch` 테이블(순위·카테고리·총점·판정 색상·항목별 점수 + Excel 다운로드).
5. **단일 분석 폼** — 카테고리 입력(`key="category_input"`, 카드/랜덤 선택값과 공유) + 타겟 시장/통화 + "이미 분석한 카테고리 다시 분석" 체크박스 + `🔍 분석 실행`. 이미 분석한 카테고리는 체크 없으면 경고 후 중단.
6. **분석 결과** (`result` 있으면):
   - `ui.render_verdict_panel(v)` — 좌 게이지 SVG, 우 큰 점수(62px) + GO/WATCH/NO-GO 배지(30px) + 임계값.
   - `v.summary` + (키 있으면) AI 요약 `st.info(icon="🤖")`.
   - 스코어카드: 항목별 아이콘 막대(`ui.factor_bar`, 빨강→초록 그라데이션).
   - `키워드` 익스팬더 / `모듈별 상세 지표` 익스팬더(각 Result.notes) / `스코어카드 미리보기` 테이블.
   - `⬇️ Excel 리포트 다운로드` (`report_gen.write_report`, output/에도 저장).
   - `📌 내 전략 기준` 4개 메트릭(`ui.render_strategy`): **SEO 적합도**(키워드 합산 검색량 ≥8000 & 경쟁 <12000 → ✅) / **대량 업로드 적합**(경쟁 리스팅 ≥1500 → ✅) / **블로그 콘텐츠 난이도**(문제인지도+불만 테마 수로 쉬움/보통/어려움) / **영상 홍보 잠재력**(🔜 향후 적용).
   - `v.decision == "GO"`면 `ui.render_go_tools(result)`:
     - `🏷️ 샵 이름 5개 생성`(`shop_namer`, tier="quality") → `st.radio`로 선택(각 항목 컨셉 + 🌐 도메인 후보), 선택값은 소싱 Excel 헤더에 반영.
     - `📦 소싱 리스트 생성`(`sourcing.generate_sourcing_list(category, n_subs, n_variants)`, tier="fast") — 슬라이더로 서브카테고리 수(2~10)·변형 수(1~10) 조절, 총 행 = n_subs×5(상품)×n_variants(기본 6×5×5=150). 변형은 10종 풀(`Standard/Compact/Premium/Set of 2/Travel Size/Mini/XL/Refill Pack/Gift Box/Pro`)에서 앞 n_variants개. 각 행: 서브카테고리·기본상품·변형·brand(추정)·keyword(고검색량·저경쟁)·est_price(시드 RNG)·amazon_node_id·asin/review_count(스크래퍼 채울 플레이스홀더). **Amazon URL** = 브라우즈 노드 검색(`s?rh=n%3A{node_id}%2Cp_n_prime_eligibility%3A23533298011&s=review-count-rank` = 노드+Prime+리뷰순), 노드 ID 없으면 키워드 검색(`s?k=...&s=review-count-rank`) 폴백. → 상위 20개 미리보기 + `⬇️ Excel 다운로드` + `⬇️ Spark 일괄입력 .txt`.
       **Spark 연동**: `sourcing_report.py`가 `.xlsx`와 같은 stem의 `.txt`를 동시 생성(`카테고리|서브카테고리|URL` 한 줄씩, 중복 제거) → 그 `.txt`를 Spark 일괄입력 탭에 붙여넣기 → 작업 시작.
   - GO 아니면 "GO 판정 시 사용 가능" 안내.

---

## 7. 카테고리 목록 관리 (`modules/categories.py`)

- `all_categories()` → **`generated_categories.json`에 유효 항목이 있으면 그것만**(시드 CURATED와 합산 안 함), 없으면 시드 `CURATED` 20개. 항상 최대 `MAX_CATEGORIES`(=20)개, 이름 소문자 기준 중복 제거.
- `generate_new_categories(n=20, replace=True)` — AI(fast)로 트렌딩 카테고리 생성, `exclude` = 시드 CURATED ∪ 현재 활성 목록 ∪ 분석 이력(전부 소문자). `replace=True`: 직전 `generated_categories.json`+`analysis_history.json`을 `*.bak.json`으로 백업 → 새 목록으로 교체 → 이력 초기화 → `batch_results.json` 삭제. (`replace=False`는 append 모드, GUI 미사용.)
- `restore_previous_list()` — `*.bak.json`에서 목록·이력 복원(+배치 결과 삭제). `has_backup()`로 버튼 활성 판단.
- `load_history()` → `set[str]`, `load_history_map()` → `{name: decision|None}`(레거시 리스트 포맷도 호환). `mark_analyzed(*names, decision=None)`, `record_decisions({name:decision})`.
- `save_batch_results(rows)` / `load_batch_results()` / `clear_batch_results()` — 배치 순위 경량 데이터(`[{name,total,decision,breakdown:[[factor,score,max]...],summary}]`) 영속화 → 앱 재시작해도 순위 테이블·카드 배지 복원.
- `by_name`, `names`, `random_category` 모두 `all_categories()` 기반.

---

## 8. 현재 상태 / 한계 / 다음 작업 후보

- **검증 완료**: mock 경로(키 없음) 전체 파이프라인·CLI·Streamlit 기동(HTTP 200), Gemini Flash 실호출, Keywords Everywhere/Keepa 코드 경로(라이브 검증은 안 함 — 토큰 비용 회피).
- **Keepa**: `.env`에서 `KEEPA_API_KEY`가 `#` 주석 처리됨(40개 일괄 분석 시 토큰 대기로 멈출 수 있어). 활성화하려면 `#` 제거 후 재시작 — 단 단일/10개 청크 위주 사용 권장. Keepa 응답 파싱(`stats.current` 인덱스 3/16/17, `category_lookup.productCount`)은 best-effort이며 어긋나면 자동 mock 폴백.
- **margin_calc**는 항상 mock(실제 소싱가/마켓 수수료 소스 미연동) — 점수 35점 비중이라 실데이터화가 가장 임팩트 큼.
- **소싱 리스트**: Amazon URL은 검색 결과 페이지(ASIN 아님), 변형 5종 고정, 예상가는 LLM 추정×시드 변동.
- **버튼 색상**: Streamlit이 `type="primary"`(빨강)/`secondary`(아웃라인풍)만 지원 — amber 등 정확한 색은 amber 배너(HTML)로만 구현, 버튼은 근사.
- **보안**: `.env`에 실제 API 키 존재(`.gitignore` 처리됨). 대화 기록에 노출된 적 있어 `ANTHROPIC_API_KEY` 로테이션 권장.
- **다음 후보**: ① margin_calc 실데이터(AliExpress/CJ 소싱가 + 마켓 수수료), ② 소싱 키워드를 Keywords Everywhere로 실검증·정렬, ③ 영상 홍보 잠재력(이미지/영상 분석), ④ 단위 테스트(`pytest`), ⑤ `google-genai` 패키지로 마이그레이션.
