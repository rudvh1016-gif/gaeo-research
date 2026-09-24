#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenDART 수집 파이프라인 — Mapping · 신규공시 · 재무 · Point-in-Time.

⚠️⚠️ 이 파이프라인이 만든 어떤 값도 Legacy나 research_v1.0 / research_v1.1의
      판단점수에 들어가지 않는다. 지금은 '오늘부터 쌓아두는' 수집 전용이다.
      DART가 실제 Feature로 쓰이는 최초 버전은 research_v2.0이다.
      (데이터 수집 시작일과 모델 사용 시작일이 다른 것은 정상이다.)

계층 분리 (요구 35번)
    dart_raw                DART가 준 원본 그대로
    dart_normalized         우리 스키마로 정규화한 Event
    research_event_features (research_v2.0에서 생성. 지금은 만들지 않는다)
    research_shadow         Research Prediction (별도 파일)

핵심 규칙
- 유니버스 종목을 각각 호출하지 않는다. 신규공시 목록 → 유니버스 매칭 → 필요 시 상세.
- rcept_no로 중복을 막는다. 이미 처리한 접수번호는 새 Event로 만들지 않는다.
- rcept_dt는 '접수일자'다. 시:분:초로 해석하지 않는다.
  실시간에서 가장 중요한 시각은 detected_at(우리가 처음 발견한 시각)이다.
- 이름이 비슷하다는 이유로 임의 매칭하지 않는다. 실패는 UNKNOWN_MAPPING.
- 없는 값을 0으로 만들지 않는다. NOT_AVAILABLE로 남긴다.
"""
import datetime
import io
import json
import os
import re
import zipfile

import dart_client
import dart_time

HERE = os.path.dirname(os.path.abspath(__file__))
DART_ROOT = os.path.join(HERE, "research_archive", "dart")
MAP_PATH = os.path.join(DART_ROOT, "corp_map.json")

# Event 상태 (요구 10번) — 발견했다고 점수를 만들지 않는다
EVENT_DETECTED = "EVENT_DETECTED"
NO_OFFICIAL_EVENT_DETECTED = "NO_OFFICIAL_EVENT_DETECTED"
EVENT_COVERAGE_INCOMPLETE = "EVENT_COVERAGE_INCOMPLETE"
EVENT_DATA_ERROR = "EVENT_DATA_ERROR"

# 목록 페이지 안전 상한. 하루 공시 전체를 훑기에 충분하되(페이지당 100건 → 3,000건),
# 사고로 무한히 돌지 않게 막는다. 이 한도에 걸리면 coverage_complete=False가 된다.
DEFAULT_MAX_PAGES = 30

# Coverage가 불완전한 사유
PAGE_LIMIT_REACHED = "PAGE_LIMIT_REACHED"
BUDGET_LIMIT_REACHED = "BUDGET_LIMIT_REACHED"
API_ERROR = "API_ERROR"
NO_API_KEY = "NO_API_KEY"

UNKNOWN_MAPPING = "UNKNOWN_MAPPING"
NOT_AVAILABLE = "NOT_AVAILABLE"

# 과거 Backfill과 실시간 PIT를 절대 섞지 않는다 (요구 9번)
LIVE_DART_PIT = "LIVE_DART_PIT"
HISTORICAL_DART_BACKFILL = "HISTORICAL_DART_BACKFILL"


def _now_iso():
    """timezone-aware UTC ISO. naive 시각을 만들지 않는다."""
    return dart_time.iso_now()


def load_universe():
    """tickers.js = GAEO 유니버스(단일 소스).

    ⚠️ 종목 수를 코드에 고정하지 않는다. Coverage가 늘어나면 그대로 따라간다.
    """
    path = os.path.join(HERE, "tickers.js")
    txt = open(path, encoding="utf-8").read()
    txt = re.sub(r"^\s*//.*$", "", txt, flags=re.M)
    m = re.search(r"const\s+TICKERS\s*=\s*(\[.*?\])\s*;", txt, re.S)
    if not m:
        return {}
    rows = json.loads(m.group(1))
    return {str(r["code"]): {"name": r.get("name", ""), "sector": r.get("sector", "")}
            for r in rows if r.get("code")}


# ── 1. Mapping Table (요구 5번) ──────────────────────────────────────────────
def parse_corp_code_zip(blob):
    """corpCode.xml zip → [{corp_code, corp_name, stock_code}]."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        xml = z.read(name).decode("utf-8")
    out = []
    for chunk in re.findall(r"<list>(.*?)</list>", xml, re.S):
        def pick(tag):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", chunk, re.S)
            return (m.group(1).strip() if m else "")
        out.append({"corp_code": pick("corp_code"), "corp_name": pick("corp_name"),
                    "stock_code": pick("stock_code")})
    return out


