#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공시 연구 산출물 — disclosure_research/{contract,disclosure_changes,financial_changes,event_timelines}.json

네트워크 0 · LLM 0 · 점수 0. 2026-09-24 GAEO FINAL CLOSURE(gaeo-analyst-team #607 · gaeo-private #149).

무엇을 만드나 (공개 사이트 disclosure-research.html 과 GAEO Private 가 같은 파일을 읽는다 · 계약 disclosure-research-public-v1)
  A 공시 변화 보드   disclosure_changes.json  회사별 최근 창 vs 이전 창의 공시 종류·건수 변화 + 공시 목록(원문 링크)
  B 재무 변화표      financial_changes.json   연간 사업보고서 표준 계정의 연도별 값·변화(연결/별도 구분 · 결측 ≠ 0)
  C 사건 타임라인    event_timelines.json     결정 → 신고 → 결과 → 완료 사슬을 공시 제목으로 잇는다(못 찾음 ≠ 미실행)

원천 (전부 저장소 안의 OpenDART 유래 파일 · 이 스크립트는 DART 를 부르지 않는다)
  list      research_archive/dart/seen_rcept.json          collect_dart.py 가 본 공시 목록(접수번호·보고서명·종목)
  evidence  gaeo_coverage/corporate_action_evidence.json    종목별 list.json 365일 조회에서 보존한 기업행사 관련 제목
  financial dart_financials/<ticker>.json                   collect_dart_financials.py 의 연간 재무(표준 계정)
  vocab     config/disclosure_research_vocab.json           분류 낱말·읽는 법·사슬 단계(사람이 고친다)

원칙
  · 결측은 0 이 아니다 — NOT_COLLECTED / NOT_APPLICABLE / NOT_FOUND 로 적는다.
  · 정정 공시는 정정으로 표시한다(제목 표식). 무엇이 바뀌었는지는 원문 비교의 몫이다.
  · 시세·수익률·점수·판단·수급·컨센서스는 싣지 않는다(contract.notIncluded · test_disclosure_research 가 고정).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys

import dart_pipeline as P
from collect_dart_financials import STORE_DIR as FIN_DIR, target_years

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "disclosure_research")
VOCAB_PATH = os.path.join(HERE, "config", "disclosure_research_vocab.json")
SEEN_PATH = os.path.join(P.DART_ROOT, "seen_rcept.json")
EVIDENCE_PATH = os.path.join(HERE, "gaeo_coverage", "corporate_action_evidence.json")

SCHEMA_VERSION = "gaeo_disclosure_research_v1"
CONTRACT_VERSION = "disclosure-research-public-v1"
KINDS = ("disclosure_changes", "financial_changes", "event_timelines")
VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
NOT_COLLECTED, NOT_APPLICABLE, NOT_FOUND = "NOT_COLLECTED", "NOT_APPLICABLE", "NOT_FOUND"
FILINGS_PER_COMPANY = 40
CORRECTION_KINDS = (("[기재정정]", "기재정정"), ("[첨부정정]", "첨부정정"), ("[첨부추가]", "첨부추가"), ("[정정]", "정정"))
FS_LABEL = {"CFS": "연결", "OFS": "별도"}
REPORT_LABEL = {"11011": "사업보고서(연간)", "11012": "반기보고서", "11013": "1분기보고서", "11014": "3분기보고서"}


# ── 공통 ─────────────────────────────────────────────────────────────────────
def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_vocab(path=VOCAB_PATH):
    return _read_json(path)


