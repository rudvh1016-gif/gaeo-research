# GAEO 기업 리서치 노트 (gaeoteam.com)

공시로 회사의 변화를 쉽게 읽고, 기업·투자를 공부하는 개인 리서치 노트.
매수·매도 추천, 수익 보장, 1:1 종목 상담, 유료 리딩을 하지 않는다.

| 메뉴 | 내용 | 자료 |
|---|---|---|
| 기업 리서치 | 오늘의 공시 · 공시 변화 · 재무 변화 · 사건 흐름 · 회사별 요약(`/company/<코드>/`) | OpenDART(하루 2회 자동) |
| 공시 사전 | 공시 종류별 쉬운 이름 · 무슨 내용 · 왜 확인 · 원문에서 볼 곳(`/guide/`) | content/disclosure_guide.json(운영자 작성) |
| 주간 공시 정리 | 한 주 공시를 종류별로 묶고 쉬운 설명(`/weekly/<월요일>/`, 매주 자동) | research_archive/dart/seen_rcept.json(OpenDART 목록) |
| 과거 정밀분석 | 2026년 7~8월 분석 기록 32건(세척본) | content/past_analysis.json |
| 종목 공부 · 투자 공부 · 계산기 | 작성 당시 기준 공부 글(`/snap/<묶음>/<번호>.html`) · 브라우저 계산기 | content/*.js |

## 구조
- `site/` 화면(html·css·js) · `content/` 글 자료 · 루트 `*.py` OpenDART 수집기 · `tools/` 조립·검사
- 사이트에 올라가는 것은 `python3 tools/build_site.py` 가 만든 `_site/` 뿐(허용목록). 저장소 전체를 내보내지 않는다.
- 빌드가 정적 쪽(공부 글 한 편씩 · 공시 사전 · 회사별 요약)과 `sitemap.xml`·`rss.xml`·`robots.txt`·`llms.txt` 를 만든다. 글 본문은 1~2문장 문단으로 끊어 그린다.
- 빌드에는 Node.js 가 필요하다(`tools/content_dump.js` 가 content/*.js 를 브라우저와 같게 실행해 읽는다).
- 자동 수집: `.github/workflows/corporate-action-evidence.yml` (예약 실행은 저장소 변수 `DART_PRODUCER_ACTIVE=true` 일 때만)
  - 2026-09-29: 기업행사 증거(2,600종목)는 예약 회차마다 **30분 안에서 커서부터 이어** 받고 중간 저장한다(한 바퀴에 2~3회차 ·
    `cycle` 에 진행률·최근 한 바퀴 완료 시각). 그 단계가 실패·시간 상한에 걸려도 오늘의 공시 수집·공시 연구 생성은 돈다.
  - 공시 목록은 끝까지 확인한 마지막 날부터 하루씩 다시 본다 — 한 회차에 최대 14일, 더 밀렸으면 **가장 오래된 날부터** 회차마다 이어 본다
    (`catchUp.state = CATCHUP_IN_PROGRESS` · 장애가 아니라 복구 진행).
  - 공시 연구(`disclosure_research/contract.json`)의 `generatedAt` 은 **여기까지 접수된 공시를 다 본 시각**이다(따라잡는 중이면 끝까지 본 날
    다음 날 0시 KST · 빌드 시각은 `builtAt`). 확인 기록이 없으면 만들지 않는다.
- 배포: `.github/workflows/pages.yml` — 조립 → 공개 검사 → 배포 → 바뀐 주소만 IndexNow 알림(`tools/indexnow.py`)
- 방문 통계: 저장소 변수 `GOATCOUNTER_CODE` 가 있을 때만 GoatCounter(쿠키 0)를 붙이고 개인정보처리방침 문단을 함께 바꾼다. 없으면 통계 없음.

## 검사
```
python3 -m unittest test_disclosure_research test_dart_budget_ledger test_corporate_action_evidence test_dart_pipeline test_dart_financials_collect test_dart_live_hardening test_corporate_action_classify test_secret_hygiene test_site_build
python3 tools/build_site.py
python3 tools/public_checks.py --all
```

이전 기록: `docs/migration/MIGRATION.md` · 법률 판정: `docs/legal/LEGAL_FINAL_20260925.md` · 재점검: `docs/legal/LEGAL_RECHECK_20260928.md` · 유입 계획: `docs/growth/GROWTH_20260928.md`
