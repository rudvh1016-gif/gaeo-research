#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenDART 수집 파이프라인 테스트 (네트워크 없이 동작).

성능이 아니라 규칙 준수를 검사한다.
특히 "500종목을 반복 호출하지 않는가", "키가 새지 않는가",
"없는 값을 0으로 만들지 않는가"를 본다.
"""
import io
import json
import os
import tempfile
import unittest
import zipfile

import dart_client as C
import dart_pipeline as P


UNIVERSE = {"005930": {"name": "삼성전자", "sector": "반도체"},
            "000660": {"name": "SK하이닉스", "sector": "반도체"},
            "999999": {"name": "없는회사", "sector": "기타"}}

DART_ROWS = [
    {"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930"},
    {"corp_code": "00164779", "corp_name": "에스케이하이닉스", "stock_code": "000660"},
    {"corp_code": "00999001", "corp_name": "삼성전자서비스", "stock_code": ""},
]


class SecretHygiene(unittest.TestCase):
    def test_redact_removes_known_key(self):
        s = C.redact("error at https://x/api?crtfc_key=ABC123&page=1", "ABC123")
        self.assertNotIn("ABC123", s)

    def test_redact_without_knowing_key(self):
        s = C.redact("https://x/api?crtfc_key=SOMETHINGSECRET&page_no=1")
        self.assertNotIn("SOMETHINGSECRET", s)
        self.assertIn("crtfc_key=***REDACTED***", s)
        self.assertIn("page_no=1", s, "다른 파라미터까지 지우면 안 된다")

    def test_key_only_from_env(self):
        src = open(C.__file__, encoding="utf-8").read()
        # 소스에 키처럼 보이는 40자 hex 리터럴이 박혀 있으면 안 된다
        import re
        self.assertFalse(re.search(r"['\"][0-9a-f]{40}['\"]", src),
                         "소스코드에 API Key로 보이는 값이 있다")
        self.assertIn('os.environ.get(KEY_ENV)', src)

    def test_missing_key_is_graceful(self):
        client = C.DartClient(api_key=None)
        os.environ.pop(C.KEY_ENV, None)
        client._key = None
        res = client.call("list.json", {})
        self.assertEqual(res["status"], C.DART_KEY_MISSING)
        self.assertIsNone(res["data"])


class CorpMapping(unittest.TestCase):
    def test_exact_stock_code_only(self):
        cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        self.assertEqual(cmap["mapped"]["005930"]["corp_code"], "00126380")
        self.assertEqual(cmap["mapped"]["000660"]["corp_code"], "00164779")

    def test_similar_name_is_not_matched(self):
        """'삼성전자서비스'가 이름이 비슷하다고 삼성전자에 붙으면 안 된다."""
        cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        codes = {v["corp_code"] for v in cmap["mapped"].values()}
        self.assertNotIn("00999001", codes)

    def test_unmapped_is_unknown_mapping(self):
        cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        self.assertNotIn("999999", cmap["mapped"])
        unknown = {u["ticker"]: u for u in cmap["unknown"]}
        self.assertEqual(unknown["999999"]["status"], P.UNKNOWN_MAPPING)

    def test_ambiguous_is_not_guessed(self):
        rows = DART_ROWS + [{"corp_code": "00111111", "corp_name": "삼성전자(구)",
                             "stock_code": "005930"}]
        cmap = P.build_corp_map(rows, UNIVERSE)
        self.assertNotIn("005930", cmap["mapped"], "후보가 둘이면 고르면 안 된다")
        amb = [u for u in cmap["unknown"] if u["ticker"] == "005930"][0]
        self.assertEqual(amb["status"], P.UNKNOWN_MAPPING)
        self.assertEqual(len(amb["candidates"]), 2)

    def test_map_records_required_fields(self):
        cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        e = cmap["mapped"]["005930"]
        for k in ("corp_code", "stock_code", "ticker", "company_name"):
            self.assertTrue(e.get(k), f"{k} 누락")

    def test_parse_corp_code_zip(self):
        xml = ("<result>" + "".join(
            f"<list><corp_code>{r['corp_code']}</corp_code>"
            f"<corp_name>{r['corp_name']}</corp_name>"
            f"<stock_code>{r['stock_code']}</stock_code></list>" for r in DART_ROWS)
            + "</result>")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("CORPCODE.xml", xml)
        parsed = P.parse_corp_code_zip(buf.getvalue())
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["stock_code"], "005930")


class FilingNormalization(unittest.TestCase):
    def setUp(self):
        self.cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        self.entry = self.cmap["mapped"]["005930"]

    def test_required_raw_fields(self):
        ev = P.normalize_filing(
            {"corp_code": "00126380", "report_nm": "현금·현물배당 결정",
             "rcept_no": "20260815000001", "corp_cls": "Y", "rcept_dt": "20260815"},
            self.entry, "2026-08-15T14:20:00+00:00")
        for k in ("source", "corp_code", "stock_code", "ticker", "rcept_no",
                  "report_name", "corp_cls", "rcept_dt", "detected_at", "fetched_at",
                  "is_correction", "processing_status", "raw_source_reference"):
            self.assertIn(k, ev, f"{k} 누락")

    def test_rcept_dt_not_treated_as_time(self):
        ev = P.normalize_filing({"rcept_no": "1", "rcept_dt": "20260815", "report_nm": "x"},
                                self.entry, "2026-08-15T14:20:00+00:00")
        self.assertEqual(ev["rcept_dt_note"], "OFFICIAL_RECEIPT_DATE_ONLY_NO_TIME")
        self.assertEqual(ev["rcept_dt"], "20260815")
        self.assertNotIn(":", ev["rcept_dt"])

    def test_detected_at_is_the_pit_clock(self):
        det = "2026-08-15T14:20:00+00:00"
        ev = P.normalize_filing({"rcept_no": "1", "report_nm": "x"}, self.entry, det)
        self.assertEqual(ev["detected_at"], det)

    def test_correction_detected(self):
        ev = P.normalize_filing({"rcept_no": "2", "report_nm": "[기재정정]사업보고서"},
                                self.entry, "T")
        self.assertTrue(ev["is_correction"])
        plain = P.normalize_filing({"rcept_no": "3", "report_nm": "사업보고서"},
                                   self.entry, "T")
        self.assertFalse(plain["is_correction"])

    def test_unmapped_filing_marked(self):
        ev = P.normalize_filing({"rcept_no": "4", "report_nm": "x"}, None, "T")
        self.assertEqual(ev["ticker"], P.UNKNOWN_MAPPING)
        self.assertEqual(ev["stock_code"], P.NOT_AVAILABLE)

    def test_source_mode_separates_backfill(self):
        live = P.normalize_filing({"rcept_no": "5", "report_nm": "x"}, self.entry, "T")
        back = P.normalize_filing({"rcept_no": "6", "report_nm": "x"}, self.entry, "T",
                                  source_mode=P.HISTORICAL_DART_BACKFILL)
        self.assertEqual(live["sourceMode"], P.LIVE_DART_PIT)
        self.assertEqual(back["sourceMode"], P.HISTORICAL_DART_BACKFILL)
        self.assertNotEqual(live["sourceMode"], back["sourceMode"])


class Deduplication(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gaeo-dart-")
        self.path = os.path.join(self.tmp, "seen.json")

    def test_rcept_no_dedup(self):
        """⚠️ PENDING만으로는 건너뛰지 않는다. 저장 확인(ACK) 후에만 건너뛴다."""
        reg = P.SeenRegistry(self.path)
        self.assertTrue(reg.is_new("20260815000001"))
        reg.mark_pending("20260815000001", {"ticker": "005930", "report_name": "사업보고서"})
        self.assertTrue(reg.is_new("20260815000001"), "저장 전인데 건너뛰면 유실된다")
        reg.acknowledge("20260815000001")
        self.assertFalse(reg.is_new("20260815000001"))

    def test_dedup_persists(self):
        reg = P.SeenRegistry(self.path)
        reg.mark_pending("20260815000001", {"ticker": "005930", "report_name": "x"})
        reg.acknowledge("20260815000001")
        reg.save()
        self.assertFalse(P.SeenRegistry(self.path).is_new("20260815000001"))

    def test_correction_is_separate_receipt(self):
        """정정공시는 새 rcept_no라 별개 Event로 들어온다."""
        reg = P.SeenRegistry(self.path)
        reg.mark_pending("20260815000001", {"ticker": "005930", "report_name": "사업보고서"})
        reg.acknowledge("20260815000001")
        self.assertTrue(reg.is_new("20260815000009"))

    def test_correction_links_to_original(self):
        reg = P.SeenRegistry(self.path)
        reg.mark_pending("20260815000001", {"ticker": "005930", "report_name": "사업보고서"})
        ev = reg.link_correction({"rcept_no": "20260815000009", "ticker": "005930",
                                  "report_name": "[기재정정]사업보고서",
                                  "is_correction": True,
                                  "corrects_rcept_no": P.NOT_AVAILABLE})
        self.assertEqual(ev["corrects_rcept_no"], "20260815000001")

    def test_ambiguous_correction_not_linked(self):
        reg = P.SeenRegistry(self.path)
        reg.mark_pending("A1", {"ticker": "005930", "report_name": "사업보고서"})
        reg.mark_pending("A2", {"ticker": "005930", "report_name": "사업보고서(정정전)"})
        ev = reg.link_correction({"rcept_no": "A9", "ticker": "005930",
                                  "report_name": "[기재정정]사업보고서",
                                  "is_correction": True,
                                  "corrects_rcept_no": P.NOT_AVAILABLE})
        self.assertEqual(ev["corrects_rcept_no"], P.NOT_AVAILABLE,
                         "애매하면 임의로 연결하지 않는다")
        self.assertEqual(ev["correction_link_basis"], "AMBIGUOUS_NOT_LINKED")


class PointInTimeEvent(unittest.TestCase):
    def test_event_invisible_before_detection(self):
        ev = {"detected_at": "2026-08-15T14:20:00+00:00"}
        self.assertFalse(P.event_visible_at(ev, "2026-08-15T10:00:00+00:00"))

    def test_event_visible_after_detection(self):
        ev = {"detected_at": "2026-08-15T14:20:00+00:00"}
        self.assertTrue(P.event_visible_at(ev, "2026-08-15T15:00:00+00:00"))

    def test_boundary_is_inclusive(self):
        t = "2026-08-15T14:20:00+00:00"
        self.assertTrue(P.event_visible_at({"detected_at": t}, t))

    def test_filter_for_prediction(self):
        evs = [{"detected_at": "2026-08-15T09:00:00+00:00", "rcept_no": "A"},
               {"detected_at": "2026-08-15T14:20:00+00:00", "rcept_no": "B"}]
        got = P.events_for_prediction(evs, "2026-08-15T10:00:00+00:00")
        self.assertEqual([e["rcept_no"] for e in got], ["A"])


class Financials(unittest.TestCase):
    def test_missing_is_not_zero(self):
        out = P.extract_financials({"list": [
            {"account_nm": "매출액", "thstrm_amount": "1,000"}]})
        self.assertEqual(out["values"]["revenue"], 1000)
        self.assertEqual(out["values"]["operatingIncome"], P.NOT_AVAILABLE)
        self.assertNotEqual(out["values"]["operatingIncome"], 0)

    def test_empty_payload_all_not_available(self):
        out = P.extract_financials({})
        self.assertTrue(all(v == P.NOT_AVAILABLE for v in out["values"].values()))
        self.assertEqual(out["coverage"], 0.0)

    def test_unparseable_amount_is_not_available(self):
        out = P.extract_financials({"list": [
            {"account_nm": "매출액", "thstrm_amount": "-"}]})
        self.assertEqual(out["values"]["revenue"], P.NOT_AVAILABLE)

    def test_targets_cover_diana_gaps(self):
        """DIANA가 지금 못 쓰는 축을 DART로 채울 수 있는지 대응이 있는가."""
        wanted = {"GrossProfitability", "OperatingProfitability", "AssetGrowth",
                  "Investment", "CashFlowQuality", "Accruals", "Leverage"}
        covered = set()
        for spec in P.FINANCIAL_TARGETS.values():
            covered |= set(spec["for"])
        self.assertTrue(wanted <= covered, f"대응 없는 축: {wanted - covered}")

    def test_operating_profitability_inputs_are_collected(self):
        """FF5 영업수익성의 분자에 필요한 판관비·이자비용을 실제로 뽑는가.

        (docs/gaeo_diana_v2_feature_registry.md 10절 2번 — 이 둘이 없어서
         operatingProfitability가 NOT_READY로 막혀 있었다.)
        ⚠️ 수집만 늘린 것이다. 이 값으로 점수를 만들지 않는다.
        """
        out = P.extract_financials({"list": [
            {"sj_div": "IS", "account_id": "dart_SellingGeneralAdministrativeExpenses",
             "account_nm": "판매비와관리비", "thstrm_amount": "1,234"},
            {"sj_div": "IS", "account_id": "ifrs-full_InterestExpense",
             "account_nm": "이자비용", "thstrm_amount": "56"}]})
        self.assertEqual(out["values"]["sgaExpenses"], 1234)
        self.assertEqual(out["values"]["interestExpense"], 56)
        # 회사마다 계정명이 다르므로 이름으로도 잡혀야 한다(account_id가 없는 응답).
        by_name = P.extract_financials({"list": [
            {"sj_div": "IS", "account_nm": "판매비및관리비", "thstrm_amount": "77"}]})
        self.assertEqual(by_name["values"]["sgaExpenses"], 77)
        # 없으면 0이 아니라 NOT_AVAILABLE로 남아야 한다(지어내지 않는다).
        empty = P.extract_financials({})
        self.assertEqual(empty["values"]["sgaExpenses"], P.NOT_AVAILABLE)
        self.assertEqual(empty["values"]["interestExpense"], P.NOT_AVAILABLE)

    def test_pit_record_separates_period_and_visibility(self):
        rec = P.financial_pit_record("00126380", "005930", 2026, P.REPRT_CODES["H1"],
                                     P.extract_financials({}),
                                     disclosed_at="2026-08-14",
                                     detected_at="2026-08-15T09:00:00+00:00")
        self.assertEqual(rec["accountingPeriod"]["year"], 2026)
        self.assertEqual(rec["usableFrom"], "2026-08-15T09:00:00+00:00")
        self.assertEqual(rec["usableFromBasis"], "GAEO_DETECTED_AT")
        self.assertNotEqual(rec["usableFrom"], rec["accountingPeriod"])

    def test_no_consensus_no_surprise(self):
        rec = P.financial_pit_record("c", "t", 2026, "11012",
                                     P.extract_financials({"list": [
                                         {"account_nm": "매출액", "thstrm_amount": "100"}]}),
                                     None, "T")
        self.assertEqual(rec["consensus"], "CONSENSUS_DATA_UNAVAILABLE")
        self.assertEqual(rec["surprise"], "NOT_COMPUTABLE_WITHOUT_CONSENSUS")

    def test_unknown_disclosure_time_not_invented(self):
        rec = P.financial_pit_record("c", "t", 2026, "11012",
                                     P.extract_financials({}), None, "T")
        self.assertEqual(rec["disclosedAt"], P.NOT_AVAILABLE)


class EventStates(unittest.TestCase):
    def test_no_event_is_not_no_news(self):
        state, _r = P.coverage_state([], [], has_key=True)
        self.assertEqual(state, P.NO_OFFICIAL_EVENT_DETECTED)
        self.assertIn("뉴스 없음", P.COVERAGE_NOTE)

    def test_missing_key_is_incomplete_not_empty(self):
        state, reasons = P.coverage_state([], [], has_key=False)
        self.assertEqual(state, P.EVENT_COVERAGE_INCOMPLETE)
        self.assertIn(P.NO_API_KEY, reasons)

    def test_errors_become_data_error(self):
        state, _r = P.coverage_state([], [{"e": 1}], has_key=True)
        self.assertEqual(state, P.EVENT_DATA_ERROR)

    def test_detected_state(self):
        state, _r = P.coverage_state([{"rcept_no": "1"}], [], has_key=True)
        self.assertEqual(state, P.EVENT_DETECTED)

    def test_no_score_is_produced(self):
        """공시를 발견했다고 BUY/SELL 점수를 만들지 않는다."""
        src = open(P.__file__, encoding="utf-8").read()
        for banned in ("def event_score", "buy_score", "sell_score", "eventScore"):
            self.assertNotIn(banned, src)


class NoPerStockPolling(unittest.TestCase):
    """500종목 반복 호출 구조가 생기지 않았는지 (요구 4·16번)."""

    class FakeClient:
        has_key = True

        def __init__(self, pages):
            self.pages = pages
            self.calls = []
            self.stats = {"requests_per_run": 0, "detail_requests": 0, "api_errors": 0}

        def list_filings(self, **kw):
            self.calls.append(kw)
            self.stats["requests_per_run"] += 1
            page = kw.get("page_no", 1)
            data = self.pages.get(page)
            if data is None:
                return {"status": C.OK, "data": {"list": [], "total_page": len(self.pages)},
                        "error": None}
            return {"status": C.OK, "data": data, "error": None}

        def efficiency_report(self, extra=None):
            out = dict(self.stats); out.update(extra or {}); return out

    def _run(self, pages, seen_path):
        cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        client = self.FakeClient(pages)
        res = P.collect_new_filings(client, cmap, seen_path=seen_path)
        return client, res

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gaeo-dart2-")
        self.seen = os.path.join(self.tmp, "seen.json")

    def test_calls_scale_with_pages_not_stocks(self):
        rows = [{"corp_code": "00126380", "rcept_no": f"2026081500{i:04d}",
                 "report_nm": "주요사항보고서", "corp_cls": "Y", "rcept_dt": "20260815"}
                for i in range(100)]
        pages = {1: {"list": rows, "total_page": 1}}
        client, res = self._run(pages, self.seen)
        self.assertEqual(len(client.calls), 1, "목록 API는 페이지 수만큼만 부른다")
        self.assertLess(client.stats["requests_per_run"], 10)
        self.assertEqual(res["stats"]["matched_gaeo_filings"], 100)

    def test_no_corp_code_filter_in_list_call(self):
        """종목별로 corp_code를 넣어 부르면 500번 호출 구조가 된다."""
        pages = {1: {"list": [], "total_page": 1}}
        client, _ = self._run(pages, self.seen)
        for call in client.calls:
            self.assertNotIn("corp_code", call)

    def test_out_of_universe_filings_are_dropped(self):
        pages = {1: {"list": [
            {"corp_code": "00126380", "rcept_no": "A", "report_nm": "x", "rcept_dt": "20260815"},
            {"corp_code": "00777777", "rcept_no": "B", "report_nm": "x", "rcept_dt": "20260815"},
        ], "total_page": 1}}
        _client, res = self._run(pages, self.seen)
        self.assertEqual(res["stats"]["matched_gaeo_filings"], 1)
        self.assertEqual(res["stats"]["unmatched_filings"], 1)
        self.assertEqual([e["rcept_no"] for e in res["events"]], ["A"])

    def test_second_run_skips_duplicates(self):
        """⚠️ 저장 확인(ACK) 뒤에만 건너뛴다. ACK 전이면 반드시 재시도한다."""
        pages = {1: {"list": [
            {"corp_code": "00126380", "rcept_no": "A", "report_nm": "x", "rcept_dt": "20260815"}],
            "total_page": 1}}
        _c1, res1 = self._run(pages, self.seen)
        _c2, res2 = self._run(pages, self.seen)
        self.assertEqual([e["rcept_no"] for e in res2["events"]], ["A"],
                         "ACK 전인데 건너뛰면 유실된다")
        res1["registry"].acknowledge_many(["A"])
        res1["registry"].save()
        _c3, res3 = self._run(pages, self.seen)
        self.assertEqual(res3["stats"]["duplicate_skipped"], 1)
        self.assertEqual(res3["events"], [])

    def test_efficiency_metrics_present(self):
        pages = {1: {"list": [], "total_page": 1}}
        client, res = self._run(pages, self.seen)
        rep = client.efficiency_report(res["stats"])
        for k in ("requests_per_run", "new_filings_detected", "matched_gaeo_filings",
                  "detail_requests", "duplicate_skipped", "api_errors"):
            self.assertIn(k, rep, f"{k} 계측 누락")


if __name__ == "__main__":
    unittest.main(verbosity=1)
