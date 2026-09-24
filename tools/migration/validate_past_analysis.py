"""과거 정밀분석 세척본 검사기 (LLM 0 · 네트워크 0).

공개 파일(content/past_analysis.json)의 모든 문장에 시세·주가배수·컨센서스·목표가·수급·증권사 인용·점수·매매 권유가
없는지 본다. 서술 문장(whatWeSaw 등)의 허용 숫자는 날짜(연·분기·월·일)뿐이다 — 출처가 없는 숫자이기 때문이다.

2026-09-24 보완: "숫자·%·ROE 일괄 금지" 는 법률 기준이 아니라 내부 필터였다. 그래서
  · dartFacts(출처가 붙은 OpenDART 사업보고서 사실·자체 계산)는 숫자·% 를 허용하되, 저장소 안
    dart_financials/ 로 **다시 계산해 값이 같을 때만** 통과시킨다(add_dart_facts.facts_for 와 같은 계산).
  · ROE·EPS 는 DART 재무로 계산할 수 있는 개념이라 낱말만으로 막지 않는다. PER·PBR 은 주가가 필요해 계속 막는다.
  · 편집일(editedAt)과 문단별 출처(sectionOrigin)가 있어야 한다 — 이번 편집의 보충을 당시 판단처럼 보이지 않게.
검사 자체는 끄지 않는다.
사용: python3 tools/migration/validate_past_analysis.py content/past_analysis.json
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from add_dart_facts import facts_for  # noqa: E402
ORIGINS = {"ORIGINAL_RESTATED", "EDIT_SUPPLEMENT"}
FIELDS = ("whatWeSaw", "whyViewed", "wrongIf", "studyNext", "dartCheck")
CLASSES = {"SANITIZE_AND_RESTORE", "PRIVATE_ONLY", "SAFE_AS_IS"}
REMOVED = {"NAVER_PRICE", "NAVER_VALUATION", "CONSENSUS", "NAVER_FLOW", "THIRD_PARTY_REPORT",
           "NEWS_RELAY", "RECOMMENDATION", "SCORE", "TARGET_PRICE"}
# 허용 숫자: 연도·분기·월·일·반기, 'N년'(기간), 'N가지' 등 서술. 그 밖의 숫자는 네이버 유래 수치일 수 있어 막는다.
ALLOWED_NUM = re.compile(r"(19|20)\d\d년|\d{1,2}분기|\d{1,2}월|\d{1,2}일|[1-9]개?년|[1-9]가지|[1-9]곳|상반기|하반기")
FORBIDDEN = [r"PER", r"PBR", r"RSI", r"MACD", r"MA\d", r"컨센서스", r"목표\s*주?가", r"상승\s*여력",
             r"연구원", r"리포트", r"보고서에서\s*밝", r"증권(?!가|거래|시장|사)", r"[가-힣A-Z]+증권", r"순매수", r"순매도", r"보유율",
             r"매수", r"매도", r"추격", r"권합니다", r"권한다", r"BUY", r"SELL", r"HOLD", r"점수", r"신뢰도",
             r"\d+\s*점", r"%", r"배\b", r"원\)", r"만원", r"억원", r"조원", r"사세요", r"파세요", r"수익\s*보장", r"확실"]
def check(rec):
    errs = []
    if "classification" not in rec:        # 공개 파일 — 이미 복원으로 분류된 것만 들어 있다
        rec = dict(rec, classification="SANITIZE_AND_RESTORE", reason="(public)")
    if rec.get("classification") not in CLASSES: errs.append("classification")
    if not rec.get("reason"): errs.append("reason")
    for r in rec.get("removed", []):
        if r not in REMOVED: errs.append("removed:" + r)
    if rec.get("classification") == "SANITIZE_AND_RESTORE":
        for f in FIELDS:
            if not isinstance(rec.get(f), list) or not rec[f]: errs.append("empty:" + f)
        texts = [rec.get("title", "")] + [t for f in FIELDS for t in rec.get(f, [])]
        for t in texts:
            stripped = ALLOWED_NUM.sub("", t)
            if re.search(r"\d", stripped): errs.append("digit:" + t[:60])
            for p in FORBIDDEN:
                if re.search(p, t): errs.append(f"forbidden[{p}]:" + t[:60])
    if "editedAt" in rec or "sectionOrigin" in rec or "dartFacts" in rec:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(rec.get("editedAt", ""))): errs.append("editedAt")
        origin = rec.get("sectionOrigin") or {}
        for f in FIELDS:
            if origin.get(f) not in ORIGINS: errs.append("sectionOrigin:" + f)
        # 사실이 붙은 기록만 대조한다. 붙지 않은 기록은 "재무 미수집" 으로 보여 주며 0 을 만들지 않는다
        # (전환일에 dart_financials 가 늘어나도 편집일을 속여 사실을 자동으로 붙이지 않는다).
        if "dartFacts" in rec:
            expected = facts_for(rec["ticker"], int(rec["analyzedAt"][:4])) if rec.get("ticker") else []
            if not rec["dartFacts"] or rec["dartFacts"] != expected:
                errs.append("dartFacts:dart_financials 로 다시 계산한 값과 다르다")
        for fact in rec.get("dartFacts") or []:
            for p in FORBIDDEN:
                if p in (r"%",): continue
                if re.search(p, fact.get("text", "")): errs.append(f"forbidden[{p}]:" + fact.get("text", "")[:60])
    return errs
if __name__ == "__main__":
    bad = 0
    for path in sys.argv[1:]:
        data = json.load(open(path, encoding="utf-8"))
        for rec in (data["records"] if isinstance(data, dict) else data):
            e = check(rec)
            if e:
                bad += 1; print(rec.get("snapshotId"), e)
    print("FAIL" if bad else "PASS", bad)
    sys.exit(1 if bad else 0)
