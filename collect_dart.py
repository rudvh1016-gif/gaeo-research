#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DART 수집 실행기 — 워크플로에서 부른다.

⚠️ 이 스크립트는 실패해도 절대 0이 아닌 종료코드를 내지 않는다(요구 15번).
   DART가 죽어도 Price / TARO / DIANA / FLOW / ROTATION 워크플로는 계속 돈다.

⚠️ 여기서 모은 데이터는 research_v1.0 / v1.1의 판단에 들어가지 않는다.
   research_v2.0에서 처음으로 Feature가 된다.

사용:
    python3 collect_dart.py            # 신규공시 수집(매 사이클)
    python3 collect_dart.py --map      # corp_code 매핑 테이블 갱신(가끔)
    python3 collect_dart.py --self-test  # 네트워크 없이 로직만 점검
"""
import datetime
import json
import os
import sys

import dart_budget
import dart_client
import dart_pipeline as P
import dart_time
import research_store

HERE = os.path.dirname(os.path.abspath(__file__))
DART_ROOT = P.DART_ROOT
STATUS_PATH = os.path.join(DART_ROOT, "collection_status.json")
BUDGET_PATH = os.path.join(DART_ROOT, "api_budget.json")


def _now_iso():
    return dart_time.iso_now()


def _dart_store():
    """DART Raw도 같은 Archive 정책(Segment·gzip·manifest)을 쓴다.

    ⚠️ 단 스키마는 다르다. DART Raw에는 modelVersion이 없으므로
       Research Prediction 검사기를 그대로 쓰면 정상 Event가 손상으로 잡힌다.
    """
    return research_store.ResearchArchiveStore(
        root=DART_ROOT, record_type=research_store.RECORD_DART, encrypt=True)


def write_status(payload):
    payload = dict(payload)
    observed = payload.pop('_researchObservedFilings', None)
    os.makedirs(DART_ROOT, exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    # 옛 저장소는 여기서 dart_research.preserve_collection 으로 분석 판단 기록(research_archive/decisions)과
    # 공시를 이었다. 새 저장소에는 그 판단 기록이 없으므로 잇지 않는다(observed 는 버린다).
    del observed


def refresh_corp_map(client, budget=None):
    """corp_code 매핑 테이블 갱신. 자주 부를 필요 없다(하루 1회 이하)."""
    universe = P.load_universe()
    if budget is not None and not budget.allow("mapping"):
        return {"status": dart_budget.DART_BUDGET_EXCEEDED,
                "error": "일일 예산이 부족해 매핑 갱신을 미룹니다."}
    res = client.corp_code_zip()
    if budget is not None:
        budget.spend("mapping")
    if res["status"] != dart_client.OK:
        return {"status": res["status"], "error": res["error"],
                "universeSize": len(universe)}
    try:
        rows = P.parse_corp_code_zip(res["data"])
    except Exception as ex:
        return {"status": P.EVENT_DATA_ERROR,
                "error": dart_client.redact(f"corpCode 파싱 실패: {ex}")}
    cmap = P.build_corp_map(rows, universe)
    P.save_corp_map(cmap)
    rate = cmap["mappedCount"] / cmap["universeSize"] if cmap["universeSize"] else 0
    ambiguous = sum(1 for u in cmap["unknown"] if u.get("candidates"))
    return {"status": dart_client.OK, "dartCompanies": len(rows),
            "universeSize": cmap["universeSize"], "mapped": cmap["mappedCount"],
            "unknown": cmap["unknownCount"] - ambiguous, "ambiguous": ambiguous,
            "mappingRate": round(rate, 4)}


def collect(client, corp_map, budget=None):
    """오늘 신규공시를 모아 Daily Segment에 저장한다.

    ⚠️ Durable Write 순서를 지킨다.
       발견 → 정규화 → **Raw 저장 성공 확인** → 그 다음 Seen ACKNOWLEDGE.
       저장 전에 '봤다'고 확정하면, 저장이 실패한 공시가 영원히 사라진다.
    """
    started = _now_iso()
    # Reuse the same bounded collector. Re-query yesterday so an entire prior
    # receipt day, including after-close filings, can have an absence proof.
    today = dart_time.today_kst()
    prior = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
    result = P.collect_new_filings(client, corp_map, bgn_de=prior.replace('-', ''),
                                  end_de=today.replace('-', ''), budget=budget)
    events = result["events"]
    registry = result["registry"]
    pagination = result["pagination"]

    stored = 0
    store_errors = []
    acknowledged = 0
    if events:
        store = _dart_store()
        day = dart_time.today_kst()
        records = [dict(e, date=day) for e in events]
        try:
            state = store.segment_state(day, today=day)
            if state in ("CLOSED", "COMPRESSED"):
                raise PermissionError(f"{day} Segment가 {state}라 기록할 수 없다")
            added, replaced = store.append_predictions(day, records, today=day)
            stored = added + replaced
            # 저장이 실제로 읽히는지 확인한 뒤에만 ACK. 여기서 실패하면 재시도된다.
            saved_keys = {str(r.get("rcept_no")) for r in store.read_day(day)}
            ok_nos = [e["rcept_no"] for e in events if e["rcept_no"] in saved_keys]
            missing = [e["rcept_no"] for e in events if e["rcept_no"] not in saved_keys]
            for no in ok_nos:
                registry.mark_stored(no)
            registry.acknowledge_many(ok_nos)
            acknowledged = len(ok_nos)
            if missing:
                store_errors.append({"stage": "verify",
                                     "error": f"저장 확인 실패 {len(missing)}건 — 다음 실행에서 재시도"})
        except Exception as ex:
            # 저장 실패. ACK를 하지 않았으므로 다음 실행에서 다시 수집된다.
            store_errors.append({"stage": "append",
                                 "error": dart_client.redact(str(ex))[:200]})

    # 저장 결과가 확정된 뒤에 registry를 디스크에 쓴다.
    registry.save()

    state, reasons = P.coverage_state(events, result["errors"] + store_errors,
                                      client.has_key, pagination)
    finished = _now_iso()
    return {
        "startedAt": started, "finishedAt": finished,
        "queryWindow": {"start": prior, "end": today},
        "_researchObservedFilings": result.get('researchObservedFilings'),
        "eventState": state, "coverageReasons": reasons,
        "coverageNote": P.COVERAGE_NOTE,
        "pagination": pagination,
        "eventsFound": len(events), "eventsStored": stored,
        "eventsAcknowledged": acknowledged,
        "pendingRetryNext": registry.pending_count(),
        "efficiency": client.efficiency_report({
            "new_filings_detected": result["stats"]["new_filings_detected"],
            "matched_gaeo_filings": result["stats"]["matched_gaeo_filings"],
            "duplicate_skipped": result["stats"]["duplicate_skipped"],
            "unmatched_filings": result["stats"]["unmatched_filings"],
            "pages_fetched": result["stats"]["pages_fetched"],
            "list_requests": result["stats"]["list_requests"],
            "processing_duration_sec": None,
        }),
        "seenTotal": result["seenTotal"],
        "errors": result["errors"] + store_errors,
    }


def self_test():
    """네트워크·API Key 없이 파이프라인 로직만 점검한다."""
    universe = P.load_universe()
    fake_dart = [{"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930"},
                 {"corp_code": "00164779", "corp_name": "SK하이닉스", "stock_code": "000660"},
                 {"corp_code": "99999999", "corp_name": "비상장회사", "stock_code": ""}]
    cmap = P.build_corp_map(fake_dart, universe)
    print(f"자체점검 · 유니버스 {cmap['universeSize']}종목 중 "
          f"매핑 {cmap['mappedCount']}건 · UNKNOWN_MAPPING {cmap['unknownCount']}건")
    ev = P.normalize_filing(
        {"corp_code": "00126380", "report_nm": "[기재정정]현금·현물배당 결정",
         "rcept_no": "20260815000001", "corp_cls": "Y", "rcept_dt": "20260815"},
        cmap["mapped"].get("005930"), _now_iso())
    print(f"정규화 예시 · ticker={ev['ticker']} · is_correction={ev['is_correction']} "
          f"· rcept_dt 해석={ev['rcept_dt_note']}")
    print(f"PIT 규칙 · 발견 이전 시점 사용 가능? "
          f"{P.event_visible_at(ev, '2026-01-01T00:00:00+00:00')} (False여야 정상)")
    return 0


def main():
    args = set(sys.argv[1:])
    if "--self-test" in args:
        return self_test()

    client = dart_client.DartClient()
    budget = dart_budget.DailyBudget(BUDGET_PATH)
    payload = {"ranAt": _now_iso(), "hasApiKey": client.has_key,
               "kstToday": dart_time.today_kst(),
               "note": ("DART 수집 전용. research_v1.0 / v1.1 판단에 사용하지 않는다. "
                        "최초 사용 버전은 research_v2.0이다.")}

    if not client.has_key:
        # 키가 없어도 파이프라인을 죽이지 않는다.
        payload.update({"status": dart_client.DART_KEY_MISSING,
                        "eventState": P.EVENT_COVERAGE_INCOMPLETE,
                        "hint": f"{dart_client.KEY_ENV}를 GitHub Secrets로 주입하세요."})
        write_status(payload)
        print(f"[DART] {dart_client.KEY_ENV} 없음 — 수집 생략(파이프라인은 계속 진행)")
        return 0

    try:
        # ⚠️ 유니버스가 늘었는데 기존 매핑 테이블을 그대로 쓰면, 새로 추가된 종목은
        #    영원히 DART 매핑이 안 된다(2026-08-15 500 → 600 확대 때 실제로 발견).
        #    저장된 universeSize와 지금 종목 수가 다르면 매핑을 다시 만든다.
        existing_map = P.load_corp_map()
        universe_changed = bool(
            existing_map and existing_map.get("universeSize") != len(P.load_universe()))
        if universe_changed:
            print(f"[DART] 유니버스 변경 감지 — 매핑 {existing_map.get('universeSize')}종목 기준 "
                  f"→ 현재 {len(P.load_universe())}종목. 매핑 테이블을 다시 만듭니다.")
        if "--map" in args or existing_map is None or universe_changed:
            payload["mapping"] = refresh_corp_map(client, budget)
            print(f"[DART] 매핑 — {payload['mapping']}")
        corp_map = P.load_corp_map()
        if not corp_map:
            payload.update({"status": P.EVENT_DATA_ERROR,
                            "eventState": P.EVENT_COVERAGE_INCOMPLETE,
                            "error": "corp_map을 만들지 못했습니다"})
            write_status(payload)
            print("[DART] 매핑 테이블 없음 — 수집 생략")
            return 0
        payload.update(collect(client, corp_map, budget))
        payload["status"] = dart_client.OK if not payload["errors"] else P.EVENT_DATA_ERROR

        # DART Raw도 Daily Segment → gzip → manifest 정책을 그대로 쓴다.
        try:
            payload["maintenance"] = _dart_store().maintain()
        except Exception as ex:
            payload["maintenanceError"] = dart_client.redact(str(ex))[:200]

        payload["budget"] = budget.report()
        print(f"[DART] {payload['eventState']} · 신규 {payload['efficiency']['new_filings_detected']}건 "
              f"· 유니버스 매칭 {payload['efficiency']['matched_gaeo_filings']}건 "
              f"· 중복 skip {payload['efficiency']['duplicate_skipped']}건 "
              f"· 호출 {payload['efficiency']['requests_per_run']}회 "
              f"· 오늘 누적 {payload['budget']['requests_today']}건 "
              f"({payload['budget']['usage_pct_of_hard_limit']}% of {budget.hard_limit}) "
              f"· {payload['budget']['status']}")
    except Exception as ex:
        # 여기까지 오면 예상 못 한 오류다. 그래도 워크플로를 죽이지 않는다.
        payload.update({"status": P.EVENT_DATA_ERROR,
                        "eventState": P.EVENT_DATA_ERROR,
                        "error": dart_client.redact(f"{type(ex).__name__}: {ex}")[:300]})
        print(f"[DART] 수집 실패 — 나머지 파이프라인은 계속 진행: {payload['error']}")

    try:
        budget.save()
        payload.setdefault("budget", budget.report())
    except OSError as ex:
        payload["budgetSaveError"] = str(ex)[:120]
    write_status(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