def _iso(day8):
    s = str(day8 or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 and s[:8].isdigit() else None


def _clean_title(title):
    return " ".join(str(title or "").split())


def correction_kind(title):
    for mark, kind in CORRECTION_KINDS:
        if mark in title:
            return kind
    return "정정" if P.CORRECTION_HINT.search(title) else None


def _bare(title):
    """분류·단계 매칭용 — 정정 표식과 공백을 뺀 제목."""
    t = re.sub(r"\[[^\]]*\]", "", str(title or ""))
    return re.sub(r"\s+", "", t)


def category_of(title, categories):
    bare = _bare(title)
    for key, spec in categories.items():
        if any(term.replace(" ", "") in bare for term in spec.get("terms") or []):
            return key
    return "other"


def filing(rcept_no, title, received_on, source):
    title = _clean_title(title)
    kind = correction_kind(title)
    return {"rceptNo": str(rcept_no), "title": title, "receivedOn": received_on,
            "isCorrection": kind is not None, "correctionKind": kind,
            "url": VIEWER + str(rcept_no), "sources": [source]}


# ── 원천 읽기 ────────────────────────────────────────────────────────────────
def load_list_filings(universe, path=SEEN_PATH):
    """seen_rcept.json → {ticker: [filing]} (추적 종목만). 접수일은 접수번호 앞 8자리다."""
    try:
        seen = _read_json(path).get("seen") or {}
    except (OSError, ValueError, AttributeError):
        seen = {}
    out, span = {}, []
    for rcept_no, entry in seen.items():
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("ticker") or "")
        day = _iso(rcept_no)
        if code not in universe or not day or not entry.get("report_name"):
            continue
        out.setdefault(code, []).append(filing(rcept_no, entry.get("report_name"), day, "list"))
        span.append(day)
    meta = {"from": min(span) if span else None, "to": max(span) if span else None, "count": len(span)}
    return out, meta


def load_evidence_filings(universe, path=EVIDENCE_PATH):
    """corporate_action_evidence.json → 관련 제목만 보존된 공시(comparisonFindings)."""
    try:
        evidence = _read_json(path).get("evidence") or {}
    except (OSError, ValueError, AttributeError):
        evidence = {}
    out, span = {}, []
    for code, rec in evidence.items():
        if code not in universe or not isinstance(rec, dict):
            continue
        for row in rec.get("comparisonFindings") or []:
            day = _iso(row.get("receivedOn"))
            if not row.get("id") or not day or not row.get("title"):
                continue
            out.setdefault(code, []).append(filing(row["id"], row["title"], day, "evidence"))
            span.append(day)
    meta = {"from": min(span) if span else None, "to": max(span) if span else None, "count": len(span)}
    return out, meta


def merge_filings(*sources):
    """같은 접수번호는 한 건 — sources 를 합친다. 최신 접수일 순."""
    merged = {}
    for by_code in sources:
        for code, rows in by_code.items():
            bucket = merged.setdefault(code, {})
            for row in rows:
                cur = bucket.get(row["rceptNo"])
                if cur is None:
                    bucket[row["rceptNo"]] = dict(row, sources=list(row["sources"]))
                else:
                    for s in row["sources"]:
                        if s not in cur["sources"]:
                            cur["sources"].append(s)
    return {code: sorted(rows.values(), key=lambda r: (r["receivedOn"], r["rceptNo"]), reverse=True)
            for code, rows in merged.items()}