def build_corp_map(dart_rows, universe):
    """GAEO 종목 ↔ DART 기업 매핑.

    ⚠️ stock_code(6자리 종목코드) 완전일치로만 연결한다.
       회사명이 비슷하다는 이유로 임의 매칭하지 않는다(요구 5번).
       매칭 실패는 UNKNOWN_MAPPING으로 남긴다.
    """
    by_stock = {}
    for row in dart_rows:
        sc = (row.get("stock_code") or "").strip()
        if len(sc) == 6 and sc.isdigit():
            by_stock.setdefault(sc, []).append(row)

    mapped, unknown, ambiguous = {}, [], []
    for code, meta in universe.items():
        hits = by_stock.get(code) or []
        if not hits:
            unknown.append({"ticker": code, "company_name": meta["name"],
                            "status": UNKNOWN_MAPPING,
                            "reason": "DART에 같은 종목코드가 없음"})
            continue
        if len(hits) > 1:
            # 같은 종목코드가 둘 이상이면 고르지 않는다. 사람이 확인할 일이다.
            ambiguous.append({"ticker": code, "company_name": meta["name"],
                              "status": UNKNOWN_MAPPING,
                              "reason": f"corp_code 후보 {len(hits)}개",
                              "candidates": [h["corp_code"] for h in hits]})
            continue
        hit = hits[0]
        mapped[code] = {
            "corp_code": hit["corp_code"],
            "stock_code": hit["stock_code"],
            "ticker": code,
            "company_name": meta["name"],          # GAEO 표기
            "dart_corp_name": hit["corp_name"],    # DART 표기(다를 수 있다)
            "sector": meta["sector"],
            "mapped_by": "STOCK_CODE_EXACT",
        }
    return {
        "schemaVersion": "dart_corp_map_v1",
        "builtAt": _now_iso(),
        "universeSize": len(universe),
        "mappedCount": len(mapped),
        "unknownCount": len(unknown) + len(ambiguous),
        "mapped": mapped,
        "unknown": unknown + ambiguous,
    }


