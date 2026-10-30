#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenDART 연간 재무제표 수집 — DIANA v2.0 / Piotroski F-Score 준비 (2026-09-04 신설).

왜 새로 만드는가
  `docs/gaeo_diana_v2_feature_registry.md` 10절 3번이 막힌 항목으로 남겨둔 것이다.
  `accruals`·`assetGrowth`, 그리고 Piotroski F-Score는 **여러 회계연도**가 있어야
  계산된다. 그런데 `dart_client.financial_statement()`는 지금 스모크 테스트에서만
  쓰이고 일일 수집에 연결돼 있지 않다. 이 파일이 그 수집 경로다.

⚠️ 예산이 이 설계의 핵심이다
  600종목 × 3개 회계연도 = 1,800회다. `dart_budget.NORMAL_TARGET_PER_DAY`는 500회다.
  한 번에 다 받으면 안 된다. 그래서:
    - 한 실행에서 받을 회사 수와 호출 수에 상한을 둔다(기본 40개사 · 150호출).
    - 이미 저장한 (회사, 연도)는 다시 받지 않는다. 연간 재무는 1년에 한 번만 바뀐다.
    - 결손이 있는 회사를 순회한다. 반복 실패가 뒤 회사를 막지 않도록 이어서 시작한다.
      그러면 유니버스 한 바퀴에 약 2주가 걸리고,
      그 뒤로는 새 사업보고서가 나온 회사만 갱신하면 된다.
    - 예산 상태가 나쁘면(`financial`은 OPTIONAL) 조용히 멈춘다.

⚠️ 이 파일은 점수를 만들지 않는다. 수집과 저장만 한다.
   F-Score 계산은 `piotroski.py`, 화면 반영 여부는 검증 절차를 따른다.
