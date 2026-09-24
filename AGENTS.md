# GAEO 기업 리서치 (공개) — 작업 철칙

1. **공개 저장소다.** 네이버 금융·KIND 자료(원자료·파생·시세·수급·컨센서스)를 다시 수집하거나 들여오지 않는다. 새 공급원을 추가하지 않는다.
2. 자료는 **OpenDART 공시 사실**과 운영자가 쓴 공부 글뿐이다. 수집기 호스트는 opendart.fss.or.kr·dart.fss.or.kr 만 허용(`tools/public_checks.py --producer-hosts`).
3. **Toss·계좌·보유종목·모의투자(PAPER)·GAEO Private 자료를 이 저장소·사이트에 싣지 않는다 — 영구.**
4. 매수·매도 추천, 목표 수익률, 수익 보장, 개인 맞춤 매매 조언, 1:1 상담, 유료 리딩 기능을 만들지 않는다.
5. 과거 분석은 「과거 분석 기록 · 작성 당시 기준 · 현재의 매수·매도 추천이 아님」 표시를 유지한다. 세척본 검사기를 약화시키지 않는다.
6. OpenDART 키를 코드·로그·채팅에 출력하지 않는다. 키를 새로 만들어 한도를 우회하지 않는다. 하루 예산 원장(`research_archive/dart/api_budget.json`)을 지킨다.
7. 사이트는 `_site` 허용목록만 배포한다. 광고·이용통계·서비스워커를 소유자 결정 없이 붙이지 않는다.
8. 글자 크기 상한: 페이지 제목 모바일 ≤26px · PC ≤30px · 본문 15~16px. 30px 넘는 글자는 검사기가 막는다.
9. force push · 이력 재작성 금지. 옛 저장소(gaeo-analyst-team)의 이력을 이 저장소로 가져오지 않는다.

변경 전후: `python3 tools/build_site.py && python3 tools/public_checks.py --all` + README 의 unittest.
