# 공개 GAEO 새 저장소 이전 기록 (2026-09-24)

원본: `rudvh1016-gif/gaeo-analyst-team` main `15557889129f0786ccef159df37689b435706065`
옛 git 이력은 **가져오지 않았다**(clone·mirror·filter-repo 아님). 이 저장소의 첫 커밋은 부모가 없는 새 커밋이며,
아래 목록의 파일만 담는다. 파일별 원본 경로·sha256 은 `MIGRATION_MANIFEST.json`.

## 1. 옮긴 것
| 묶음 | 파일 | 방식 |
|---|---|---|
| OpenDART 수집기 | collect_dart · collect_dart_financials · collect_corporate_action_evidence · build_dart_today · build_disclosure_research · dart_client · dart_time · dart_budget · dart_pipeline · research_store · research_crypto · due_targets · corporate_action_classify · krx_calendar | 그대로. 단 2곳 수정(아래 §3) |
| OpenDART 상태·산출물 | research_archive/dart/{seen_rcept,corp_map,api_budget,collection_status}.json · gaeo_coverage/corporate_action_evidence.json · dart_financials/*.json · dart_today.js · disclosure_research/*.json | 그대로(원본과 sha256 같음) |
| 시험 | test_disclosure_research · test_dart_budget_ledger · test_corporate_action_evidence · test_dart_pipeline · test_dart_financials_collect · test_dart_live_hardening · test_corporate_action_classify · test_secret_hygiene | 옛 저장소 전용 검사만 뺌(§3) |
| 공부 글 | content/stock_lessons.js · estate_lessons.js · calculators.js | 그대로 — SAFE_AS_IS(운영자가 쓴 투자 기초·세금·부동산 공부 글) |
| 종목 공부 | content/stock_study.js | 문장 단위 세척(§2-B) |
| 과거 정밀분석 | content/past_analysis.json → /research/deep-analysis/… 정적 쪽 | 세척 재작성(§2-A) |
| 화면 | site/ 전체 | 새로 씀(디자인 개편) · 계산기 위젯만 옛 app.js 에서 추출 |
| 서체·아이콘 | site/assets/fonts/wanted-sans(OFL) · site/img | 그대로 |

## 2. 콘텐츠 분류

### A. 과거 정밀분석 34건(26개 회사)
| 분류 | 건수 | 뜻 |
|---|---|---|
| SAFE_AS_IS | 0 | 모든 기록이 당시 시세(기준가)·이동평균·주가배수·수급 수치 위에 서 있어 그대로 둘 수 있는 글이 없었다 |
| SANITIZE_AND_RESTORE | 32 | 수치·컨센서스·목표가·수급·증권사/기사 인용·점수·매매 판단을 빼고 「당시 무엇을 봤나 · 왜 · 무엇이면 틀릴 수 있었나 · 이후 공부 · 지금 DART에서 확인할 것」으로 다시 썼다 |
| PRIVATE_ONLY | 2 | `005930-202608121215`(핵심 판단이 특정 증권사 전망·목표가 괴리·수급) · `475150-202607231603`(상승 이유가 뉴스 전달뿐) — 옛 저장소에만 남는다 |

글마다 분류 이유: `past_analysis_classification.json`. 문장 검사기: `tools/migration/validate_past_analysis.py`(허용 숫자 = 날짜뿐 · 금지어 목록) — CI 가 매번 돈다.
쪽마다 맨 위에 「과거 분석 기록 · 작성 당시 기준 · 현재의 매수·매도 추천이 아님」 한 줄.
옛 주소 `/research/deep-analysis/<종목>/<시각>/` 를 그대로 쓴다(복원된 32건). 목록은 `/past-analysis/`.

### B. 종목 공부 35건
| 분류 | 건수 |
|---|---|
| SAFE_AS_IS | 2 |
| SANITIZE_AND_RESTORE | 33 |
| PRIVATE_ONLY | 0 |

방식: 컨센서스·목표주가·투자의견·순매수/순매도·지분율·PER/PBR·증권사 연구원 인용·옛 사이트 시세 파일(data.js) 인용·원화 주가 문장만
문장 단위로 뺐다(`tools/migration/sanitize_study.py`, 글마다 뺀 문장 수: `stock_study_classification.json`). 글을 새로 쓰지 않았다.
옛 사이트 시세 파일을 가리키는 출처 링크도 뺐다. 기사 출처 링크는 링크로만 남긴다.

### C. 투자 공부 101건(주식 82 · 부동산 19) · 계산기 14개 — SAFE_AS_IS
운영자가 쓴 기초 개념·제도 설명. 외부 수치 표를 복제한 글이 아니다. 공식 기관(KIND 밸류업 안내 등) 문서 링크는 링크로만 있다.

## 3. 코드 수정 2곳과 뺀 시험
- `collect_dart.py`: 옛 판단 기록(research_archive/decisions)과 공시를 잇던 `dart_research.preserve_collection` 호출 삭제 — 새 저장소에는 판단 기록이 없다.
- `collect_corporate_action_evidence.py`: 수집 대상이 KIND 상장법인목록(`krx_list.json`)이었다 → OpenDART 고유번호 목록(corpCode)의 종목코드 ∩ `config/evidence_universe.json`(옛 증거 파일의 종목코드 2,600개 그대로). 예산 산수 불변. 가격비교·KIND 분류 모듈(comparison_evidence)은 가져오지 않고 제목 판정 `relevant()` 만 `disclosure_scope.py` 로 옮김(SCOPE_VERSION 동일).
- 뺀 시험(옛 저장소 파일을 전제): test_dart_pipeline.NotWiredIntoV1 · test_dart_live_hardening.V1Frozen · test_dart_financials_collect.test_stored_values_feed_piotroski · test_dart_budget_ledger.test_analysis_runner_merge_path_registers_the_driver. 화면 계약 시험(PublicPage)은 새 화면에 맞춰 다시 씀.

## 4. 옮기지 않은 것(옛 저장소에만 남음)
네이버 시세·지표·수급·컨센서스와 그 파생 전부(data.js · auto_analysis · indicators · history · radar · rotation · market_context · flow_history · research_shadow · price_provenance · 성적표·모델 파일) ·
KIND 수집 자료(krx_list · sector_map · kind_market_action_evidence) · 모의투자 원장(paper_trading · paper_public) · 뉴스분석(news_analysis.js — 옛 시세로 만든 시장 통계가 본문에 섞임) ·
DART 원문 암호화 아카이브(research_archive/dart/live — 새 저장소는 새로 쌓는다) · 광고(AdSense·AdFit)·이용통계(GA·KVdb)·서비스워커 · 커뮤니티/방명록 · 옛 git 이력 전체.
광고를 다시 붙일지는 소유자 결정이다(OpenDART 상업적 이용 조건과 함께 봐야 한다 — 이 이전에서 붙이지 않았다).

## 5. 전환 절차(순서 고정 · 앞 단계가 실패하면 멈춘다)
1. (소유자) 빈 public 저장소 생성 — 이름 `gaeo-research`(충돌 확인: 2026-09-24 계정 저장소 5개 중 없음).
2. (작업자) 이 트리를 부모 없는 커밋으로 push → CI(ci.yml) 통과 확인.
3. (소유자) Settings → Pages → Source: **GitHub Actions** → pages.yml 로 임시 주소 `https://rudvh1016-gif.github.io/gaeo-research/` 확인.
   임시 주소는 하위 경로(`/gaeo-research/`)라 pages.yml 이 configure-pages 의 base_path 를 BASE_PATH 로 넘겨 링크를 맞춘다.
4. (소유자) Settings → Secrets → Actions: `OPEN_DART_API_KEY`(옛 저장소와 같은 키 — 새 키 발급 금지) · `RESEARCH_ARCHIVE_KEY`.
5. (작업자) 옛 저장소 예약 수집(corporate-action-evidence cron) 정지 PR → 병합 → `bash tools/migration/sync_dart_state.sh <옛 clone>` 로 최신 DART 상태 동기화 커밋.
6. (소유자) Settings → Variables → Actions: `DART_PRODUCER_ACTIVE` = `true` (이때부터 새 저장소만 예약 수집 — 같은 키 동시 소비 없음).
7. (작업자) workflow_dispatch 로 40종목·300요청 스모크 → 산출물 커밋·누출 검사 PASS 확인.
8. (소유자) 옛 저장소 Settings → Pages 에서 커스텀 도메인 제거 → 새 저장소 Settings → Pages → Custom domain `gaeoteam.com` 입력 · Enforce HTTPS.
   DNS 는 GitHub Pages 를 가리키고 있으므로 레코드 변경은 필요 없을 것으로 본다(미확인 — 도메인 검증(verified domain) 설정이 있으면 그대로 유지).
9. (작업자) gaeoteam.com 모바일 390px·PC 화면·링크·DART 원문 링크 확인.
10. (작업자) GAEO Private 의 공개 자료 주소(raw.githubusercontent.com/…/gaeo-analyst-team/main)를 새 저장소로 바꾸는 PR — 옛 저장소가 private 가 되면 옛 주소는 404 가 된다.
11. (소유자) 위가 모두 확인된 뒤에만 옛 저장소 Settings → General → Danger Zone → Change visibility → Private.