def load_corp_map():
    if not os.path.exists(MAP_PATH):
        return None
    try:
        return json.load(open(MAP_PATH, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_corp_map(cmap):
    os.makedirs(os.path.dirname(MAP_PATH), exist_ok=True)
    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(cmap, f, ensure_ascii=False, indent=1, sort_keys=True)


# ── 2. 신규공시 정규화 + 중복 제거 (요구 6·7번) ──────────────────────────────
CORRECTION_HINT = re.compile(r"\[기재정정\]|\[첨부정정\]|\[정정\]|정정신고")


def normalize_filing(row, corp_map_entry, detected_at, source_mode=LIVE_DART_PIT):
    """DART list.json 한 건 → 우리 스키마 Event Raw Record.

    ⚠️ rcept_dt는 접수'일자'다. 시:분:초로 해석하지 않는다.
       실시간에서 의미 있는 시각은 detected_at이다.
    """
    rcept_no = str(row.get("rcept_no") or "").strip()
    report_name = (row.get("report_nm") or "").strip()
    return {
        "source": "OPENDART",
        "sourceMode": source_mode,          # LIVE_DART_PIT / HISTORICAL_DART_BACKFILL
        "corp_code": row.get("corp_code") or NOT_AVAILABLE,
        "stock_code": (corp_map_entry or {}).get("stock_code") or NOT_AVAILABLE,
        "ticker": (corp_map_entry or {}).get("ticker") or UNKNOWN_MAPPING,
        "rcept_no": rcept_no,
        "report_name": report_name,
        "corp_cls": row.get("corp_cls") or NOT_AVAILABLE,
        # 접수일자. 시각 정보가 아니다.
        "rcept_dt": row.get("rcept_dt") or NOT_AVAILABLE,
        "rcept_dt_note": "OFFICIAL_RECEIPT_DATE_ONLY_NO_TIME",
        # GAEO가 이 공시를 처음 발견한 시각. Point-in-Time의 기준이다.
        "detected_at": detected_at,
        "fetched_at": _now_iso(),
        "is_correction": bool(CORRECTION_HINT.search(report_name)),
        # 정정 원본과의 관계. DART 목록만으로는 원본 접수번호를 알 수 없다.
        "corrects_rcept_no": NOT_AVAILABLE,
        "processing_status": EVENT_DETECTED,
        "raw_source_reference": (f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
                                 if rcept_no else NOT_AVAILABLE),
    }


class SeenRegistry:
    """rcept_no 기반 중복 제거 + Durable Write 상태 관리 (요구 5·6번).

    ⚠️ 순서가 중요하다. "봤다"고 먼저 표시하고 나중에 저장하면,
       저장이 실패한 순간 그 공시는 영원히 사라진다. 다음 실행에서
       "이미 본 공시"로 건너뛰기 때문이다.

    그래서 상태를 셋으로 나눈다.

        PENDING       발견해서 정규화했지만 아직 저장 안 됨
        STORED        Raw Archive에 실제로 기록됨(디스크 flush 확인)
        ACKNOWLEDGED  저장 확인 후 '처리 완료'로 확정. 이때부터 건너뛴다

    건너뛰기 판정은 **ACKNOWLEDGED만** 본다. PENDING/STORED에서 죽으면
    다음 실행에서 같은 rcept_no를 다시 수집한다(at-least-once).
    중복 저장은 Archive가 rcept_no 키로 덮어써서 흡수한다.
    """

    PENDING = "PENDING"
    STORED = "STORED"
    ACKNOWLEDGED = "ACKNOWLEDGED"

    def __init__(self, path):
        self.path = path
        self.seen = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.seen = json.load(f).get("seen", {})
            except (OSError, json.JSONDecodeError):
                self.seen = {}

    def is_new(self, rcept_no):
        """아직 '처리 완료'로 확정되지 않은 접수번호인가.

        PENDING/STORED에서 중단된 건은 새 것으로 취급해 반드시 재시도한다.
        """
        if not rcept_no:
            return False
        meta = self.seen.get(rcept_no)
        if meta is None:
            return True
        return meta.get("state") != self.ACKNOWLEDGED

    def mark_pending(self, rcept_no, meta):
        """발견 단계. 아직 저장 전이라 건너뛰기 대상이 아니다."""
        if rcept_no:
            entry = dict(meta or {})
            entry["state"] = self.PENDING
            entry["pendingAt"] = dart_time.iso_now()
            self.seen[rcept_no] = entry

    def mark_stored(self, rcept_no):
        if rcept_no in self.seen:
            self.seen[rcept_no]["state"] = self.STORED
            self.seen[rcept_no]["storedAt"] = dart_time.iso_now()

    def acknowledge(self, rcept_no):
        """Raw Archive 저장이 실제로 확인된 뒤에만 부른다."""
        if rcept_no in self.seen:
            self.seen[rcept_no]["state"] = self.ACKNOWLEDGED
            self.seen[rcept_no]["acknowledgedAt"] = dart_time.iso_now()

    def acknowledge_many(self, rcept_nos):
        for no in rcept_nos:
            self.acknowledge(no)

    def pending_count(self):
        return sum(1 for m in self.seen.values()
                   if m.get("state") != self.ACKNOWLEDGED)

    def link_correction(self, event):
        """같은 종목의 직전 공시 중 이름이 겹치는 원본을 후보로 남긴다.

        ⚠️ 확정하지 않는다. 추적 가능하게 후보만 기록하고,
           확정 근거가 없으면 NOT_AVAILABLE 그대로 둔다.
        """
        if not event.get("is_correction"):
            return event
        base = CORRECTION_HINT.sub("", event["report_name"]).strip()
        if not base:
            return event
        cands = [no for no, meta in self.seen.items()
                 if meta.get("ticker") == event.get("ticker")
                 and base and base in (meta.get("report_name") or "")
                 and no != event["rcept_no"]]
        if len(cands) == 1:
            event["corrects_rcept_no"] = cands[0]
            event["correction_link_basis"] = "SAME_TICKER_SAME_REPORT_NAME"
        elif cands:
            event["correction_candidates"] = sorted(cands)[-5:]
            event["correction_link_basis"] = "AMBIGUOUS_NOT_LINKED"
        return event

    def save(self):
        """원자적으로 쓴다. 쓰는 도중 죽어도 기존 파일이 깨지지 않게."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"schemaVersion": "dart_seen_v2", "updatedAt": dart_time.iso_now(),
                       "count": len(self.seen), "seen": self.seen},
                      f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)


# ── 3. Point-in-Time EVENT 규칙 (요구 8번) ───────────────────────────────────
def event_visible_at(event, prediction_timestamp):
    """이 공시를 그 시점 Prediction에서 써도 되는가.

    조건: event_detected_at <= prediction_timestamp

    ⚠️ 문자열 비교로 판정하지 않는다. timezone 표기가 다르면
       (+09:00 vs +00:00) 문자열 순서와 실제 시각순서가 뒤집힌다.
       aware datetime으로 parse해 UTC Instant로 비교한다.
       읽을 수 없거나 timezone이 없는 값은 사용 불가로 본다(False).
    """
    return dart_time.instant_le(event.get("detected_at"), prediction_timestamp)


def events_for_prediction(events, prediction_timestamp):
    """research_v2.0이 쓸 때를 대비한 조회 함수. 지금은 아무도 호출하지 않는다."""
    return [e for e in events if event_visible_at(e, prediction_timestamp)]


# ── 4. 재무 데이터 수집 준비 (요구 11·12번) ──────────────────────────────────
# DIANA가 지금 못 쓰는 축과, DART 계정과목으로 채울 수 있는지의 대응표.
# ⚠️ 실제로 응답에 없으면 0이 아니라 NOT_AVAILABLE로 남긴다.
# ⚠️ 실제 응답에서 배운 값으로 만들었다(2026-08-15 스모크 테스트).
#    account_nm(계정명)은 회사마다 다르다. 현대차는 "당기순이익"이 아니라
#    "연결당기순이익"이고, KB금융은 "영업활동현금흐름"이 아니라
#    "영업활동으로부터의 현금흐름"이다.
#    반면 account_id는 IFRS 표준이라 회사가 달라도 같다.
#    그래서 **account_id를 우선**으로 찾고, 없을 때만 이름으로 되찾는다.
#
#    sjDiv는 그 계정이 어느 재무제표에 있어야 하는지다. 같은 이름이 여러 표에
#    나오므로(예: 당기순이익은 IS·CIS·CF에 모두 등장) 엉뚱한 표의 값을
#    집지 않도록 제한한다.
FINANCIAL_TARGETS = {
    "revenue": {
        "ids": ["ifrs-full_Revenue"],
        "names": ["매출액", "수익(매출액)", "영업수익"],
        "sjDiv": ["IS", "CIS"],
        "for": ["GrossProfitability", "AssetTurnover"]},
    "costOfSales": {
        "ids": ["ifrs-full_CostOfSales"],
        "names": ["매출원가"],
        "sjDiv": ["IS", "CIS"],
        "for": ["GrossProfitability"]},
    "grossProfit": {
        "ids": ["ifrs-full_GrossProfit"],
        "names": ["매출총이익"],
        "sjDiv": ["IS", "CIS"],
        "for": ["GrossProfitability"]},
    "operatingIncome": {
        "ids": ["dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"],
        "names": ["영업이익", "영업이익(손실)"],
        "sjDiv": ["IS", "CIS"],
        "for": ["OperatingProfitability"]},
    "netIncome": {
        "ids": ["ifrs-full_ProfitLoss"],
        "names": ["당기순이익", "당기순이익(손실)", "연결당기순이익"],
        "sjDiv": ["IS", "CIS"],
        "for": ["Accruals", "ROE"]},
    "totalAssets": {
        "ids": ["ifrs-full_Assets"],
        "names": ["자산총계"],
        "sjDiv": ["BS"],
        "for": ["AssetGrowth", "GrossProfitability", "Leverage"]},
    "totalLiabilities": {
        "ids": ["ifrs-full_Liabilities"],
        "names": ["부채총계"],
        "sjDiv": ["BS"],
        "for": ["Leverage"]},
    "totalEquity": {
        "ids": ["ifrs-full_Equity"],
        "names": ["자본총계"],
        "sjDiv": ["BS"],
        "for": ["Leverage", "ROE"]},
    "operatingCashFlow": {
        "ids": ["ifrs-full_CashFlowsFromUsedInOperatingActivities"],
        "names": ["영업활동현금흐름", "영업활동으로인한현금흐름", "영업활동으로부터의현금흐름"],
        "sjDiv": ["CF"],
        "for": ["CashFlowQuality", "Accruals"]},
    "investingCashFlow": {
        "ids": ["ifrs-full_CashFlowsFromUsedInInvestingActivities"],
        "names": ["투자활동현금흐름", "투자활동으로인한현금흐름", "투자활동으로부터의현금흐름"],
        "sjDiv": ["CF"],
        "for": ["Investment"]},
    # 📚 2026-08-21 추가 — docs/gaeo_diana_v2_feature_registry.md 10절 2번.
    #    operatingProfitability(FF5 원공식)의 분자에 판관비·이자비용이 필요한데
    #    수집 목록에 없어서 그 축이 NOT_READY로 막혀 있었다.
    #    ⚠️ 수집만 늘린다. 점수는 만들지 않는다 — 같은 문서 "지금은 점수를
    #       만들지 않는다"와 7번(그 뒤에야 Feature 계산 시작)을 그대로 따른다.
    #    ⚠️ 계정을 못 찾으면 기존과 같이 NOT_AVAILABLE로 남는다(0으로 만들지 않는다).
    #       실제 응답에 있는지는 dart_smoke_test.py로 확인해야 확정된다.
    "sgaExpenses": {
        "ids": ["dart_SellingGeneralAdministrativeExpenses",
                "ifrs-full_SellingGeneralAndAdministrativeExpense"],
        "names": ["판매비와관리비", "판매비및관리비", "판매관리비"],
        "sjDiv": ["IS", "CIS"],
        "for": ["OperatingProfitability"]},
    "interestExpense": {
        "ids": ["ifrs-full_InterestExpense", "dart_InterestExpense"],
        "names": ["이자비용", "금융원가", "이자비용(금융원가)"],
        "sjDiv": ["IS", "CIS"],
        "for": ["OperatingProfitability"]},
    # 📚 2026-09-04 추가 — Piotroski(2000, JAR) F-Score 9개 신호 중 지금 계정이 없어
    #    아예 계산할 수 없던 세 가지(유동성·차입금·증자)를 위해 수집 목록을 늘린다.
    #    ⚠️ 2026-08-21과 같은 원칙: **수집만 늘린다. 점수는 여기서 만들지 않는다.**
    #    ⚠️ 계정을 못 찾으면 기존과 같이 NOT_AVAILABLE로 남는다(0으로 만들지 않는다).
    #       실제 응답에 있는지는 dart_smoke_test.py로 확인해야 확정된다.
    #    ⚠️ 유동자산·유동부채는 유동/비유동 구분을 하지 않는 재무제표(금융업 등)에는
    #       원래 없다. 그런 경우도 결측이 아니라 '개념 부재'로 다뤄야 한다.
    "currentAssets": {
        "ids": ["ifrs-full_CurrentAssets"],
        "names": ["유동자산"],
        "sjDiv": ["BS"],
        "for": ["Piotroski.dLiquidity"]},
    "currentLiabilities": {
        "ids": ["ifrs-full_CurrentLiabilities"],
        "names": ["유동부채"],
        "sjDiv": ["BS"],
        "for": ["Piotroski.dLiquidity"]},
    "nonCurrentLiabilities": {
        "ids": ["ifrs-full_NoncurrentLiabilities"],
        "names": ["비유동부채"],
        "sjDiv": ["BS"],
        "for": ["Piotroski.dLeverage"]},
    "issuedCapital": {
        "ids": ["ifrs-full_IssuedCapital"],
        "names": ["자본금"],
        "sjDiv": ["BS"],
        "for": ["Piotroski.equityOffer"]},
}

# 유동/비유동을 나누지 않는 재무제표에는 원래 없는 항목이다(금융업이 대표적).
# '결측'과 구분해 NOT_APPLICABLE로 다룬다.
NON_CURRENT_SPLIT_ACCOUNTS = ("currentAssets", "currentLiabilities", "nonCurrentLiabilities")

# 금융업은 매출원가·매출총이익 개념이 없고 부채의 의미도 다르다(요구 20번).
# 일반기업 공식에 억지로 넣지 않기 위한 표시.
FINANCIAL_SECTOR_SPECIAL_HANDLING_REQUIRED = "FINANCIAL_SECTOR_SPECIAL_HANDLING_REQUIRED"
NOT_APPLICABLE_FINANCIAL_SECTOR = "NOT_APPLICABLE_FINANCIAL_SECTOR"
FINANCIAL_SECTOR_HINTS = ("은행", "금융", "보험", "증권", "카드", "캐피탈", "저축은행", "지주")

REPRT_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}


def is_financial_sector(sector_name):
    """업종명으로 금융업 여부를 판정한다. 확정이 아니라 '별도 처리 필요' 표시용이다."""
    name = str(sector_name or "")
    return any(h in name for h in FINANCIAL_SECTOR_HINTS)


def extract_financials(payload, sector=None):
    """fnlttSinglAcntAll.json 응답 → 목표 항목만 뽑는다.

    ⚠️ account_id(IFRS 표준) 우선, account_nm(회사마다 다름)은 보조.
       실측: 현대차 netIncome은 이름이 "연결당기순이익"이라 이름만으로는 못 찾았고,
       KB금융 영업활동현금흐름도 "영업활동으로부터의 현금흐름"이라 못 찾았다.
       account_id는 둘 다 표준값이라 한 번에 잡힌다.

    ⚠️ 없는 항목은 NOT_AVAILABLE. 0으로 만들지 않는다.
    ⚠️ 금융업은 매출원가·매출총이익이 원래 없다. 그걸 '결측'이라고 부르지 않고
       NOT_APPLICABLE_FINANCIAL_SECTOR로 구분한다.
    """
    rows = (payload or {}).get("list") or []
    by_id, by_name = {}, {}
    any_id, any_name = {}, {}     # sj_div 없이도 찾을 수 있게 하는 보조 색인
    for r in rows:
        sj = r.get("sj_div")
        aid = (r.get("account_id") or "").strip()
        if aid:
            by_id.setdefault((aid, sj), r)
            any_id.setdefault(aid, r)
        nm = (r.get("account_nm") or "").replace(" ", "")
        if nm:
            by_name.setdefault((nm, sj), r)
            any_name.setdefault(nm, r)

    financial_sector = is_financial_sector(sector)
    out, found, missing, not_applicable = {}, [], [], []
    matched_by = {}
    for key, spec in FINANCIAL_TARGETS.items():
        hit, how = None, None
        for sj in spec["sjDiv"]:
            for aid in spec["ids"]:
                hit = by_id.get((aid, sj))
                if hit:
                    how = "account_id"
                    break
            if hit:
                break
        if hit is None:
            for sj in spec["sjDiv"]:
                for cand in spec["names"]:
                    hit = by_name.get((cand.replace(" ", ""), sj))
                    if hit:
                        how = "account_nm"
                        break
                if hit:
                    break
        if hit is None:
            # sj_div가 비어 있는 응답도 있으므로 마지막에 표 구분 없이 한 번 더 찾는다.
            for aid in spec["ids"]:
                hit = any_id.get(aid)
                if hit:
                    how = "account_id_any_sj"
                    break
        if hit is None:
            for cand in spec["names"]:
                hit = any_name.get(cand.replace(" ", ""))
                if hit:
                    how = "account_nm_any_sj"
                    break
        if hit is None:
            # 금융업에서 원래 존재하지 않는 항목은 '결측'과 구분한다.
            if financial_sector and key in ("costOfSales", "grossProfit", "revenue",
                                            *NON_CURRENT_SPLIT_ACCOUNTS):
                out[key] = NOT_APPLICABLE_FINANCIAL_SECTOR
                not_applicable.append(key)
            else:
                out[key] = NOT_AVAILABLE
                missing.append(key)
            continue
        amount = (hit.get("thstrm_amount") or "").replace(",", "").strip()
        try:
            out[key] = int(amount)
            found.append(key)
            matched_by[key] = how
        except ValueError:
            out[key] = NOT_AVAILABLE
            missing.append(key)
    # 적용 불가 항목은 분모에서 뺀다. 금융업이 억지로 낮은 점수를 받지 않게.
    applicable = len(FINANCIAL_TARGETS) - len(not_applicable)
    return {"values": out, "found": found, "missing": missing,
            "notApplicable": not_applicable, "matchedBy": matched_by,
            "sectorHandling": (FINANCIAL_SECTOR_SPECIAL_HANDLING_REQUIRED
                               if financial_sector else "STANDARD"),
            "coverage": (len(found) / applicable) if applicable else 0.0}


def financial_pit_record(corp_code, ticker, year, reprt_code, extracted,
                         disclosed_at, detected_at, source_mode=LIVE_DART_PIT):
    """재무자료의 회계기간과 '실제로 알 수 있었던 시점'을 분리해 저장한다(요구 12번).

    2026 Q2 실적이라고 2026 Q2 내내 쓸 수 있는 게 아니다.
    usableFrom 이후의 Prediction에서만 Feature로 쓸 수 있다.
    """
    return {
        "source": "OPENDART",
        "sourceMode": source_mode,
        "corp_code": corp_code,
        "ticker": ticker,
        "accountingPeriod": {"year": int(year), "reprtCode": reprt_code},
        # 시장에 공개된 시점(공시 접수). 알 수 없으면 만들어내지 않는다.
        "disclosedAt": disclosed_at or NOT_AVAILABLE,
        # GAEO가 실제로 알게 된 시점. Feature 사용 가능 시점의 기준.
        "detectedAt": detected_at,
        "usableFrom": detected_at,
        "usableFromBasis": "GAEO_DETECTED_AT",
        "values": extracted["values"],
        "missing": extracted["missing"],
        "coverage": round(extracted["coverage"], 4),
        # ⚠️ DART Actual만으로 Surprise를 만들지 않는다(요구 13번)
        "consensus": "CONSENSUS_DATA_UNAVAILABLE",
        "surprise": "NOT_COMPUTABLE_WITHOUT_CONSENSUS",
    }


# ── 5. 수집 실행 (요구 4·16번) ───────────────────────────────────────────────
def collect_new_filings(client, corp_map, bgn_de=None, end_de=None, max_pages=None,
                        seen_path=None, source_mode=LIVE_DART_PIT, budget=None):
    """신규공시 목록 → 유니버스 매칭 → 중복 제거 → 정규화.

    ⚠️ 종목별 반복호출을 하지 않는다. 목록 API를 페이지 단위로만 부른다.
       호출 수는 페이지 수에 비례하지, 종목 수(500)에 비례하지 않는다.

    ⚠️ 여기서는 seen을 ACKNOWLEDGED로 만들지 않는다. PENDING까지만 표시한다.
       실제 저장이 확인된 뒤 호출자가 acknowledge_many()를 부른다.
       (그래야 저장 실패 시 다음 실행에서 반드시 재시도된다)

    ⚠️ 페이지 한도나 예산 때문에 중간에 멈췄으면 coverageComplete=False.
       그 상태를 '공시 없음'으로 해석하면 안 된다.
    """
    today = dart_time.today_kst_compact()      # Runner timezone에 기대지 않는다
    bgn_de = bgn_de or today
    end_de = end_de or today
    page_limit = max_pages if max_pages is not None else DEFAULT_MAX_PAGES
    seen = SeenRegistry(seen_path or os.path.join(DART_ROOT, "seen_rcept.json"))
    by_corp = {v["corp_code"]: v for v in (corp_map.get("mapped") or {}).values()}

    detected_at = dart_time.iso_now()
    stats = {"new_filings_detected": 0, "matched_gaeo_filings": 0,
             "duplicate_skipped": 0, "unmatched_filings": 0,
             "pages_fetched": 0, "list_requests": 0}
    events, errors = [], []
    observed_filings = []  # This query's matched rows, including already stored receipts.
    total_pages_reported = None
    coverage_complete = True
    incomplete_reasons = []

    page = 1
    while True:
        if page > page_limit:
            coverage_complete = False
            incomplete_reasons.append(PAGE_LIMIT_REACHED)
            break
        if budget is not None and not budget.allow("list"):
            coverage_complete = False
            incomplete_reasons.append(BUDGET_LIMIT_REACHED)
            break
        res = client.list_filings(bgn_de=bgn_de, end_de=end_de,
                                  page_no=page, page_count=100)
        stats["list_requests"] += 1
        if budget is not None:
            budget.spend("list")
        if res["status"] != dart_client.OK:
            errors.append({"page": page, "status": res["status"], "error": res["error"]})
            coverage_complete = False
            incomplete_reasons.append(API_ERROR)
            break
        stats["pages_fetched"] += 1
        payload = res["data"] or {}
        rows = payload.get("list") or []
        reported = payload.get("total_page")
        if reported is not None:
            try:
                total_pages_reported = int(reported)
            except (TypeError, ValueError):
                total_pages_reported = None
        for row in rows:
            stats["new_filings_detected"] += 1
            rcept_no = str(row.get("rcept_no") or "").strip()
            entry = by_corp.get(row.get("corp_code"))
            if entry is None:
                stats["unmatched_filings"] += 1
                continue          # 우리 유니버스 밖 — 저장하지 않는다
            observed_filings.append(normalize_filing(row, entry, detected_at, source_mode))
            if not seen.is_new(rcept_no):
                stats["duplicate_skipped"] += 1
                continue
            ev = normalize_filing(row, entry, detected_at, source_mode)
            ev = seen.link_correction(ev)
            ev["processing_status"] = SeenRegistry.PENDING
            # ⚠️ PENDING까지만. 저장 확인 전에는 절대 ACKNOWLEDGED로 만들지 않는다.
            seen.mark_pending(rcept_no, {"ticker": ev["ticker"],
                                         "report_name": ev["report_name"],
                                         "detected_at": detected_at})
            events.append(ev)
            stats["matched_gaeo_filings"] += 1
        if not rows:
            break
        if total_pages_reported is not None and page >= total_pages_reported:
            break
        if total_pages_reported is None and len(rows) < 100:
            break              # 마지막 페이지로 본다
        page += 1

    # 실제로 다 훑었는지 최종 판정
    if (total_pages_reported is not None
            and stats["pages_fetched"] < total_pages_reported
            and coverage_complete):
        coverage_complete = False
        incomplete_reasons.append(PAGE_LIMIT_REACHED)

    return {"events": events, "stats": stats, "errors": errors,
            "researchObservedFilings": observed_filings,
            "registry": seen, "seenTotal": len(seen.seen),
            "pendingTotal": seen.pending_count(),
            "pagination": {
                "total_pages_reported": total_pages_reported,
                "pages_fetched": stats["pages_fetched"],
                "page_limit": page_limit,
                "coverage_complete": coverage_complete,
                "incomplete_reasons": sorted(set(incomplete_reasons)),
            }}


def coverage_state(events, errors, has_key, pagination=None):
    """요구 6·10번 상태. '공시 없음'은 '뉴스 없음'이 아니다.

    ⚠️ 페이지 한도·예산·에러로 전체를 못 훑었으면 NO_OFFICIAL_EVENT_DETECTED를
       내면 안 된다. 못 본 페이지에 우리 종목 공시가 있었을 수 있다.
    """
    if not has_key:
        return EVENT_COVERAGE_INCOMPLETE, [NO_API_KEY]
    complete = True if pagination is None else bool(pagination.get("coverage_complete"))
    reasons = list((pagination or {}).get("incomplete_reasons") or [])
    if errors:
        return EVENT_DATA_ERROR, sorted(set(reasons + [API_ERROR]))
    if not complete:
        return EVENT_COVERAGE_INCOMPLETE, sorted(set(reasons)) or [PAGE_LIMIT_REACHED]
    if events:
        return EVENT_DETECTED, []
    return NO_OFFICIAL_EVENT_DETECTED, []


COVERAGE_NOTE = ("NO_OFFICIAL_EVENT_DETECTED는 '뉴스 없음'이 아니다. "
                 "일반 언론뉴스 Coverage가 없어서 공식 공시만 본 결과다.")
