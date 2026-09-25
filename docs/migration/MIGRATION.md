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
| SAFE_AS_IS | 1 |
| SANITIZE_AND_RESTORE | 34 |
| PRIVATE_ONLY | 0 |

방식(2026-09-25 보강 반영 — §7): 컨센서스·추정치·목표주가·투자의견·순매수/순매도·지분율·PER/PBR·증권사 연구원 인용·옛 사이트 시세 파일(data.js) 인용·원화 주가 문장만
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

## 6. 2026-09-24 보완 (GPT 재검토 #609 댓글 반영 · 새 전체 감사 아님)

### A. 과거 정밀분석 — 과도한 내부 필터 바로잡기
- "날짜 외 숫자·%·ROE 일괄 금지" 는 법률 기준이 아니라 내부 필터였다. 검사는 끄지 않고 범위만 나눴다.
  - 서술 문장(당시 기록·보충): 출처가 없는 숫자는 계속 막는다 — 근거 없는 과거 시세·수급·제3자 수치 차단 유지. PER·PBR(주가 필요)도 계속 막는다.
  - `dartFacts`: OpenDART 사업보고서 구조화 재무수치와 그 자체 계산(매출 증감률·영업이익률·기말자본 ROE)은 숫자·% 허용.
    단 검사기가 저장소 안 `dart_financials/` 로 **다시 계산해 같을 때만** 통과(`tools/migration/add_dart_facts.py` 와 같은 계산).
  - ROE·EPS 는 DART 로 계산 가능한 개념이라 낱말만으로 막지 않는다.
- 결과: 32건 중 23건에 공시 재무 사실 1~3줄을 되살렸다. 9건(009155 · 096770 · 195940 · 257720×3 · 267260 · 316140 · 402340)은 재무 자료가 아직 수집되지 않아 "미수집" 으로 표시한다(0 을 만들지 않음).
- 원래 분석일과 이번 편집일을 나눴다: 쪽 머리 「원래 분석일 · 이번 편집일 2026-09-24」, 문단 제목 「당시 기록」 과 「이번 편집에서 정리·보충한 생각 — 당시의 판단이 아님」, 공시 재무 사실은 「2026-09-24 편집에서 덧붙임 · 당시 분석의 근거가 아님」. 데이터에도 `editedAt` · `sectionOrigin` 을 적었다.
- "이동평균 위/아래" 문장은 삭제 대상이 아니다(세척기·검사기 모두 그 낱말로 지우지 않는다 — 확인함). 숫자를 지웠다고 옛 수집 방식의 문제가 해소된 것은 아니다: 당시 기록 문장은 네이버 유래 수치를 옮기지 않는 정성 서술만 남긴 것이다.
- 종목 공부 35건은 다시 쓰지 않았다. 뺀 문장은 컨센서스·목표주가·투자의견·수급·주가배수·증권사 인용(전부 네이버·제3자 유래)이라 DART 로 살릴 대상이 아니다.

### B. 옛 62쪽 ↔ 이번 34건 대응(1회 확인 · `research/deep-analysis/**/index.html` @ 옛 main)
| 옛 쪽 | 수 | 새 트리 |
|---|---|---|
| 전체 목록(`research/deep-analysis/`) | 1 | `/past-analysis/` |
| 목록 2쪽째(`page/2/`) | 1 | 목록 한 쪽으로 합침 |
| 회사별 목록 | 26 | 없음(전체 목록에서 회사별로 묶음) |
| 분석 기록 | 34 | 34건 모두 분류됨 — 공개 32 · 비공개 2(PRIVATE_ONLY) |
누락 0 · 중복 0. 공개 회사 25곳(비공개 2건 중 1건이 그 회사의 유일한 기록).