# ── A. 공시 변화 ─────────────────────────────────────────────────────────────
def windows(coverage_from, as_of):
    """자료가 60일 이상이면 30/30, 그 전에는 덮인 기간을 반으로(최소 7일). 창이 자료 밖이면 fullyCovered=False."""
    start = dt.date.fromisoformat(coverage_from)
    end = dt.date.fromisoformat(as_of)
    covered = (end - start).days + 1
    days = 30 if covered >= 60 else max(7, covered // 2)
    recent_from = end - dt.timedelta(days=days - 1)
    prior_to = recent_from - dt.timedelta(days=1)
    prior_from = prior_to - dt.timedelta(days=days - 1)
    return {
        "recent": {"from": recent_from.isoformat(), "to": end.isoformat(), "days": days},
        "prior": {"from": prior_from.isoformat(), "to": prior_to.isoformat(), "days": days,
                  "fullyCovered": prior_from >= start},
        "coverageFrom": coverage_from,
    }


def _count_by_category(rows, categories, lo, hi):
    out = {}
    for r in rows:
        if lo <= r["receivedOn"] <= hi:
            out[category_of(r["title"], categories)] = out.get(category_of(r["title"], categories), 0) + 1
    return out


def company_changes(rows, categories, win):
    list_rows = [r for r in rows if "list" in r["sources"]]
    rc = _count_by_category(list_rows, categories, win["recent"]["from"], win["recent"]["to"])
    pc = _count_by_category(list_rows, categories, win["prior"]["from"], win["prior"]["to"])
    n = win["recent"]["days"]
    covered = win["prior"]["fullyCovered"]
    changes = []
    for key in list(categories) + sorted(set(rc) | set(pc)):
        if key in {c["category"] for c in changes}:
            continue
        r, p = rc.get(key, 0), pc.get(key, 0)
        if r == 0 and p == 0:
            continue
        label = categories.get(key, {}).get("label", key)
        if not covered:
            if r:
                changes.append({"type": "RECENT_ONLY", "category": key, "recent": r, "prior": None,
                                "text": f"최근 {n}일에 {label} 공시 {r}건 (이전 창은 자료가 덮이지 않아 비교하지 않음)"})
            continue
        if p == 0:
            changes.append({"type": "NEW_CATEGORY", "category": key, "recent": r, "prior": 0,
                            "text": f"최근 {n}일에 {label} 공시 {r}건 — 그 이전 {n}일에는 0건"})
        elif r == 0:
            changes.append({"type": "FEWER", "category": key, "recent": 0, "prior": p,
                            "text": f"최근 {n}일에 {label} 공시 0건 — 그 이전 {n}일에는 {p}건"})
        elif r > p:
            changes.append({"type": "MORE", "category": key, "recent": r, "prior": p,
                            "text": f"{label} 공시 {r}건 — 이전 {n}일 {p}건보다 늘었다"})
        elif r < p:
            changes.append({"type": "FEWER", "category": key, "recent": r, "prior": p,
                            "text": f"{label} 공시 {r}건 — 이전 {n}일 {p}건보다 줄었다"})
        else:
            changes.append({"type": "SAME", "category": key, "recent": r, "prior": p,
                            "text": f"{label} 공시 {r}건 (이전 {n}일과 같음)"})
    corrections = sum(1 for r in list_rows if r["isCorrection"] and win["recent"]["from"] <= r["receivedOn"] <= win["recent"]["to"])
    if corrections:
        changes.append({"type": "CORRECTIONS", "category": None, "recent": corrections, "prior": None,
                        "text": f"최근 {n}일 정정 공시 {corrections}건 — 정정 전후는 원문 비교로 확인"})
    recent_count = sum(rc.values())
    prior_count = sum(pc.values()) if covered else None
    return changes, recent_count, prior_count


def build_disclosure_changes(universe, merged, list_meta, evidence_meta, vocab, as_of, generated_at):
    categories = vocab["categories"]
    coverage_from = list_meta["from"] or as_of
    win = windows(coverage_from, as_of)
    win["rule"] = vocab["windowRule"]
    companies = {}
    total = 0
    for code in sorted(merged):
        rows = merged[code]
        if not rows:
            continue
        changes, recent_count, prior_count = company_changes(rows, categories, win)
        shown = [dict(r, category=category_of(r["title"], categories)) for r in rows[:FILINGS_PER_COMPANY]]
        total += len(rows)
        companies[code] = {
            "name": universe[code]["name"] or None,
            "filingCount": len(rows),
            "latestReceivedOn": rows[0]["receivedOn"],
            "recentCount": recent_count,
            "priorCount": prior_count,
            "changes": changes,
            "filings": shown,
            "filingsTruncated": max(0, len(rows) - FILINGS_PER_COMPANY),
        }
    return {
        "schemaVersion": SCHEMA_VERSION, "contractVersion": CONTRACT_VERSION, "kind": "disclosure_changes",
        "generatedAt": generated_at, "asOf": as_of,
        "source": {"provider": "opendart", "dataset": "공시 목록(list.json) — 접수번호·보고서명·접수일·회사 고유번호",
                   "fields": ["rcept_no", "report_nm", "rcept_dt", "corp_code"], "viewer": VIEWER + "<접수번호>"},
        "windows": win,
        "coverage": {
            "trackedCompanies": len(universe), "companiesWithFilings": len(companies), "filings": total,
            "sources": {
                "list": {"label": "공시 목록(list.json) 전수 · 추적 종목", **list_meta},
                "evidence": {"label": "기업행사 증거(종목별 list.json 365일 · 관련 제목만 보존)", **evidence_meta,
                             "onlyTitlesMatching": vocab["evidenceTitleTerms"]},
            },
        },
        "limits": vocab["disclosureLimits"],
        "categories": categories,
        "companies": companies,
    }


# ── B. 재무 변화 ─────────────────────────────────────────────────────────────
def load_financial(code, fin_dir=FIN_DIR):
    path = os.path.join(fin_dir, f"{code}.json")
    if not os.path.exists(path):
        return None
    try:
        doc = _read_json(path)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("years"), dict) else None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _pct(cur, prev):
    if prev is None or prev <= 0:
        return None, "prior_zero_or_negative"
    return round((cur - prev) / prev * 100, 1), None