"""
import argparse
import json
import os
import tempfile

import dart_budget
import dart_client
import dart_pipeline as P
import dart_time

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(HERE, "dart_financials")
STATUS_PATH = os.path.join(STORE_DIR, "_status.json")

# Piotroski는 회계연도 3개가 필요하다(논문 분모가 '기초 총자산'이라 작년치를
# 계산하려면 전전기말 자산이 또 필요하다). piotroski.compute의 설명 참조.
YEARS_NEEDED = 3
DEFAULT_MAX_COMPANIES = 40
DEFAULT_MAX_CALLS = 150

SKIPPED_NO_KEY = "SKIPPED_NO_KEY"
SKIPPED_NO_MAPPING = "SKIPPED_NO_MAPPING"
SKIPPED_BUDGET = "SKIPPED_BUDGET"
SKIPPED_ALREADY_TODAY = "SKIPPED_ALREADY_TODAY"
OK = "OK"
PARTIAL = "PARTIAL"


class InvalidFinancialStore(Exception):
    """An existing company file could not be verified and must not be replaced."""


def already_ran_today(budget):
    """오늘 이미 재무를 받았으면 True.

    ⚠️ 이 게이트가 없으면 예산이 터진다. update-analysis 워크플로는 장중 30분마다,
       하루 14회 안팎 돈다. 한 번에 150호출이면 하루 2,100호출이 되는데
       `dart_budget.NORMAL_TARGET_PER_DAY`는 500이다.
       연간 재무는 1년에 한 번만 바뀌므로 하루 한 번이면 충분하다.
       별도 마커 파일을 만들지 않고 이미 있는 예산 카운터를 쓴다
       (같은 날짜 기준·같은 파일이라 어긋날 일이 없다).
    """
    return bool(budget) and (budget.counts.get("financial") or 0) > 0


def target_years(today=None):
    """받을 회계연도. 사업보고서는 회계연도 종료 뒤 3개월 안에 나오므로,
    3월 이전에는 작년치가 아직 없을 수 있다. 그래서 한 해 앞에서 시작한다."""
    day = today or dart_time.today_kst()
    year, month = int(str(day)[:4]), int(str(day)[5:7])
    latest = year - 1 if month >= 4 else year - 2
    return [latest - i for i in range(YEARS_NEEDED)]


def store_path(ticker):
    return os.path.join(STORE_DIR, f"{ticker}.json")


def load_company(ticker, strict=False):
    path = store_path(ticker)
    if not os.path.exists(path):
        if strict and os.path.lexists(path):
            raise InvalidFinancialStore()
        return {"ticker": ticker, "years": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if (isinstance(data, dict) and isinstance(data.get("years"), dict)
                and (not strict or data.get("ticker") == ticker)):
            if strict:
                for year, record in data["years"].items():
                    if (not isinstance(year, str) or len(year) != 4 or not year.isascii()
                            or not year.isdecimal() or not isinstance(record, dict)
                            or record.get("status") not in (OK, "NO_DATA")):
                        raise InvalidFinancialStore()
                    if record["status"] == OK and (record.get("fsDiv") not in ("CFS", "OFS")
                                                    or not isinstance(record.get("values"), dict)):
                        raise InvalidFinancialStore()
            return data
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        pass
    if strict:
        raise InvalidFinancialStore()
    return {"ticker": ticker, "years": {}}


def save_company(doc):
    os.makedirs(STORE_DIR, exist_ok=True)
    tmp = store_path(doc["ticker"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, store_path(doc["ticker"]))


def missing_years(ticker, years):
    """아직 안 받은 회계연도. 이미 'NO_DATA'로 확인된 해는 다시 묻지 않는다."""
    doc = load_company(ticker)
    have = doc.get("years") or {}
    return [y for y in years if str(y) not in have]


def pick_companies(corp_map, years, limit, after=None):
    """Cycle through incomplete companies so persistent failures cannot starve the rest."""
    mapped = (corp_map or {}).get("mapped") or {}
    rows = []
    for ticker, entry in mapped.items():
        try:
            doc = load_company(ticker, strict=True)
            need = [year for year in years if str(year) not in doc["years"]]
        except InvalidFinancialStore:
            # Report this company even if corrupt year keys appear complete.
            need = list(years)
        if need:
            rows.append((len(need), ticker, entry, need))
    rows.sort(key=lambda r: r[1])
    if after:
        rows = [r for r in rows if r[1] > after] + [r for r in rows if r[1] <= after]
    return rows[:limit]


def valid_financial_rows(rows, corp_code, year, reprt_code):
    """Check documented identity/currency fields without inventing missing accounts."""
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        return False
    for row in rows:
        if (row.get("corp_code") != corp_code or row.get("bsns_year") != str(year)
                or row.get("reprt_code") != reprt_code or row.get("currency") != "KRW"):
            return False
        for key in ("account_id", "account_nm", "sj_div", "thstrm_amount"):
            if row.get(key) is not None and not isinstance(row[key], str):
                return False
    return any((isinstance(row.get("account_id"), str) and row["account_id"].strip()
                or isinstance(row.get("account_nm"), str) and row["account_nm"].strip())
               and "thstrm_amount" in row for row in rows)


def collect(client, corp_map, budget=None, max_companies=DEFAULT_MAX_COMPANIES,
            max_calls=DEFAULT_MAX_CALLS, today=None, once_per_day=False, selection_after=None):
    started = dart_time.iso_now()
    if once_per_day and already_ran_today(budget):
        return {"status": SKIPPED_ALREADY_TODAY, "startedAt": started,
                "financialCallsToday": budget.counts.get("financial"),
                "reason": "오늘 이미 재무를 받았다. 연간 재무는 하루 한 번이면 충분하다."}
    if not client.has_key:
        return {"status": SKIPPED_NO_KEY, "startedAt": started,
                "reason": "OPEN_DART_API_KEY가 없어 재무 수집을 건너뛴다."}
    if not ((corp_map or {}).get("mapped")):
        return {"status": SKIPPED_NO_MAPPING, "startedAt": started,
                "reason": "corp_code 매핑이 없어 재무 수집을 건너뛴다."}

    years = target_years(today)
    picks = pick_companies(corp_map, years, max_companies, selection_after)
    cursor = selection_after
    calls = 0
    stored = 0
    no_data = 0
    errors = []
    coverage_samples = []
    budget_stopped = False

    for _need_n, ticker, entry, need in picks:
        if calls >= max_calls or budget_stopped:
            break
        try:
            doc = load_company(ticker, strict=True)
        except InvalidFinancialStore:
            errors.append({"ticker": ticker, "status": "STORE_UNVERIFIED"})
            cursor = ticker
            continue
        # The file may have gained a year since the initial selection.
        need = [year for year in need if str(year) not in doc["years"]]
        calls_before = calls
        changed = False
        for year in need:
            if calls >= max_calls:
                break
            # financial은 OPTIONAL이라 예산이 빠듯하면 여기서 멈춘다.
            if budget is not None and not budget.allow("financial"):
                budget_stopped = True
                break
            got = None
            absence = []
            failed = False
            for fs_div in ("CFS", "OFS"):
                if calls >= max_calls or (budget is not None and not budget.allow("financial")):
                    budget_stopped = True
                    break
                if budget is not None:
                    budget.spend("financial")
                calls += 1
                try:
                    res = client.financial_statement(entry["corp_code"], year,
                                                     P.REPRT_CODES["FY"], fs_div)
                except Exception:
                    # Don't persist exception text: it can contain a URL or credential.
                    res = {"status": "CLIENT_EXCEPTION"}
                payload = res.get("data") if isinstance(res, dict) else None
                rows = payload.get("list") if isinstance(payload, dict) else None
                if (isinstance(res, dict) and res.get("status") == dart_client.OK
                        and isinstance(payload, dict) and payload.get("status") == dart_client.STATUS_OK
                        and ("noData" not in res or res.get("noData") is False)
                        and valid_financial_rows(rows, entry["corp_code"], year, P.REPRT_CODES["FY"])):
                    got = (fs_div, payload)
                    break
                if (isinstance(res, dict) and res.get("status") == dart_client.OK
                        and res.get("noData") is True and isinstance(payload, dict)
                        and payload.get("status") == dart_client.STATUS_NO_DATA
                        and ("list" not in payload or rows == [])):
                    absence.append(fs_div)
                    continue
                failed = True
                status = res.get("status") if isinstance(res, dict) else None
                known_errors = (dart_client.EVENT_DATA_ERROR, dart_client.DART_KEY_MISSING,
                                dart_client.DART_UNREACHABLE, "CLIENT_EXCEPTION")
                errors.append({"ticker": ticker, "year": year, "fsDiv": fs_div,
                               "status": status if status in known_errors else "INVALID_RESPONSE"})
                break
            if budget_stopped and not got:
                break
            if not got:
                if failed or absence != ["CFS", "OFS"]:
                    # Failed or interrupted is not absence; leave it retryable.
                    continue
                # Confirmed independently for both bases; avoid unnecessary repeat calls.
                doc["years"][str(year)] = {"status": "NO_DATA",
                                           "checkedAt": dart_time.iso_now(),
                                           "absenceEvidence": {"CFS": "013", "OFS": "013"}}
                no_data += 1
                changed = True
                continue
            fs_div, payload = got
            try:
                ext = P.extract_financials(payload, sector=entry.get("sector"))
            except Exception:
                errors.append({"ticker": ticker, "year": year, "fsDiv": fs_div,
                               "status": "EXTRACT_ERROR"})
                continue
            doc["years"][str(year)] = {
                "status": OK,
                "fsDiv": fs_div,
                "reprtCode": P.REPRT_CODES["FY"],
                "values": ext["values"],
                "coverage": round(ext["coverage"], 4),
                "found": ext["found"],
                "missing": ext["missing"],
                "notApplicable": ext["notApplicable"],
                "matchedBy": ext["matchedBy"],
                "sectorHandling": ext["sectorHandling"],
                "collectedAt": dart_time.iso_now(),
            }
            coverage_samples.append(ext["coverage"])
            stored += 1
            changed = True
        if changed:
            doc["updatedAt"] = dart_time.iso_now()
            save_company(doc)
        if calls > calls_before or not need:
            cursor = ticker

    avg_cov = round(sum(coverage_samples) / len(coverage_samples), 4) if coverage_samples else None
    return {
        "status": PARTIAL if errors else OK,
        "startedAt": started,
        "finishedAt": dart_time.iso_now(),
        "targetYears": years,
        "companiesConsidered": len(picks),
        "apiCalls": calls,
        "yearsStored": stored,
        "yearsNoData": no_data,
        "averageCoverage": avg_cov,
        "budgetStopped": budget_stopped,
        "selectionCursor": cursor,
        "errors": errors[:20],
        "note": ("연간 재무는 1년에 한 번만 바뀌므로 이미 받은 (회사, 연도)는 다시 받지 않는다. "
                 "유니버스 한 바퀴를 여러 날에 나눠 돈다."),
    }


def load_selection_cursor(path):
    """Keep the previous cursor across daily skips; do not reset a damaged status file."""
    try:
        with open(path, encoding="utf-8") as file:
            doc = json.load(file)
    except FileNotFoundError:
        if os.path.lexists(path):
            raise InvalidFinancialStore()
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise InvalidFinancialStore()
    if not isinstance(doc, dict):
        raise InvalidFinancialStore()
    cursor = doc.get("selectionCursor")
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) != 6
                               or not cursor.isascii() or not cursor.isdecimal()):
        raise InvalidFinancialStore()
    return cursor


def save_status(path, result):
    """Publish a complete status/cursor together; retain the prior file on write failure."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".financial-status-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=1, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def universe_readiness(corp_map=None, today=None):
    """Piotroski를 계산할 수 있는 회사가 몇 곳인지 정직하게 센다."""
    years = target_years(today)
    mapped = ((corp_map or P.load_corp_map() or {}).get("mapped") or {})
    tickers = list(mapped) or [f.split(".")[0] for f in os.listdir(STORE_DIR)] \
        if os.path.isdir(STORE_DIR) else list(mapped)
    ready = partial = none = 0
    for t in tickers:
        have = [y for y in years
                if (load_company(t).get("years") or {}).get(str(y), {}).get("status") == OK]
        if len(have) >= YEARS_NEEDED:
            ready += 1
        elif have:
            partial += 1
        else:
            none += 1
    total = ready + partial + none
    return {"targetYears": years, "companies": total, "readyForFScore": ready,
            "partial": partial, "noData": none,
            "readyPct": round(ready / total * 100, 1) if total else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-companies", type=int, default=DEFAULT_MAX_COMPANIES)
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    ap.add_argument("--readiness", action="store_true",
                    help="수집 없이 현재 준비 상태만 출력한다")
    ap.add_argument("--once-per-day", action="store_true",
                    help="오늘 이미 받았으면 건너뛴다(30분마다 도는 워크플로에서 쓴다)")
    args = ap.parse_args()
    if args.readiness:
        print(json.dumps(universe_readiness(), ensure_ascii=False, indent=1))
        return 0
    client = dart_client.DartClient()
    budget = dart_budget.DailyBudget(os.path.join(P.DART_ROOT, "api_budget.json"))
    corp_map = P.load_corp_map()
    try:
        cursor = load_selection_cursor(STATUS_PATH)
    except InvalidFinancialStore:
        print(json.dumps({"status": "STATUS_UNVERIFIED"}, ensure_ascii=False))
        return 1
    try:
        result = collect(client, corp_map, budget=budget,
                         max_companies=args.max_companies, max_calls=args.max_calls,
                         once_per_day=args.once_per_day, selection_after=cursor)
    finally:
        # Calls already spent must survive ordinary collector/write exceptions.
        # A process kill or host loss still requires separate budget reconciliation.
        budget.save() if hasattr(budget, "save") else None
    result.setdefault("selectionCursor", cursor)
    save_status(STATUS_PATH, result)
    print(json.dumps({k: v for k, v in result.items() if k != "errors"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
