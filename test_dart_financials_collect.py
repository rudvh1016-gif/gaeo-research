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
import tempfile
import unittest
from unittest.mock import patch

import collect_dart_financials as C
import dart_client
import dart_pipeline as P


def fake_payload(assets=2000):
    return {"status": "000", "list": [
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
            return {"status": dart_client.OK, "data": {"status": "013", "list": []}}
        return {"status": dart_client.OK, "data": fake_payload()}


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
        with patch.object(client, "financial_statement", return_value={"status": dart_client.OK, "data": fake_payload()}):
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