def company_financial(code, name, doc, accounts, years):
    periods, notes = [], []
    for y in years:
        rec = (doc.get("years") or {}).get(str(y))
        if not isinstance(rec, dict):
            periods.append({"year": str(y), "status": NOT_COLLECTED, "fsDiv": None, "fsDivLabel": None,
                            "reprtCode": None, "reportLabel": None, "collectedAt": None, "coverage": None})
            continue
        status = rec.get("status")
        fs = rec.get("fsDiv")
        periods.append({"year": str(y), "status": "OK" if status == "OK" else (status or NOT_COLLECTED),
                        "fsDiv": fs, "fsDivLabel": FS_LABEL.get(fs), "reprtCode": rec.get("reprtCode"),
                        "reportLabel": REPORT_LABEL.get(str(rec.get("reprtCode"))), "collectedAt": rec.get("collectedAt"),
                        "coverage": rec.get("coverage")})
        if status == "NO_DATA":
            notes.append(f"{y}: DART 에 해당 연도 사업보고서 자료가 없다고 응답(NO_DATA) — 값을 만들지 않는다")
    ok_years = [p for p in periods if p["status"] == "OK"]
    if not ok_years:
        return None
    fs_divs = {p["fsDiv"] for p in ok_years}
    fs_div = ok_years[-1]["fsDiv"]
    if len(fs_divs) > 1:
        notes.append("연도별 재무제표 구분(연결/별도)이 다르다 — 구분이 다른 쌍은 비교에서 뺀다: "
                     + " · ".join(f"{p['year']} {p['fsDivLabel']}" for p in ok_years))
    pairs = []
    for a, b in zip(years, years[1:]):
        pa = next(p for p in periods if p["year"] == str(a))
        pb = next(p for p in periods if p["year"] == str(b))
        if pa["status"] == "OK" and pb["status"] == "OK" and pa["fsDiv"] == pb["fsDiv"]:
            pairs.append({"from": str(a), "to": str(b)})
    rows, derived = [], {}
    for account, spec in accounts.items():
        values, missing = {}, []
        for y in years:
            rec = (doc.get("years") or {}).get(str(y))
            if not isinstance(rec, dict) or rec.get("status") != "OK":
                values[str(y)] = NOT_COLLECTED
                continue
            if account in (rec.get("notApplicable") or []):
                values[str(y)] = NOT_APPLICABLE
                continue
            v = _num((rec.get("values") or {}).get(account))
            if v is None:
                missing.append(str(y))       # 저장된 재무제표에서 이 계정을 찾지 못함 — 0 이 아니다
            else:
                values[str(y)] = v
        changes = {}
        for pair in pairs:
            cur, prev = values.get(pair["to"]), values.get(pair["from"])
            if _num(cur) is None or _num(prev) is None:
                continue
            pct, reason = _pct(cur, prev)
            changes[pair["to"]] = {"abs": cur - prev, "pct": pct, "pctReason": reason, "vs": pair["from"]}
        rows.append({"account": account, "label": spec["label"], "statement": spec["statement"], "unit": "KRW",
                     "values": values, "changes": changes, "missing": missing})
    by_acc = {r["account"]: r["values"] for r in rows}
    for p in ok_years:
        y = p["year"]
        rev, op = _num(by_acc.get("revenue", {}).get(y)), _num(by_acc.get("operatingIncome", {}).get(y))
        liab, eq = _num(by_acc.get("totalLiabilities", {}).get(y)), _num(by_acc.get("totalEquity", {}).get(y))
        derived[y] = {
            "operatingMarginPct": round(op / rev * 100, 1) if rev is not None and op is not None and rev > 0 else None,
            "debtToEquityPct": round(liab / eq * 100, 1) if liab is not None and eq is not None and eq > 0 else None,
        }
    return {"name": name or None, "fsDiv": fs_div, "fsDivLabel": FS_LABEL.get(fs_div), "periods": periods,
            "comparablePairs": pairs, "rows": rows, "derived": derived, "notes": notes, "correctionsApplied": "UNKNOWN"}


