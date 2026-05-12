# Shop Discovery 자동화 앱

## 프로젝트 목적
드랍쇼핑 신규 샵 발굴 자동화
- 카테고리 입력 → Go/No-Go 판정 → Excel 리포트 출력

## 아키텍처
- 설계: claude-opus-4-7
- 실행: claude-sonnet-4-6

## 데이터 흐름
```
category
  → keyword_gen   (카테고리 → 키워드 N개; Anthropic API, 없으면 템플릿 폴백)
  → trend_check   (키워드별 검색량/성장률/계절성; 현재 mock)
  → amazon_bsr    (베스트셀러 랭크·경쟁 리스팅 수; 현재 mock)
  → review_miner  (기존 리뷰 평점·불만 테마; 메트릭 mock, 불만은 LLM)
  → intent_check  (구매의도/문제인지도; LLM, 없으면 어휘 휴리스틱)
  → margin_calc   (단위 손익: 소싱가·판매가·배송·수수료·광고비 → 순마진; 현재 mock)
  → synthesizer   (100점 스코어카드 → GO / WATCH / NO-GO)
  → report_gen    (output/*.xlsx — Summary·Scorecard·Keywords·Details 시트)
```
공통 모듈: `modules/models.py`(불변 데이터클래스), `modules/llm.py`(Anthropic 래퍼 + 오프라인 폴백), `modules/util.py`(시드 RNG·clamp).

## Go/No-Go 스코어링 (100점)
| 항목 | 배점 | 산정 |
|------|------|------|
| Margin / unit economics | 35 | 드랍쇼핑 성패의 핵심. 순마진 35% → 만점, 0%까지 선형 |
| Search trend | 20 | 성장 14 (0.8x→1.4x YoY) + 안정성 6, 계절성 −2 |
| Market & competition (BSR) | 20 | 수요(베스트셀러 랭크) 12 + 경쟁(리스팅 수) 8 |
| Review opportunity | 15 | 기존 평점 ~3.8/5 부근에서 최대 (불만족=기회), 양끝 감점 |
| Purchase intent | 10 | 상업적 의도 ×7 + 문제인지도 ×3 |

판정: **≥70 GO** / **50–69 WATCH** / **<50 NO-GO**

## 실행
```
python main.py "wireless earbuds"     # 카테고리 인자
python main.py                          # 인자 없으면 프롬프트
```
`.env`의 `ANTHROPIC_API_KEY` 사용. 키가 없으면 데이터 모듈이 카테고리 시드 기반 결정론적 mock으로 폴백 → 파이프라인 전체가 그대로 동작.

## 모듈 구조
- `main.py` — 파이프라인 오케스트레이션 + CLI + 콘솔 스코어카드
- `modules/` — 단계별 모듈(`keyword_gen` `trend_check` `amazon_bsr` `review_miner` `intent_check` `margin_calc` `synthesizer` `report_gen`) + 공통 모듈
- 실제 API 연동 지점은 각 데이터 모듈에 `# TODO:` 로 표시 (Google Trends, Amazon PA-API, 리뷰 스크래핑, 소싱가/수수료)