# GAEO 기업 리서치 (공개) — 작업 철칙

1. **공개 저장소다.** 네이버 금융·KIND 자료(원자료·파생·시세·수급·컨센서스)를 다시 수집하거나 들여오지 않는다. 새 공급원을 추가하지 않는다.
2. 자료는 **OpenDART 공시 사실**과 운영자가 쓴 공부 글뿐이다. 수집기 호스트는 opendart.fss.or.kr·dart.fss.or.kr 만 허용(`tools/public_checks.py --producer-hosts`). 배포 뒤 검색엔진 알림(`tools/indexnow.py` → api.indexnow.org)은 수집이 아니다.
3. **Toss·계좌·보유종목·모의투자(PAPER)·GAEO Private 자료를 이 저장소·사이트에 싣지 않는다 — 영구.**
4. 매수·매도 추천, 목표 수익률, 수익 보장, 개인 맞춤 매매 조언, 1:1 상담, 유료 리딩 기능을 만들지 않는다.
5. 과거 분석은 「과거 분석 기록 · 작성 당시 기준 · 현재의 매수·매도 추천이 아님」 표시를 유지한다. 세척본 검사기를 약화시키지 않는다.
6. OpenDART 키를 코드·로그·채팅에 출력하지 않는다. 키를 새로 만들어 한도를 우회하지 않는다. 하루 예산 원장(`research_archive/dart/api_budget.json`)을 지킨다.
7. 사이트는 `_site` 허용목록만 배포한다. 광고·서비스워커를 소유자 결정 없이 붙이지 않는다. 방문 통계는 소유자 결정(2026-09-28)으로 **GoatCounter 한 가지만**(쿠키 0 · IP 미저장) — 저장소 변수 `GOATCOUNTER_CODE` 가 있을 때만 빌드가 붙이고 개인정보처리방침 문단도 같이 바뀐다(`public_checks --site` 가 둘이 어긋나면 막는다). 다른 외부 스크립트는 붙이지 않는다.
8. **글자는 작게(2026-09-28 소유자 지시).** 본문 모바일 14px · PC 15px · 보조 13px · 카드 제목 15~16px · 섹션 18~20px · 페이지 제목 모바일 21px · PC 24px. 30px 넘는 글자는 검사기가 막는다.
9. force push · 이력 재작성 금지. 옛 저장소(gaeo-analyst-team)의 이력을 이 저장소로 가져오지 않는다.
10. **쉽게 끊어 읽히게 쓴다(2026-09-28 소유자 지시 · 앞으로도).** 글 본문은 1~2문장 문단으로 끊고(빌드 `md_html` 이 자동으로 끊는다), 핵심은 `**굵게**`. 공시 설명은 초보자 기준 「쉬운 이름 · 무슨 내용 · 왜 확인 · 원문에서 볼 곳」 네 칸(`content/disclosure_guide.json`)으로 쓰고, 좋다/나쁘다·사라/팔라는 판단을 쓰지 않는다. 법령 숫자(기한·기준 금액)는 확인한 날짜(`checkedOn`)를 적는다.
11. **공부 글에 넣지 않는 것** — 옛 사이트 수집 시세·지표(원화 주가·52주 범위·수집 시가총액·배당수익률·EPS/ROE), 주가배수(PER·PBR·EV/EBITDA·PSR), 증권사·시장 실적 추정치(컨센서스), 투자의견, 없어진 옛 기능 안내(RISK·TARO·DIANA 카드 등), 방송·책·강의 같은 남의 저작물 요약. `public_checks.py --content` 가 막는다(근거: `docs/legal/LEGAL_RECHECK_20260928.md`).
12. **검색 유입 구조를 지킨다.** 옛 사이트가 색인시킨 공부 글 주소 `/snap/{study,lesson,estate,calc}/<번호>.html` 은 빌드가 새 글로 되살린다(`snap/stock`·`snap/news` 는 은퇴 그대로 404). 회사 쪽 `/company/<종목코드>/`, 공시 사전 `/guide/`, 주간 공시 정리 `/weekly/<월요일>/`(매주 자동), `sitemap.xml`·`rss.xml`·`robots.txt`(다음 검색 확인 줄 유지)·`llms.txt`·IndexNow 키 파일도 빌드가 만든다. 계획·소유자 할 일: `docs/growth/GROWTH_20260928.md`.

변경 전후: `python3 tools/build_site.py && python3 tools/public_checks.py --all` + README 의 unittest. 빌드에는 Node.js 가 필요하다(`tools/content_dump.js` 가 공부 글을 브라우저와 같게 실행해 읽는다).