def build_financial_changes(universe, vocab, generated_at, fin_dir=FIN_DIR, today=None):
    years = sorted(target_years(today))
    accounts = vocab["financialAccounts"]
    companies, not_collected = {}, []
    for code in sorted(universe):
        doc = load_financial(code, fin_dir)
        built = company_financial(code, universe[code]["name"], doc, accounts, years) if doc else None
        if built is None:
            not_collected.append(code)
        else:
            companies[code] = built
    return {
        "schemaVersion": SCHEMA_VERSION, "contractVersion": CONTRACT_VERSION, "kind": "financial_changes",
        "generatedAt": generated_at,
        "source": {"provider": "opendart", "dataset": "단일회사 전체 재무제표(fnlttSinglAcntAll.json) — 표준 계정(account_id) 수치",
                   "reprtCode": "11011 사업보고서(연간)", "unit": "KRW", "periodType": "annual",
                   "fields": ["bsns_year", "reprt_code", "fs_div", "sj_div", "account_id", "account_nm", "thstrm_amount"]},
        "coverage": {"trackedCompanies": len(universe), "companiesCollected": len(companies),
                     "companiesWithRows": len(companies), "notCollected": len(not_collected),
                     "notCollectedNote": "아직 수집되지 않은 회사다(재무가 없다는 뜻이 아니다). 하루 40개사·150요청 상한으로 차례로 채운다."},
        "targetYears": [str(y) for y in years],
        "accounts": accounts, "derived": vocab["financialDerived"], "method": vocab["financialMethod"],
        "howToRead": vocab["financialHowToRead"],
        "companies": companies, "notCollectedTickers": not_collected,
    }


# ── C. 사건 타임라인 ─────────────────────────────────────────────────────────
def _stage_of(title, chain):
    bare = _bare(title)
    for stage in chain["stages"]:
        for pat in stage["titlePatterns"]:
            if pat.replace(" ", "") in bare:
                return stage
    return None


def company_timelines(rows, chains):
    out = []
    for key, chain in chains.items():
        items = []
        for r in sorted(rows, key=lambda r: (r["receivedOn"], r["rceptNo"])):
            stage = _stage_of(r["title"], chain)
            if stage is None:
                continue
            items.append({"stage": stage["stage"], "stageLabel": stage["label"], "rceptNo": r["rceptNo"],
                          "title": r["title"], "receivedOn": r["receivedOn"], "isCorrection": r["isCorrection"],
                          "correctionKind": r["correctionKind"], "url": r["url"], "sources": r["sources"]})
        if not items:
            continue
        seen = []
        for s in chain["stages"]:
            if any(i["stage"] == s["stage"] for i in items) and s["stage"] not in seen:
                seen.append(s["stage"])
        not_found = [{"stage": s["stage"], "stageLabel": s["label"], "state": NOT_FOUND,
                      "meaning": "후속 공시를 찾지 못함 — 미실행이 아니다"}
                     for s in chain["stages"] if s["stage"] not in seen]
        out.append({"chain": key, "label": chain["label"], "items": items, "stagesSeen": seen,
                    "stagesNotFound": not_found, "latestStage": items[-1]["stage"],
                    "latestReceivedOn": items[-1]["receivedOn"], "note": chain["note"]})
    return out


