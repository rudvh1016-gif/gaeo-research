#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""오늘의 공시 위젯 스냅샷(dart_today.js) — 네트워크 0 · LLM 0 (2026-09-24 신설).

왜 새로 만드는가
  dart_today.js 는 analyze_auto.py(update-analysis.yml · 30분 주기)가 자동분석 산출물의 곁가지로 만들었다.
  그 워크플로가 은퇴(네이버 유래 입력 · config/source_compliance.json retirement)하면서 홈의 '오늘의 공시'
  위젯이 함께 얼어붙게 됐다. 공시는 OpenDART(허용된 공식 API)에서 오므로 이 위젯만 따로 살린다 —
  collect_dart.py 가 남긴 research_archive/dart/seen_rcept.json(접수번호·보고서명·종목·탐지시각)만 읽는다.

무엇을 하지 않나
  · DART 를 부르지 않는다(수집은 collect_dart.py). 점수·판단을 만들지 않는다. 시세를 싣지 않는다.
  · '공시 없음' 을 '악재 없음' 으로 옮기지 않는다 — coverageState 를 그대로 싣는다.

출력 모양은 analyze_auto.py 가 만들던 것과 같다(app.js dartTodayItems · ops_status.check_dart 가 읽는다):
  {generatedAt, priceLabel, count, coverageState, note, items[{code,name,title,receiptDate,detectedAt,isCorrection,rceptNo}]}
"""
import datetime
import json
import os
import re
import sys

import dart_pipeline as P
import dart_time

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_PATH = os.path.join(P.DART_ROOT, "seen_rcept.json")
STATUS_PATH = os.path.join(P.DART_ROOT, "collection_status.json")
OUT_PATH = os.path.join(HERE, "dart_today.js")
PER_STOCK = 3          # 종목당 최근 3건 — 옛 dart_context_loader.public_event_summary 와 같은 수
RECENT_DAYS = 7

#: collect_dart.py 의 eventState → 위젯/상태판(ops_status.check_dart)이 아는 어휘
COVERAGE_MAP = {
    P.EVENT_DETECTED: "EVENT_DETECTED",
    P.NO_OFFICIAL_EVENT_DETECTED: "NO_EVENT",
    P.EVENT_COVERAGE_INCOMPLETE: "PARTIAL",
    P.EVENT_DATA_ERROR: "SOURCE_UNAVAILABLE",
}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_seen(path=SEEN_PATH):
    doc = _read_json(path) or {}
    seen = doc.get("seen")
    return seen if isinstance(seen, dict) else {}


def receipt_date(rcept_no):
    s = str(rcept_no or "")
    return s[:8] if len(s) >= 8 and s[:8].isdigit() else ""


def build(seen, names, status=None, now_kst=None):
    """순수 함수. 가장 최근 접수일의 공시만 싣는다(휴장일에는 마지막 거래일 접수분이 그대로 남는다)."""
    rows = []
    for rcept_no, entry in seen.items():
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("ticker") or "")
        title = " ".join(str(entry.get("report_name") or "").split())
        if not code or not title or code not in names:
            continue
        rows.append({
            "code": code,
            "name": names.get(code) or code,
            "title": title,
            "receiptDate": receipt_date(rcept_no),
            "detectedAt": entry.get("detected_at") or "",
            "isCorrection": bool(P.CORRECTION_HINT.search(title)),
            "rceptNo": str(rcept_no),
        })
    # analyze_auto.py 가 만들던 모양 그대로 — 종목마다 최근 3건(접수일 · 탐지시각 순), 최근 7일 접수분만.
    latest = max((r["receiptDate"] for r in rows if r["receiptDate"]), default="")
    items = []
    if latest:
        floor = (datetime.date(int(latest[:4]), int(latest[4:6]), int(latest[6:])) - datetime.timedelta(days=RECENT_DAYS - 1)).strftime("%Y%m%d")
        by_code = {}
        for r in sorted(rows, key=lambda r: (r["receiptDate"], r["detectedAt"]), reverse=True):
            if r["receiptDate"] < floor:
                continue
            by_code.setdefault(r["code"], [])
            if len(by_code[r["code"]]) < PER_STOCK:
                by_code[r["code"]].append(r)
        items = [r for group in by_code.values() for r in group]
    items.sort(key=lambda r: (r["detectedAt"], r["name"]), reverse=True)
    now = now_kst or datetime.datetime.now(dart_time.KST)
    state = COVERAGE_MAP.get((status or {}).get("eventState")) if isinstance(status, dict) else None
    earliest = min((r["receiptDate"] for r in items), default=latest)
    fmt = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}"
    day = f"{fmt(earliest)}~{fmt(latest)}" if latest else "확인 안 됨"
    return {
        "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
        # 시세 라벨 자리 — 시세 자료 공급은 2026-09-24 종료(config/source_compliance.json retirement). 거짓 시각을 만들지 않는다.
        "priceLabel": f"공시 접수일 {day} 기준 · 시세 자료 공급 종료(2026-09-24)",
        "count": len(items),
        "coverageState": state,
        "note": "금융감독원 전자공시(DART) 자동 수집(하루 2회 · corporate-action-evidence.yml). 참고 정보이며 점수·판단에는 쓰지 않는다.",
        "items": items,
    }


def main():
    names = {code: (meta.get("name") or code) for code, meta in P.load_universe().items()}
    seen = load_seen()
    if not seen:
        print("[dart_today] seen_rcept.json 을 읽지 못했다 — 기존 파일을 건드리지 않는다")
        return 1
    out = build(seen, names, _read_json(STATUS_PATH))
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("// 자동 생성: build_dart_today.py · 홈 '오늘의 공시' 위젯 전용 소형 스냅샷 (네트워크 0)\n"
                "// 원천: collect_dart.py 가 남긴 research_archive/dart/seen_rcept.json (OpenDART 공시 목록)\n"
                "const DART_TODAY = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")
    os.replace(tmp, OUT_PATH)
    print(f"[dart_today] 저장 완료 — 공시 {out['count']}건 · 접수일 {out['priceLabel']} · 상태 {out['coverageState']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