### C. 새 공개 저장소에 들어가는 중간 원자료 — 공개권한 확인
공개 저장소는 사이트에서 뺀 파일도 raw GitHub 로 누구나 받는다. 그래서 `_site` 제외가 아니라 **저장소에 넣어도 되는가** 로 봤다.
| 파일 | 담긴 것 | 근거 | 판정 |
|---|---|---|---|
| dart_financials/*.json | 사업보고서 표준 계정 수치·찾은/못 찾은 계정 | opendart derivedPublication APPROVED_WITH_CONDITIONS(구조화 재무수치) | 공개 가능 |
| research_archive/dart/seen_rcept.json | 접수번호·보고서명·종목코드·탐지시각 | 같은 결정(제목·접수번호) | 공개 가능 |
| research_archive/dart/corp_map.json | 종목코드↔고유번호·회사명·GAEO 자체 폴더명(sector) | OpenDART corpCode 식별자 + 자체 분류 | 공개 가능 |
| research_archive/dart/api_budget.json · collection_status.json | 자체 호출 수·수집 상태 | 제3자 내용 없음 | 공개 가능 |
| research_archive/dart/live/*.enc (수집 후 생김) | list.json 메타(제목·접수번호)의 **암호문** · 키는 Secret | 평문이어도 위 범위 · 공시 원문 본문은 없음 | 공개 가능(암호문) |
| gaeo_coverage/corporate_action_evidence.json | 관련 공시 제목·접수번호·자체 분류·응답 해시 | 같은 결정 | 공개 가능 |
| config/evidence_universe.json | 종목코드 2,600개(코드만) | 모든 코드가 OpenDART 고유번호와 매칭된 회사. 옛 대상 선택이 KIND 상장법인목록에서 왔지만 KIND 의 이름·시장·업종 필드는 없다 | 공개 가능 — 선택 출처만 기록 |
| tickers.js | 코드·회사명 600 | 옛 목록에서 코드·이름만(업종·시장 필드 제거) | 공개 가능 |
공시 원문 본문·첨부, 네이버·KIND 내용 필드, Toss 자료는 새 트리에 없다(`tools/public_checks.py --tree` · `--producer-hosts` 가 막는다).

### D. 전환 진행 상태(2026-09-24 실측)
- 1단계(소유자 · 새 public 저장소 `gaeo-research` 생성): **아직 확인되지 않음.** 이 세션에서 `rudvh1016-gif/gaeo-research` 는 "없음 또는 권한 없음". 저장소를 만든 뒤 Claude GitHub 앱이 그 저장소에 접근하도록 허용해야 2단계(부모 없는 커밋 push)를 진행할 수 있다.
- 2~11단계: 1단계 전이라 진행하지 않았다. 옛 저장소 DART 예약 수집은 그대로 돈다(유일한 생산자) — 새 저장소 쪽은 `DART_PRODUCER_ACTIVE` 가 없으면 예약 수집을 하지 않으므로 동시 소비가 생기지 않는다.
- 필요한 설정 이름(값은 적지 않는다): Secrets `OPEN_DART_API_KEY` · `RESEARCH_ARCHIVE_KEY`(옛 저장소와 같은 값) · Variables `DART_PRODUCER_ACTIVE`(5단계 뒤 `true`) · Pages Source `GitHub Actions` · Custom domain `gaeoteam.com`.
- 이 세션 로컬 검사: `tools/public_checks.py --all` 중 `[history]` 만 실패(이 작업 폴더가 옛 저장소 얕은 clone 을 빌려 써서) · `test_dart_live_hardening` 은 로컬 암호 라이브러리 부재 — 둘 다 새 저장소 CI(fetch-depth 0 · cryptography 설치)에서 확인한다.

## 7. 2026-09-25 PUBLIC LEGAL GATE (법률·약관 최종 판정 뒤 · 원본: `docs/legal/LEGAL_FINAL_20260925.md`)

### A. 게이트 결과
| 검사 | 결과 |
|---|---|
| NAVER raw · KIND raw · Toss raw | 0 (`public_checks.py --tree --site` PASS) |
| 계좌정보 · 개인 보유종목 · Secret · 실제 주문 | 0 (같은 검사) |
| 권리불명확 기사/리포트 전문 | 0 — 기사 표본 8건 원문 대조 일치 구간 573개 중 1개 · 리포트 PDF 직링크 제거 |
| 공개 허용이 확인되지 않은 raw database | 0 — 남은 DART 중간 JSON 은 공공데이터포털 이용허락범위 "제한 없음"/공공누리 제1유형 확인 |
| 추적기/광고 | 0 (사이트 전 파일: 분석 도구·광고·쿠키 생성·브라우저 저장소·sendBeacon·서비스워커 0) |
| 옛 git 이력 | 0 (`--history` PASS — 부모 없는 첫 커밋) |

### B. 이번에 고친 것
- 종목 공부 세척 보강: 옛 세척기가 "PER은"(한글 조사)·"시장에서는 …예상"·"비중확대 의견"·"100만원대 주가"·링크 제목 속 목표가를 놓쳤다 → 규칙 보강 후 원본(sha256 1076068…)에서 다시 생성. 결과 SAFE_AS_IS 1 · SANITIZE_AND_RESTORE 34 · PRIVATE_ONLY 0. 사업 뜻의 "비중 확대"·숫자 없는 "시장 예상을 웃돌았다" 는 지우지 않는다(과잉삭제 방지).
- 공유 이미지(og-image): 옛 서비스 문구("500종목 매일 자동분석 · AI 애널리스트 5인") → 현재 성격(공시 리서치 · 무료 · 광고 없음 · 추천 없음)으로 다시 그림.
- LICENSE: 코드·운영자 글과 제3자 자료(OpenDART·기사)를 구분 — 제3자 자료를 재라이선스하지 않는다고 명시. 없는 파일(옛 SOURCE_COMPLIANCE_MATRIX) 참조 제거.
- THIRD_PARTY_NOTICES · disclaimer: OpenDART 이용허락범위와 출처표시 추가.
- `public_checks.py`: Windows 에서 자기 자신을 검사 대상으로 잘못 잡던 경로 비교 수정(동작 변화는 Windows 로컬뿐).

### C. 전환 진행(2026-09-25 실측 · 앞 단계가 실패하면 멈춘다)
| # | 단계 | 결과 |
|---|---|---|
| 1 | gaeo-research push | 완료 — main `892d52a` (첫 커밋 `c807e3a` 부모 없음 · 옛 이력 0) |
| 2 | CI | 통과(ci run 36142192799) |
| 3 | 임시 Pages | 완료 — Source: GitHub Actions(API 로 설정) · https://rudvh1016-gif.github.io/gaeo-research/ HTTP 200 |
| 4 | 실제 화면 | 확인 — 홈 내부 링크 26개 깨짐 0 · 서체 로드 · 외부 스크립트 0 · 과거 분석 쪽 경고문·편집일 표시 · 주요 쪽 7개 200 |
| 5 | Secrets 확인 | **멈춤 — `OPEN_DART_API_KEY` · `RESEARCH_ARCHIVE_KEY` 가 없다.** 키 값 입력은 소유자만 한다(작업자는 비밀값을 다루지 않는다) |
| 6~14 | 옛 생산자 중지 · 상태 이관 · 새 생산자 · 자동수집 · gaeoteam.com · 모바일/PC · Private 주소 · Private 수신 · 옛 저장소 private | 5 전이라 실행하지 않음. 옛 저장소가 유일한 DART 생산자로 계속 돈다(동시 소비 0) |

5 뒤 순서(바뀐 점 1개): 6단계 옛 생산자 정지는 코드 PR 이 아니라 `gh workflow disable corporate-action-evidence.yml -R rudvh1016-gif/gaeo-analyst-team` 로 한다(되돌리기 쉽고 옛 저장소 준법 게이트 원장·테스트를 바꾸지 않는다). 이어서 `bash tools/migration/sync_dart_state.sh <옛 clone>` → Variables `DART_PRODUCER_ACTIVE=true` → workflow_dispatch 40종목·300요청 스모크 → 옛 저장소 Pages cname 제거 · 새 저장소 cname `gaeoteam.com`(옛 쪽은 legacy/main + CNAME 파일 · https_enforced true) → 390px/PC 확인 → Private `GAEO_PUBLIC_DATA_BASE_URL`(gaeo-private PR #153 환경변수 · Vercel 과 Oracle intelligence 두 곳) 교체 → Private 수신 확인 → 옛 저장소 private.

### D. 전환 진행 2 (2026-09-25 23:15~23:50 KST)
| # | 단계 | 결과 |
|---|---|---|
| 5 | Secrets | 완료 — `RESEARCH_ARCHIVE_KEY` 는 새로 생성(새 저장소에 옛 암호문 0개 · 이관 대상 아님 · Private 미사용 → 옛 키 호환 불필요, 값 출력 0) · `OPEN_DART_API_KEY` 는 소유자가 기존 키를 입력(재발급 안 함 — 약관 제19조⑤ 1인 1키) |
| 6 | 옛 생산자 중지 | 완료 — gaeo-analyst-team `corporate-action-evidence.yml` `disabled_manually`(코드 변경 없음) |
| 7 | DART 상태 이관 | 변경 0 — 옛 저장소 마지막 수집이 2026-09-24 15:32 KST(추석 휴장 9/24~26 예약 건너뛰기)라 새 저장소 값과 같았다 |
| 8 | 새 생산자 | 완료 — Variables `DART_PRODUCER_ACTIVE=true` |
| 9 | 자동수집 확인 | 완료 — workflow_dispatch 40종목·300요청: 1차는 누출 검사 `--history` 가 얕은 체크아웃 때문에 실패했는데도 커밋 단계가 돌았다(내용은 전체 검사 PASS 로 재확인) → 누출 검사 실패 시 커밋 금지로 수정(68a81cf) → 2차 수집·검사·커밋 모두 성공. 기업행사 증거 40/40 · 오늘의 공시 신규 0(휴장) |
| 10 | gaeoteam.com | 완료 — 옛 저장소 CNAME 제거(58a93a6) · Pages cname 해제 → 새 저장소 cname `gaeoteam.com` · 인증서 approved · HTTPS 강제. DNS(185.199.108~111.153) 변경 없음 |
| 11 | 모바일/PC | 완료 — 390px·1440px, 10쪽 가로 넘침 0 · 링크에 `/gaeo-research/` 경로 0 · www→apex · http→https |
| 12 | Private 주소 | 완료 — gaeo-private PR #157(c5bd820) 기본 주소를 gaeo-research 로(환경변수 불필요) · Oracle 배포 success · Vercel Production success |
| 13 | Private 수신 | Oracle intelligence 확인 — 배포 검증이 받은 공시 연구 `generatedAt 2026-09-25T14:29:07Z` = 새 저장소 값(옛 저장소는 09-24 06:32). ✗ Oracle `gaeo-mcp` 는 아직 옛 raw 주소를 읽는다(gaeo-gateway PR #9 준비 · 수동 배포 서비스) |
| 14 | 옛 저장소 private | **보류** — 지금 바꾸면 `gaeo-mcp get_disclosures` 가 404. PR #9 를 Oracle 에 배포한 뒤 전환 |
