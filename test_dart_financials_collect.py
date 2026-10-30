#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연간 재무 수집 경로 계약 테스트 (2026-09-04 신설).

핵심 계약:
  - API 예산을 넘지 않는다(600종목 × 3년 = 1,800회를 한 번에 부르면 안 된다).
  - 이미 받은 (회사, 연도)는 다시 부르지 않는다.
  - 키가 없거나 매핑이 없으면 조용히 건너뛴다(빈 값을 만들지 않는다).
  - 예산이 빠듯하면 멈춘다(financial은 OPTIONAL 등급).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import collect_dart_financials as C
import dart_client
import dart_pipeline as P


def fake_payload(assets=2000, corp_code="C000001", year=2025, reprt_code="11011"):
    payload = {"status": "000", "list": [
        {"account_id": "ifrs-full_Assets", "sj_div": "BS", "thstrm_amount": str(assets)},
        {"account_id": "ifrs-full_Liabilities", "sj_div": "BS", "thstrm_amount": "800"},
        {"account_id": "ifrs-full_Equity", "sj_div": "BS", "thstrm_amount": "1200"},
        {"account_id": "ifrs-full_CurrentAssets", "sj_div": "BS", "thstrm_amount": "900"},
        {"account_id": "ifrs-full_CurrentLiabilities", "sj_div": "BS", "thstrm_amount": "300"},
        {"account_id": "ifrs-full_NoncurrentLiabilities", "sj_div": "BS", "thstrm_amount": "500"},
        {"account_id": "ifrs-full_IssuedCapital", "sj_div": "BS", "thstrm_amount": "100"},
        {"account_id": "ifrs-full_Revenue", "sj_div": "IS", "thstrm_amount": "1000"},
        {"account_id": "ifrs-full_CostOfSales", "sj_div": "IS", "thstrm_amount": "600"},
        {"account_id": "ifrs-full_GrossProfit", "sj_div": "IS", "thstrm_amount": "400"},
        {"account_id": "ifrs-full_ProfitLoss", "sj_div": "IS", "thstrm_amount": "100"},
        {"account_id": "dart_OperatingIncomeLoss", "sj_div": "IS", "thstrm_amount": "200"},
        {"account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
         "sj_div": "CF", "thstrm_amount": "150"},
        {"account_id": "ifrs-full_CashFlowsFromUsedInInvestingActivities",
         "sj_div": "CF", "thstrm_amount": "-50"},
    ]}
    for row in payload["list"]:
        row.update(corp_code=corp_code, bsns_year=str(year), reprt_code=reprt_code, currency="KRW")
    return payload


class FakeClient:
    def __init__(self, has_key=True, empty_for=()):
        self._has_key = has_key
        self.calls = []
        self.empty_for = set(empty_for)

    @property
    def has_key(self):
        return self._has_key

    def financial_statement(self, corp_code, year, reprt_code, fs_div="CFS"):
        self.calls.append((corp_code, year, fs_div))
        if (corp_code, year) in self.empty_for:
            return {"status": dart_client.OK, "noData": True,
                    "data": {"status": "013", "list": []}}
        return {"status": dart_client.OK, "data": fake_payload(corp_code=corp_code, year=year,
                                                                   reprt_code=reprt_code)}


class FakeBudget:
    def __init__(self, allow_n=999, financial_today=0):
        self.allow_n = allow_n
        self.spent = 0
        self.counts = {"financial": financial_today}

    def allow(self, kind):
        return self.spent < self.allow_n

    def spend(self, kind):
        self.spent += 1
        self.counts[kind] = self.counts.get(kind, 0) + 1


def corp_map(n=5):
    return {"mapped": {f"{i:06d}": {"corp_code": f"C{i:06d}", "company_name": f"회사{i}",
                                    "sector": "반도체"} for i in range(1, n + 1)}}


class CollectorContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = C.STORE_DIR
        C.STORE_DIR = self.tmp

    def tearDown(self):
        C.STORE_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_respects_call_ceiling(self):
        """⭐ 한 번에 유니버스를 다 받으면 예산이 터진다."""
        cl = FakeClient()
        out = C.collect(cl, corp_map(50), budget=FakeBudget(),
                        max_companies=40, max_calls=12, today="2026-09-04")
        self.assertLessEqual(out["apiCalls"], 12)
        self.assertLessEqual(len(cl.calls), 12)

    def test_does_not_refetch_stored_years(self):
        """연간 재무는 1년에 한 번만 바뀐다. 이미 받은 해를 또 부르면 예산 낭비다."""
        cl = FakeClient()
        C.collect(cl, corp_map(2), budget=FakeBudget(), max_companies=2,
                  max_calls=99, today="2026-09-04")
        first = len(cl.calls)
        self.assertGreater(first, 0)
        cl2 = FakeClient()
        out2 = C.collect(cl2, corp_map(2), budget=FakeBudget(), max_companies=2,
                         max_calls=99, today="2026-09-04")
        self.assertEqual(len(cl2.calls), 0, "이미 받은 연도를 다시 불렀다")
        self.assertEqual(out2["yearsStored"], 0)

    def test_stops_when_budget_says_no(self):
        cl = FakeClient()
        out = C.collect(cl, corp_map(10), budget=FakeBudget(allow_n=0),
                        max_companies=10, max_calls=99, today="2026-09-04")
        self.assertTrue(out["budgetStopped"])
        self.assertEqual(out["apiCalls"], 0)

    def test_skips_without_key(self):
        out = C.collect(FakeClient(has_key=False), corp_map(3), budget=FakeBudget())
        self.assertEqual(out["status"], C.SKIPPED_NO_KEY)

    def test_real_client_key_property_without_network(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(C.collect(dart_client.DartClient(), corp_map(1))["status"], C.SKIPPED_NO_KEY)
        client = dart_client.DartClient(api_key="test-only-not-a-secret")
        def respond(corp_code, year, reprt_code, fs_div="CFS"):
            return {"status": dart_client.OK, "data": fake_payload(corp_code=corp_code, year=year,
                                                                     reprt_code=reprt_code)}
        with patch.object(client, "financial_statement", side_effect=respond):
            self.assertEqual(C.collect(client, corp_map(1), budget=FakeBudget())["yearsStored"], 3)

    def test_fallback_request_cannot_exceed_call_budget(self):
        client = FakeClient(empty_for=[("C000001", 2025)])
        result = C.collect(client, corp_map(1), budget=FakeBudget(allow_n=1),
                           max_calls=1, today="2026-09-14")
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(result["budgetStopped"])
        self.assertNotIn("2025", C.load_company("000001")["years"])

    def test_skips_without_mapping(self):
        out = C.collect(FakeClient(), {"mapped": {}}, budget=FakeBudget())
        self.assertEqual(out["status"], C.SKIPPED_NO_MAPPING)

    def test_no_data_year_is_remembered(self):
        """자료가 없는 해를 매번 다시 묻지 않는다."""
        cm = corp_map(1)
        code = cm["mapped"]["000001"]["corp_code"]
        cl = FakeClient(empty_for=[(code, 2023)])
        C.collect(cl, cm, budget=FakeBudget(), max_companies=1, max_calls=99,
                  today="2026-09-04")
        doc = C.load_company("000001")
        self.assertEqual(doc["years"]["2023"]["status"], "NO_DATA")
        cl2 = FakeClient(empty_for=[(code, 2023)])
        C.collect(cl2, cm, budget=FakeBudget(), max_companies=1, max_calls=99,
                  today="2026-09-04")
        self.assertEqual(len(cl2.calls), 0, "NO_DATA로 확인된 해를 다시 불렀다")

    def test_request_failure_is_retryable_and_does_not_query_ofs(self):
        client = FakeClient()
        def fail_cfs(corp_code, year, reprt_code, fs_div="CFS"):
            client.calls.append((corp_code, year, fs_div))
            return {"status": dart_client.DART_UNREACHABLE, "data": None}
        client.financial_statement = fail_cfs
        out = C.collect(client, corp_map(1), budget=FakeBudget(), max_companies=1,
                        max_calls=3, today="2026-09-04")
        self.assertEqual(out["status"], "PARTIAL")
        self.assertEqual(out["yearsNoData"], 0)
        self.assertTrue(all(call[2] == "CFS" for call in client.calls))
        self.assertEqual(C.missing_years("000001", C.target_years("2026-09-04")),
                         C.target_years("2026-09-04"))
        retry = C.collect(FakeClient(), corp_map(1), budget=FakeBudget(), max_companies=1,
                          max_calls=3, today="2026-09-05")
        self.assertEqual(retry["yearsStored"], 3)

    def test_only_confirmed_no_data_can_trigger_fallback(self):
        bad = [
            {"status": dart_client.OK, "data": {"status": "000", "list": []}},
            {"status": dart_client.OK, "data": {"status": "013", "list": []}},
            {"status": dart_client.OK, "noData": True,
             "data": {"status": "013", "list": [{"account_id": "unexpected"}]}},
            {"status": dart_client.OK, "noData": 1, "data": fake_payload()},
            {"status": dart_client.OK, "data": {"status": "000", "list": "invalid"}},
        ]
        for response in bad:
            with self.subTest(response=response):
                shutil.rmtree(self.tmp, ignore_errors=True)
                client = FakeClient()
                def invalid(corp_code, year, reprt_code, fs_div="CFS"):
                    client.calls.append((corp_code, year, fs_div))
                    return response
                client.financial_statement = invalid
                out = C.collect(client, corp_map(1), budget=FakeBudget(), max_companies=1,
                                max_calls=1, today="2026-09-04")
                self.assertEqual(out["status"], "PARTIAL")
                self.assertEqual([call[2] for call in client.calls], ["CFS"])
                self.assertNotIn("2025", C.load_company("000001")["years"])

    def test_fallback_and_proven_absence(self):
        client = FakeClient()
        def answer(corp_code, year, reprt_code, fs_div="CFS"):
            client.calls.append((corp_code, year, fs_div))
            if fs_div == "CFS" or year == 2024:
                return {"status": dart_client.OK, "noData": True,
                        "data": {"status": "013"}}
            return {"status": dart_client.OK, "data": fake_payload(corp_code=corp_code, year=year,
                                                                     reprt_code=reprt_code)}
        client.financial_statement = answer
        out = C.collect(client, corp_map(1), budget=FakeBudget(), max_companies=1,
                        max_calls=4, today="2026-09-04")
        doc = C.load_company("000001")["years"]
        self.assertEqual(out["yearsStored"], 1)
        self.assertEqual(doc["2025"]["fsDiv"], "OFS")
        self.assertEqual(doc["2024"]["status"], "NO_DATA")
        self.assertEqual(doc["2024"]["absenceEvidence"], {"CFS": "013", "OFS": "013"})
        self.assertNotIn("2023", doc)

    def test_error_after_confirmed_cfs_absence_remains_retryable(self):
        client = FakeClient()
        def answer(corp_code, year, reprt_code, fs_div="CFS"):
            client.calls.append((corp_code, year, fs_div))
            if fs_div == "CFS":
                return {"status": dart_client.OK, "noData": True,
                        "data": {"status": "013"}}
            return {"status": dart_client.DART_UNREACHABLE, "data": None}
        client.financial_statement = answer
        out = C.collect(client, corp_map(1), budget=FakeBudget(), max_companies=1,
                        max_calls=2, today="2026-09-04")
        self.assertEqual(out["status"], "PARTIAL")
        self.assertNotIn("2025", C.load_company("000001")["years"])

    def test_invalid_existing_store_is_not_overwritten(self):
        path = C.store_path("000001")
        with open(path, "w", encoding="utf-8") as file:
            file.write('{"damaged":')
        client = FakeClient()
        out = C.collect(client, corp_map(1), budget=FakeBudget(), max_companies=1,
                        max_calls=3, today="2026-09-04")
        with open(path, encoding="utf-8") as file:
            self.assertEqual(file.read(), '{"damaged":')
        self.assertEqual(client.calls, [])
        self.assertEqual(out["status"], "PARTIAL")

    def test_client_exception_is_counted_and_does_not_save_error_text(self):
        client = FakeClient()
        client.financial_statement = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret-like-url"))
        budget = FakeBudget()
        out = C.collect(client, corp_map(1), budget=budget, max_companies=1,
                        max_calls=1, today="2026-09-04")
        self.assertEqual((out["status"], out["apiCalls"], budget.spent), ("PARTIAL", 1, 1))
        self.assertEqual(out["errors"][0]["status"], "CLIENT_EXCEPTION")
        self.assertNotIn("secret-like-url", json.dumps(out))
        self.assertFalse(os.path.exists(C.store_path("000001")))

    def test_malformed_success_rows_are_not_saved_as_ok(self):
        for rows in ([{"unexpected": "schema"}],
                     [{"account_id": 123, "sj_div": "BS", "thstrm_amount": "9"}]):
            with self.subTest(rows=rows):
                client = FakeClient()
                client.financial_statement = lambda *a, **k: {
                    "status": dart_client.OK, "data": {"status": "000", "list": rows}}
                out = C.collect(client, corp_map(1), budget=FakeBudget(), max_companies=1,
                                max_calls=1, today="2026-09-04")
                self.assertEqual((out["status"], out["yearsStored"]), ("PARTIAL", 0))
                self.assertFalse(os.path.exists(C.store_path("000001")))

    def test_wrong_company_year_report_or_currency_is_not_saved(self):
        for field, wrong in (("corp_code", "OTHER"), ("bsns_year", "1900"),
                             ("reprt_code", "11013"), ("currency", "USD"), ("currency", None)):
            with self.subTest(field=field, wrong=wrong):
                payload = fake_payload()
                payload["list"][0][field] = wrong
                client = FakeClient()
                client.financial_statement = lambda *a, **k: {"status": dart_client.OK, "data": payload}
                out = C.collect(client, corp_map(1), budget=FakeBudget(), max_companies=1,
                                max_calls=1, today="2026-09-04")
                self.assertEqual((out["status"], out["yearsStored"]), ("PARTIAL", 0))
                self.assertFalse(os.path.exists(C.store_path("000001")))

    def test_extraction_failure_is_retryable(self):
        with patch.object(P, "extract_financials", side_effect=ValueError("unsafe details")):
            out = C.collect(FakeClient(), corp_map(1), budget=FakeBudget(), max_companies=1,
                            max_calls=1, today="2026-09-04")
        self.assertEqual((out["status"], out["yearsStored"]), ("PARTIAL", 0))
        self.assertEqual(out["errors"][0]["status"], "EXTRACT_ERROR")
        self.assertNotIn("unsafe details", json.dumps(out))
        self.assertFalse(os.path.exists(C.store_path("000001")))

    def test_interruption_after_complete_year_saves_only_that_year(self):
        client = FakeClient(empty_for=[("C000001", 2024)])
        out = C.collect(client, corp_map(1), budget=FakeBudget(allow_n=2), max_companies=1,
                        max_calls=9, today="2026-09-04")
        self.assertTrue(out["budgetStopped"])
        self.assertEqual(list(C.load_company("000001")["years"]), ["2025"])
        retry = FakeClient(empty_for=[("C000001", 2024)])
        C.collect(retry, corp_map(1), budget=FakeBudget(), max_companies=1,
                  max_calls=9, today="2026-09-05")
        self.assertTrue(all(call[1] != 2025 for call in retry.calls))
        self.assertEqual(C.load_company("000001")["years"]["2024"]["status"], "NO_DATA")

    def test_persistent_failure_does_not_starve_next_company(self):
        client = FakeClient()
        def answer(corp_code, year, reprt_code, fs_div="CFS"):
            client.calls.append((corp_code, year, fs_div))
            if corp_code == "C000001":
                return {"status": dart_client.DART_UNREACHABLE, "data": None}
            return {"status": dart_client.OK, "data": fake_payload(corp_code=corp_code, year=year,
                                                                     reprt_code=reprt_code)}
        client.financial_statement = answer
        first = C.collect(client, corp_map(2), budget=FakeBudget(), max_companies=1,
                          max_calls=3, today="2026-09-04")
        second = C.collect(client, corp_map(2), budget=FakeBudget(), max_companies=1,
                           max_calls=3, today="2026-09-05", selection_after=first["selectionCursor"])
        self.assertEqual(first["status"], "PARTIAL")
        self.assertEqual(second["yearsStored"], 3)
        self.assertEqual(C.missing_years("000001", C.target_years("2026-09-04")),
                         C.target_years("2026-09-04"))

    def test_corrupt_first_company_does_not_starve_next_company(self):
        with open(C.store_path("000001"), "w", encoding="utf-8") as file:
            file.write('{"damaged":')
        first = C.collect(FakeClient(), corp_map(2), budget=FakeBudget(), max_companies=1,
                          max_calls=3, today="2026-09-04")
        second = C.collect(FakeClient(), corp_map(2), budget=FakeBudget(), max_companies=1,
                           max_calls=3, today="2026-09-05", selection_after=first["selectionCursor"])
        self.assertEqual((first["status"], second["yearsStored"]), ("PARTIAL", 3))
        with open(C.store_path("000001"), encoding="utf-8") as file:
            self.assertEqual(file.read(), '{"damaged":')

    def test_daily_skip_preserves_cursor(self):
        path = os.path.join(self.tmp, "_status.json")
        C.save_status(path, {"status": "PARTIAL", "selectionCursor": "000001"})
        budget = FakeBudget(financial_today=1)
        with patch.object(C, "STATUS_PATH", path), patch.object(C.dart_budget, "DailyBudget", return_value=budget), \
             patch.object(C.dart_client, "DartClient", return_value=FakeClient()), \
             patch.object(C.P, "load_corp_map", return_value=corp_map(2)), \
             patch.object(sys, "argv", ["collect_dart_financials.py", "--once-per-day"]):
            self.assertEqual(C.main(), 0)
        self.assertEqual(C.load_selection_cursor(path), "000001")

    def test_invalid_status_does_not_reset_cursor_or_send_requests(self):
        path = os.path.join(self.tmp, "_status.json")
        with open(path, "w", encoding="utf-8") as file:
            file.write('{"damaged":')
        client = FakeClient()
        with patch.object(C, "STATUS_PATH", path), patch.object(C.dart_budget, "DailyBudget", return_value=FakeBudget()), \
             patch.object(C.dart_client, "DartClient", return_value=client), \
             patch.object(C.P, "load_corp_map", return_value=corp_map(2)), \
             patch.object(sys, "argv", ["collect_dart_financials.py"]):
            self.assertEqual(C.main(), 1)
        self.assertEqual(client.calls, [])
        with open(path, encoding="utf-8") as file:
            self.assertEqual(file.read(), '{"damaged":')

    def test_budget_is_saved_after_unexpected_collection_failure(self):
        budget = FakeBudget()
        budget.save = unittest.mock.Mock()
        with patch.object(C, "STATUS_PATH", os.path.join(self.tmp, "_status.json")), \
             patch.object(C.dart_budget, "DailyBudget", return_value=budget), \
             patch.object(C.dart_client, "DartClient", return_value=FakeClient()), \
             patch.object(C.P, "load_corp_map", return_value=corp_map(1)), \
             patch.object(C, "collect", side_effect=OSError("write failed")), \
             patch.object(sys, "argv", ["collect_dart_financials.py"]):
            with self.assertRaises(OSError):
                C.main()
        budget.save.assert_called_once()

    def test_collects_three_fiscal_years(self):
        """Piotroski는 회계연도 3개가 필요하다."""
        cl = FakeClient()
        out = C.collect(cl, corp_map(1), budget=FakeBudget(), max_companies=1,
                        max_calls=99, today="2026-09-04")
        self.assertEqual(len(out["targetYears"]), C.YEARS_NEEDED)
        doc = C.load_company("000001")
        ok_years = [y for y, v in doc["years"].items() if v["status"] == "OK"]
        self.assertEqual(len(ok_years), 3)

class OncePerDayGate(unittest.TestCase):
    """⭐ 워크플로는 장중 30분마다 돈다. 게이트가 없으면 하루 2,100호출이 되는데
       일일 목표는 500호출이다. 연간 재무는 하루 한 번이면 충분하다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = C.STORE_DIR
        C.STORE_DIR = self.tmp

    def tearDown(self):
        C.STORE_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_second_run_of_the_day_is_skipped(self):
        cl = FakeClient()
        out = C.collect(cl, corp_map(3), budget=FakeBudget(financial_today=12),
                        once_per_day=True, today="2026-09-04")
        self.assertEqual(out["status"], C.SKIPPED_ALREADY_TODAY)
        self.assertEqual(len(cl.calls), 0)

    def test_first_run_of_the_day_proceeds(self):
        cl = FakeClient()
        out = C.collect(cl, corp_map(1), budget=FakeBudget(financial_today=0),
                        once_per_day=True, max_companies=1, max_calls=99,
                        today="2026-09-04")
        self.assertEqual(out["status"], C.OK)
        self.assertGreater(len(cl.calls), 0)

    def test_gate_is_opt_in(self):
        """게이트를 안 켜면 예전처럼 그대로 돈다(수동 실행·백필용)."""
        cl = FakeClient()
        out = C.collect(cl, corp_map(1), budget=FakeBudget(financial_today=99),
                        max_companies=1, max_calls=99, today="2026-09-04")
        self.assertEqual(out["status"], C.OK)


class YearSelection(unittest.TestCase):
    def test_before_april_uses_one_year_earlier(self):
        """사업보고서는 회계연도 종료 뒤 3개월 안에 나온다. 1~3월에는 작년치가 없다."""
        self.assertEqual(C.target_years("2026-02-10")[0], 2024)
        self.assertEqual(C.target_years("2026-05-10")[0], 2025)


class WorkflowWiring(unittest.TestCase):
    """워크플로 연결 계약 — 예산을 지키는 형태로만 연결돼야 한다."""

    # 2026-09-24: update-analysis.yml 은퇴 — DART 단일 생산자는 corporate-action-evidence.yml 이다.
    WF = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      ".github", "workflows", "corporate-action-evidence.yml")

    def setUp(self):
        if not os.path.exists(self.WF):
            self.skipTest("워크플로 파일 없음")
        with open(self.WF, encoding="utf-8") as f:
            self.text = f.read()

    def test_collector_is_wired(self):
        self.assertIn("collect_dart_financials.py", self.text,
                      "재무 수집이 워크플로에 연결되지 않았다")

    def test_once_per_day_flag_is_present(self):
        """⭐ 이 플래그가 빠지면 예산이 샌다 — 하루 2회 도는 워크플로에서도 재무는 1회로 묶는다(목표 500회)."""
        self.assertRegex(
            self.text, r"collect_dart_financials\.py\s+--once-per-day",
            "--once-per-day가 빠졌다. 장중 30분마다 도는 워크플로라 예산이 터진다.")

    def test_failure_does_not_stop_the_pipeline(self):
        """재무 수집이 실패해도 시세·판단 파이프라인은 계속 돌아야 한다."""
        idx = self.text.index("collect_dart_financials.py")
        tail = self.text[idx:idx + 260]
        self.assertIn("||", tail,
                      "재무 수집 실패가 파이프라인 전체를 멈추면 안 된다")

    def test_collected_data_is_committed(self):
        self.assertIn("git add dart_financials", self.text,
                      "받은 재무 자료가 커밋되지 않으면 다음 실행에서 또 받는다")

    def test_financial_budget_uses_the_persisted_dart_store(self):
        from pathlib import Path
        self.assertIn('os.path.join(P.DART_ROOT, "api_budget.json")', Path(C.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