def build_event_timelines(universe, merged, list_meta, evidence_meta, vocab, generated_at):
    chains = vocab["chains"]
    companies = {}
    for code in sorted(merged):
        tl = company_timelines(merged[code], chains)
        if tl:
            companies[code] = {"name": universe[code]["name"] or None, "timelines": tl}
    return {
        "schemaVersion": SCHEMA_VERSION, "contractVersion": CONTRACT_VERSION, "kind": "event_timelines",
        "generatedAt": generated_at,
        "source": {"provider": "opendart", "dataset": "공시 목록(list.json) 제목·접수번호·접수일", "viewer": VIEWER + "<접수번호>"},
        "stageVocabulary": vocab["stageVocabulary"], "chains": chains,
        "coverage": {"trackedCompanies": len(universe), "companiesWithTimelines": len(companies),
                     "sources": {"list": {"label": "공시 목록(list.json) 전수 · 추적 종목", **list_meta},
                                 "evidence": {"label": "기업행사 증거(종목별 list.json 365일 · 관련 제목만 보존)", **evidence_meta,
                                              "onlyTitlesMatching": vocab["evidenceTitleTerms"]}}},
        "limits": vocab["timelineLimits"],
        "companies": companies,
    }


# ── 계약·쓰기 ────────────────────────────────────────────────────────────────
def _dump(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n").encode("utf-8")


def contract(universe, files, vocab, as_of, generated_at):
    return {
        "schemaVersion": SCHEMA_VERSION, "contractVersion": CONTRACT_VERSION,
        "generatedAt": generated_at, "asOf": as_of,
        "producer": "build_disclosure_research.py (gaeo-analyst-team · corporate-action-evidence.yml · LLM 0 · 네트워크 0)",
        "provider": {"id": "opendart", "gates": "config/source_compliance.json providers.opendart.gates (derivedPublication/commercialUse 조건부 · 조건은 같은 파일 verdictChangeNote)"},
        "files": files,
        "publicFieldPolicy": "공시 사실만 — 시세·점수·판단·수급·컨센서스·개인 자료는 키 자체가 없다(test_disclosure_research.PublicFieldPolicy 가 고정)",
        "notIncluded": vocab["notIncluded"],
        "companyNames": {code: (meta["name"] or code) for code, meta in sorted(universe.items())},
    }


def build_all(universe=None, vocab=None, as_of=None, now=None, fin_dir=FIN_DIR, seen_path=SEEN_PATH, evidence_path=EVIDENCE_PATH):
    universe = universe if universe is not None else P.load_universe()
    vocab = vocab or load_vocab()
    now = now or dt.datetime.now(dt.timezone.utc)
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    as_of = as_of or (now + dt.timedelta(hours=9)).date().isoformat()
    list_rows, list_meta = load_list_filings(universe, seen_path)
    ev_rows, ev_meta = load_evidence_filings(universe, evidence_path)
    merged = merge_filings(list_rows, ev_rows)
    docs = {
        "disclosure_changes": build_disclosure_changes(universe, merged, list_meta, ev_meta, vocab, as_of, generated_at),
        "financial_changes": build_financial_changes(universe, vocab, generated_at, fin_dir, today=as_of),
        "event_timelines": build_event_timelines(universe, merged, list_meta, ev_meta, vocab, generated_at),
    }
    files = []
    blobs = {}
    for kind in KINDS:
        blob = _dump(docs[kind])
        sha = hashlib.sha256(blob).hexdigest()
        blobs[kind] = blob
        files.append({"file": f"disclosure_research/{kind}.json", "kind": kind, "sha256": sha, "bytes": len(blob),
                      "generatedAt": generated_at, "companies": len(docs[kind]["companies"]),
                      "recordId": f"{CONTRACT_VERSION}:{kind}:{sha[:16]}"})
    docs["contract"] = contract(universe, files, vocab, as_of, generated_at)
    blobs["contract"] = _dump(docs["contract"])
    return docs, blobs


def write_all(blobs, out_dir=OUT_DIR):
    os.makedirs(out_dir, exist_ok=True)
    for kind, blob in blobs.items():
        path = os.path.join(out_dir, f"{kind}.json")
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, path)


def main():
    docs, blobs = build_all()
    write_all(blobs)
    c = docs["contract"]
    for f in c["files"]:
        print(f"[disclosure_research] {f['kind']}: {f['companies']}사 · {f['bytes']:,}B · {f['recordId']}")
    print(f"[disclosure_research] asOf {c['asOf']} · generatedAt {c['generatedAt']} · 추적 {len(c['companyNames'])}사")
    return 0


if __name__ == "__main__":
    sys.exit(main())
