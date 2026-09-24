"""과거 정밀분석 세척본 검사기 (LLM 0 · 네트워크 0).

공개 파일(content/past_analysis.json)의 모든 문장에 시세·주가배수·컨센서스·목표가·수급·증권사 인용·점수·매매 권유가
없는지 본다. 허용 숫자는 날짜(연·분기·월·일)뿐이다.
사용: python3 tools/migration/validate_past_analysis.py content/past_analysis.json
"""
import json, re, sys
FIELDS = ("whatWeSaw", "whyViewed", "wrongIf", "studyNext", "dartCheck")
CLASSES = {"SANITIZE_AND_RESTORE", "PRIVATE_ONLY", "SAFE_AS_IS"}
REMOVED = {"NAVER_PRICE", "NAVER_VALUATION", "CONSENSUS", "NAVER_FLOW", "THIRD_PARTY_REPORT",
           "NEWS_RELAY", "RECOMMENDATION", "SCORE", "TARGET_PRICE"}
# 허용 숫자: 연도·분기·월·일·반기, 'N년'(기간), 'N가지' 등 서술. 그 밖의 숫자는 네이버 유래 수치일 수 있어 막는다.
ALLOWED_NUM = re.compile(r"(19|20)\d\d년|\d{1,2}분기|\d{1,2}월|\d{1,2}일|[1-9]개?년|[1-9]가지|[1-9]곳|상반기|하반기")
FORBIDDEN = [r"PER", r"PBR", r"EPS", r"ROE", r"RSI", r"MACD", r"MA\d", r"컨센서스", r"목표\s*주?가", r"상승\s*여력",
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
