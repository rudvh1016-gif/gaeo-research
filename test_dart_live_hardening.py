#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LIVE CONNECTION & PRE-V2 HARDENING 테스트.

Durable Write · Pagination Coverage · Timezone · API 예산 ·
DART Raw Schema 분리 · gzip Integration을 검사한다.
성능이나 정확도는 검사하지 않는다.
"""
import datetime
import gzip
import json
import os
import shutil
import tempfile
import unittest
from zoneinfo import ZoneInfo

import dart_budget
import dart_client as C
import dart_pipeline as P
import dart_time as T
import research_crypto as CR
import research_store as S


UNIVERSE = {"005930": {"name": "삼성전자", "sector": "반도체"},
            "000660": {"name": "SK하이닉스", "sector": "반도체"}}
DART_ROWS = [{"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930"},
             {"corp_code": "00164779", "corp_name": "에스케이하이닉스", "stock_code": "000660"}]


def _filing(no, corp="00126380", name="주요사항보고서"):
    return {"corp_code": corp, "rcept_no": no, "report_nm": name,
            "corp_cls": "Y", "rcept_dt": "20260815"}


class FakeClient:
    """네트워크 없이 목록 API 응답을 흉내낸다."""
    has_key = True

    def __init__(self, pages, fail_from=None):
        self.pages = pages
        self.fail_from = fail_from
        self.calls = []
        self.stats = {"requests_per_run": 0, "detail_requests": 0, "api_errors": 0}

    def list_filings(self, **kw):
        self.calls.append(kw)
        self.stats["requests_per_run"] += 1
        page = kw.get("page_no", 1)
        if self.fail_from is not None and page >= self.fail_from:
            self.stats["api_errors"] += 1
            return {"status": C.EVENT_DATA_ERROR, "data": None, "error": "HTTP 500"}
        return {"status": C.OK, "data": self.pages.get(page, {"list": [], "total_page": 1}),
                "error": None}

    def efficiency_report(self, extra=None):
        out = dict(self.stats); out.update(extra or {}); return out


# ── 0. Secret 이름 ───────────────────────────────────────────────────────────
class SecretName(unittest.TestCase):
    def test_canonical_name(self):
        self.assertEqual(C.KEY_ENV, "OPEN_DART_API_KEY")

    def test_no_stale_name_anywhere(self):
        here = os.path.dirname(os.path.abspath(__file__))
        targets = ["dart_client.py", "collect_dart.py", "dart_pipeline.py",
                   ".github/workflows/update-analysis.yml",
                   ".github/workflows/corporate-action-evidence.yml",
                   "docs/gaeo_research_v2_plan.md"]
        for rel in targets:
            path = os.path.join(here, rel)
            if not os.path.exists(path):
                continue
            src = open(path, encoding="utf-8").read()
            # OPENDART_API_KEY(언더바 없는 옛 이름)가 남아 있으면 안 된다
            self.assertNotIn("OPENDART_API_KEY", src, f"{rel}에 옛 Secret 이름이 남아 있다")

    def test_workflow_uses_secret(self):
        here = os.path.dirname(os.path.abspath(__file__))
        # 2026-09-24: DART 단일 생산자는 corporate-action-evidence.yml 이다(update-analysis.yml 은퇴).
        src = open(os.path.join(here, ".github/workflows/corporate-action-evidence.yml"),
                   encoding="utf-8").read()
        self.assertIn("OPEN_DART_API_KEY: ${{ secrets.OPEN_DART_API_KEY }}", src)


# ── 8·9. Timezone ────────────────────────────────────────────────────────────
class Timezone(unittest.TestCase):
    def test_today_is_seoul_not_runner(self):
        """Runner가 UTC여도 한국 날짜를 쓴다."""
        self.assertEqual(T.today_kst(), datetime.datetime.now(T.KST).date().isoformat())
        # UTC 오후 3시 이후는 한국에서 다음 날이다
        utc_today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        kst_today = T.today_kst()
        self.assertIn(kst_today, {utc_today,
                                  (datetime.date.fromisoformat(utc_today)
                                   + datetime.timedelta(days=1)).isoformat()})

    def test_iso_now_is_aware(self):
        dt = T.parse_instant(T.iso_now())
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo)

    def test_naive_is_rejected(self):
        self.assertIsNone(T.parse_instant("2026-08-15T14:20:00"))

    def test_garbage_is_rejected(self):
        for bad in ("", None, "어제", "2026-13-45T99:99:99+00:00", 12345):
            self.assertIsNone(T.parse_instant(bad))

    def test_z_suffix_supported(self):
        self.assertIsNotNone(T.parse_instant("2026-08-15T14:20:00Z"))


class EventInstantComparison(unittest.TestCase):
    """문자열 비교로 시간순서를 판정하지 않는다."""

    def test_different_offsets_same_instant(self):
        a = "2026-08-15T23:30:00+09:00"      # UTC 14:30
        b = "2026-08-15T14:30:00+00:00"      # 같은 순간
        self.assertTrue(P.event_visible_at({"detected_at": a}, b))
        self.assertTrue(P.event_visible_at({"detected_at": b}, a))

    def test_string_comparison_would_be_wrong(self):
        """문자열이었다면 틀렸을 사례가 실제로 맞게 나오는지."""
        det = "2026-08-15T23:30:00+09:00"    # UTC 14:30
        pred = "2026-08-15T15:00:00+00:00"   # UTC 15:00 — 실제로는 더 나중
        self.assertFalse(str(det) <= str(pred), "이 사례는 문자열 비교가 틀린다")
        self.assertTrue(P.event_visible_at({"detected_at": det}, pred))

    def test_one_second_before(self):
        self.assertTrue(P.event_visible_at(
            {"detected_at": "2026-08-15T14:19:59+00:00"}, "2026-08-15T14:20:00+00:00"))

    def test_exact_same_instant(self):
        t = "2026-08-15T14:20:00+00:00"
        self.assertTrue(P.event_visible_at({"detected_at": t}, t))

    def test_one_second_after_is_blocked(self):
        self.assertFalse(P.event_visible_at(
            {"detected_at": "2026-08-15T14:20:01+00:00"}, "2026-08-15T14:20:00+00:00"))

    def test_naive_timestamp_is_blocked(self):
        self.assertFalse(P.event_visible_at(
            {"detected_at": "2026-08-15T14:20:00"}, "2026-08-15T23:00:00+00:00"))
        self.assertFalse(P.event_visible_at(
            {"detected_at": "2026-08-15T14:20:00+00:00"}, "2026-08-15T23:00:00"))

    def test_invalid_timestamp_is_blocked(self):
        self.assertFalse(P.event_visible_at({"detected_at": "어제"}, T.iso_now()))
        self.assertFalse(P.event_visible_at({}, T.iso_now()))


# ── 5. Durable Write ─────────────────────────────────────────────────────────
class DurableWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gaeo-durable-")
        self.seen = os.path.join(self.tmp, "seen.json")
        self._saved_key = os.environ.get(CR.KEY_ENV)
        os.environ[CR.KEY_ENV] = CR.generate_key_b64()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._saved_key is None:
            os.environ.pop(CR.KEY_ENV, None)
        else:
            os.environ[CR.KEY_ENV] = self._saved_key

    def _collect(self, client=None):
        cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        client = client or FakeClient({1: {"list": [_filing("A1")], "total_page": 1}})
        return P.collect_new_filings(client, cmap, seen_path=self.seen)

    def test_collection_only_marks_pending(self):
        """수집 단계에서 ACKNOWLEDGED로 확정하면 안 된다."""
        res = self._collect()
        reg = res["registry"]
        self.assertEqual(reg.seen["A1"]["state"], P.SeenRegistry.PENDING)
        self.assertEqual(res["events"][0]["processing_status"], P.SeenRegistry.PENDING)

    def test_pending_is_still_new_next_run(self):
        """저장 전에 죽으면 다음 실행에서 반드시 다시 수집한다."""
        res = self._collect()
        res["registry"].save()                     # ACK 없이 저장(=크래시 흉내)
        res2 = self._collect()
        self.assertEqual([e["rcept_no"] for e in res2["events"]], ["A1"],
                         "저장 실패한 공시가 재시도되지 않았다")

    def test_acknowledged_is_skipped(self):
        res = self._collect()
        res["registry"].acknowledge_many(["A1"])
        res["registry"].save()
        res2 = self._collect()
        self.assertEqual(res2["events"], [])
        self.assertEqual(res2["stats"]["duplicate_skipped"], 1)

    def test_fault_injection_storage_failure_retries(self):
        """Raw 저장을 강제로 실패시키면 ACK가 안 되고 다음 실행에서 재수집된다."""
        res = self._collect()
        reg = res["registry"]
        store = S.ResearchArchiveStore(root=os.path.join(self.tmp, "arc"),
                                       record_type=S.RECORD_DART)
        day = T.today_kst()
        try:
            orig = store.append_predictions
            def boom(*a, **k):
                raise OSError("디스크 가득 참(주입된 오류)")
            store.append_predictions = boom
            try:
                store.append_predictions(day, res["events"], today=day)
            except OSError:
                pass          # 저장 실패 — ACK 하지 않는다
        finally:
            store.append_predictions = orig
        reg.save()
        self.assertNotEqual(reg.seen["A1"]["state"], P.SeenRegistry.ACKNOWLEDGED)
        res2 = self._collect()
        self.assertEqual([e["rcept_no"] for e in res2["events"]], ["A1"])

    def test_ack_only_after_readback(self):
        """저장 후 실제로 읽히는 것만 ACK한다."""
        res = self._collect()
        reg = res["registry"]
        store = S.ResearchArchiveStore(root=os.path.join(self.tmp, "arc2"),
                                       record_type=S.RECORD_DART)
        day = T.today_kst()
        store.append_predictions(day, [dict(e, date=day) for e in res["events"]], today=day)
        saved = {str(r.get("rcept_no")) for r in store.read_day(day)}
        self.assertIn("A1", saved)
        reg.acknowledge_many([n for n in ["A1"] if n in saved])
        self.assertEqual(reg.seen["A1"]["state"], P.SeenRegistry.ACKNOWLEDGED)

    def test_pending_count_reported(self):
        res = self._collect()
        self.assertEqual(res["pendingTotal"], 1)

    def test_registry_save_is_atomic(self):
        res = self._collect()
        res["registry"].save()
        self.assertTrue(os.path.exists(self.seen))
        self.assertFalse(os.path.exists(self.seen + ".tmp"))
        data = json.load(open(self.seen, encoding="utf-8"))
        self.assertEqual(data["schemaVersion"], "dart_seen_v2")


# ── 6. Pagination Coverage ───────────────────────────────────────────────────
class PaginationCoverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gaeo-page-")
        self.seen = os.path.join(self.tmp, "seen.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, pages, max_pages=None, client=None):
        cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        client = client or FakeClient(pages)
        return P.collect_new_filings(client, cmap, seen_path=self.seen,
                                     max_pages=max_pages)

    def test_full_coverage_marked_complete(self):
        res = self._run({1: {"list": [_filing("A1")], "total_page": 1}})
        self.assertTrue(res["pagination"]["coverage_complete"])
        self.assertEqual(res["pagination"]["incomplete_reasons"], [])

    def test_page_limit_marks_incomplete(self):
        pages = {i: {"list": [_filing(f"A{i}")] * 100, "total_page": 5} for i in range(1, 6)}
        res = self._run(pages, max_pages=2)
        self.assertFalse(res["pagination"]["coverage_complete"])
        self.assertIn(P.PAGE_LIMIT_REACHED, res["pagination"]["incomplete_reasons"])
        self.assertEqual(res["pagination"]["pages_fetched"], 2)
        self.assertEqual(res["pagination"]["total_pages_reported"], 5)

    def test_incomplete_never_reports_no_event(self):
        """전체를 못 훑었으면 '공시 없음'이라고 말하면 안 된다."""
        pages = {i: {"list": [], "total_page": 5} for i in range(1, 6)}
        res = self._run(pages, max_pages=2)
        state, reasons = P.coverage_state([], [], True, res["pagination"])
        self.assertEqual(state, P.EVENT_COVERAGE_INCOMPLETE)
        self.assertNotEqual(state, P.NO_OFFICIAL_EVENT_DETECTED)
        self.assertIn(P.PAGE_LIMIT_REACHED, reasons)

    def test_complete_and_empty_is_no_event(self):
        res = self._run({1: {"list": [], "total_page": 1}})
        state, reasons = P.coverage_state([], [], True, res["pagination"])
        self.assertEqual(state, P.NO_OFFICIAL_EVENT_DETECTED)
        self.assertEqual(reasons, [])

    def test_api_error_marks_incomplete(self):
        pages = {1: {"list": [_filing("A1")] * 100, "total_page": 3}}
        res = self._run(pages, client=FakeClient(pages, fail_from=2))
        self.assertFalse(res["pagination"]["coverage_complete"])
        state, reasons = P.coverage_state(res["events"], res["errors"], True, res["pagination"])
        self.assertEqual(state, P.EVENT_DATA_ERROR)

    def test_walks_all_pages_when_allowed(self):
        pages = {i: {"list": [_filing(f"P{i}")] * 100, "total_page": 3} for i in range(1, 4)}
        res = self._run(pages, max_pages=10)
        self.assertEqual(res["pagination"]["pages_fetched"], 3)
        self.assertTrue(res["pagination"]["coverage_complete"])

    def test_no_api_key_is_incomplete(self):
        state, reasons = P.coverage_state([], [], has_key=False)
        self.assertEqual(state, P.EVENT_COVERAGE_INCOMPLETE)
        self.assertIn(P.NO_API_KEY, reasons)


# ── 7. API 예산 ──────────────────────────────────────────────────────────────
class ApiBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gaeo-budget-")
        self.path = os.path.join(self.tmp, "budget.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_config_in_one_place(self):
        self.assertEqual(dart_budget.DAILY_HARD_LIMIT, 10000)
        self.assertLess(dart_budget.SOFT_BUDGET, dart_budget.DAILY_HARD_LIMIT)
        self.assertLess(dart_budget.NORMAL_TARGET_PER_DAY, dart_budget.SOFT_BUDGET)

    def test_counts_persist_across_runs(self):
        b = dart_budget.DailyBudget(self.path)
        b.spend("list", 5); b.save()
        b2 = dart_budget.DailyBudget(self.path)
        self.assertEqual(b2.total, 5)
        self.assertEqual(b2.runs, 1)

    def test_resets_on_new_kst_day(self):
        b = dart_budget.DailyBudget(self.path)
        b.spend("list", 5); b.save()
        data = json.load(open(self.path, encoding="utf-8"))
        data["day"] = "2020-01-01"
        json.dump(data, open(self.path, "w", encoding="utf-8"))
        self.assertEqual(dart_budget.DailyBudget(self.path).total, 0)

    def test_soft_budget_stops_optional_first(self):
        b = dart_budget.DailyBudget(self.path)
        b.spend("list", dart_budget.SOFT_BUDGET)
        self.assertFalse(b.allow("financial"), "비필수 요청이 먼저 끊겨야 한다")
        self.assertFalse(b.allow("detail"))
        self.assertTrue(b.allow("list"), "공시 목록 탐지는 계속해야 한다")
        self.assertEqual(b.status(), dart_budget.DART_BUDGET_WARNING)

    def test_hard_limit_stops_everything(self):
        b = dart_budget.DailyBudget(self.path)
        b.spend("list", dart_budget.DAILY_HARD_LIMIT)
        self.assertFalse(b.allow("list"))
        self.assertEqual(b.status(), dart_budget.DART_BUDGET_EXCEEDED)

    def test_budget_stop_marks_incomplete_not_empty(self):
        """예산 때문에 멈춘 것을 '공시 없음'으로 해석하면 안 된다."""
        tmp = tempfile.mkdtemp()
        try:
            b = dart_budget.DailyBudget(os.path.join(tmp, "b.json"))
            b.spend("list", dart_budget.DAILY_HARD_LIMIT)
            cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
            client = FakeClient({1: {"list": [_filing("A1")], "total_page": 1}})
            res = P.collect_new_filings(client, cmap,
                                        seen_path=os.path.join(tmp, "s.json"), budget=b)
            self.assertFalse(res["pagination"]["coverage_complete"])
            self.assertIn(P.BUDGET_LIMIT_REACHED, res["pagination"]["incomplete_reasons"])
            state, _r = P.coverage_state(res["events"], res["errors"], True, res["pagination"])
            self.assertEqual(state, P.EVENT_COVERAGE_INCOMPLETE)
            self.assertEqual(client.stats["requests_per_run"], 0, "예산 초과인데 호출했다")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_report_fields(self):
        b = dart_budget.DailyBudget(self.path)
        b.spend("list", 3)
        rep = b.report()
        for k in ("requests_today", "byKind", "hard_limit", "soft_budget",
                  "remaining", "usage_pct_of_hard_limit", "status"):
            self.assertIn(k, rep)

    def test_projection(self):
        pr = dart_budget.project(list_requests_per_run=2, runs_per_day=14,
                                 mapping_per_day=1, financial_per_day=20)
        self.assertEqual(pr["expected_daily_requests"], 2 * 14 + 1 + 20)
        self.assertLess(pr["pct_of_hard_limit"], 5.0)


# ── 10·11. DART Raw Archive Schema ───────────────────────────────────────────
def _dart_event(no, day="2026-08-15"):
    return {"rcept_no": no, "corp_code": "00126380", "ticker": "005930",
            "stock_code": "005930", "date": day,
            "detected_at": "2026-08-15T14:20:00+00:00",
            "fetched_at": "2026-08-15T14:20:01+00:00",
            "source": "OPENDART", "sourceMode": P.LIVE_DART_PIT,
            "report_name": "주요사항보고서", "rcept_dt": "20260815",
            "is_correction": False, "processing_status": "ACKNOWLEDGED"}


class DartArchiveSchema(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gaeo-dartarc-")
        self._saved_key = os.environ.get(CR.KEY_ENV)
        os.environ[CR.KEY_ENV] = CR.generate_key_b64()
        self.store = S.ResearchArchiveStore(root=self.tmp, record_type=S.RECORD_DART)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._saved_key is None:
            os.environ.pop(CR.KEY_ENV, None)
        else:
            os.environ[CR.KEY_ENV] = self._saved_key

    def test_dart_event_passes_dart_validator(self):
        day = "2026-08-15"
        self.store.append_predictions(day, [_dart_event("A1")], today=day)
        self.store.close_daily_segment(day, today="2026-08-16")
        v = self.store.verify_archive(day)
        self.assertEqual(v["status"], S.OK, v.get("errors"))

    def test_dart_event_would_fail_research_validator(self):
        """스키마를 안 나눴다면 정상 Event가 손상으로 잡혔을 것이다."""
        day = "2026-08-15"
        wrong = S.ResearchArchiveStore(root=os.path.join(self.tmp, "w"),
                                       record_type=S.RECORD_RESEARCH)   # 잘못된 스키마
        wrong.append_predictions(day, [_dart_event("A1")], today=day)
        wrong.close_daily_segment(day, today="2026-08-16")
        v = wrong.verify_archive(day)
        self.assertEqual(v["status"], S.ARCHIVE_INTEGRITY_ERROR)
        self.assertTrue(any("modelVersion" in e for e in v["errors"]))

    def test_no_fake_model_version_injected(self):
        day = "2026-08-15"
        self.store.append_predictions(day, [_dart_event("A1")], today=day)
        rec = self.store.read_day(day)[0]
        self.assertNotIn("modelVersion", rec)
        self.assertNotIn("research", rec)

    def test_missing_required_field_detected(self):
        day = "2026-08-15"
        bad = _dart_event("A1"); bad.pop("detected_at")
        self.store.append_predictions(day, [bad], today=day)
        self.store.close_daily_segment(day, today="2026-08-16")
        v = self.store.verify_archive(day)
        self.assertEqual(v["status"], S.ARCHIVE_INTEGRITY_ERROR)

    def test_dedup_key_is_rcept_no(self):
        day = "2026-08-15"
        self.store.append_predictions(day, [_dart_event("A1")], today=day)
        a, r = self.store.append_predictions(day, [_dart_event("A1")], today=day)
        self.assertEqual((a, r), (0, 1))
        self.assertEqual(len(self.store.read_day(day)), 1)

    def test_manifest_records_type(self):
        day = "2026-08-15"
        self.store.append_predictions(day, [_dart_event("A1")], today=day)
        m = self.store.close_daily_segment(day, today="2026-08-16")
        self.assertEqual(m["recordType"], S.RECORD_DART)


class DartArchiveIntegration(unittest.TestCase):
    """append → close → gzip → manifest → decompress → count → sha256 → restore."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gaeo-dartint-")
        self._saved_key = os.environ.get(CR.KEY_ENV)
        os.environ[CR.KEY_ENV] = CR.generate_key_b64()
        self.store = S.ResearchArchiveStore(root=self.tmp, record_type=S.RECORD_DART)
        self.day = "2026-08-15"
        self.n = 120
        self.store.append_predictions(
            self.day, [_dart_event(f"2026081500{i:04d}") for i in range(self.n)],
            today=self.day)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._saved_key is None:
            os.environ.pop(CR.KEY_ENV, None)
        else:
            os.environ[CR.KEY_ENV] = self._saved_key

    def test_full_cycle(self):
        self.store.close_daily_segment(self.day, today="2026-08-16")
        res = self.store.compress_segment(self.day, today="2026-08-16")
        self.assertEqual(res["status"], S.OK, res)
        self.assertEqual(res["recordCount"], self.n)

        gz = self.store.segment_path(self.day, True)
        self.assertTrue(os.path.exists(gz))
        self.assertTrue(gz.endswith(".gz.enc"), "DART Raw도 암호화돼야 한다")
        text = S._read_text(gz, self.store._label(self.day))
        rows = [json.loads(l) for l in text.splitlines() if l.strip()]
        self.assertEqual(len(rows), self.n)
        self.assertEqual(rows[0]["source"], "OPENDART")

        r = self.store.restore_test(self.day)
        self.assertEqual(r["status"], S.OK, r.get("errors"))
        self.assertEqual(r["recordCount"], self.n)
        self.assertTrue(r["compressed"])

    def test_manifest_sha256_matches_after_compression(self):
        self.store.close_daily_segment(self.day, today="2026-08-16")
        self.store.compress_segment(self.day, today="2026-08-16")
        m = json.load(open(self.store.manifest_path(self.day), encoding="utf-8"))
        gz = self.store.segment_path(self.day, True)
        self.assertEqual(m["sha256"][os.path.basename(gz)], S._sha256_file(gz))
        self.assertEqual(m["recordCount"], self.n)

    def test_rollups_work_on_dart_schema(self):
        self.store.close_daily_segment(self.day, today="2026-08-16")
        self.store.compress_segment(self.day, today="2026-08-16")
        w = self.store.rollup_week("2026-W33", [self.day])
        self.assertEqual(w["recordCount"], self.n)
        m = self.store.rollup_month("2026-08")
        self.assertEqual(m["status"], S.OK)
        self.assertEqual(m["recordCount"], self.n)

    def test_corrupted_dart_archive_detected(self):
        self.store.close_daily_segment(self.day, today="2026-08-16")
        self.store.compress_segment(self.day, today="2026-08-16")
        with open(self.store.segment_path(self.day, True), "r+b") as f:
            f.seek(50); f.write(b"\x00\x01\x02\x03")
        self.assertEqual(self.store.verify_archive(self.day)["status"],
                         S.ARCHIVE_INTEGRITY_ERROR)

    def test_compression_ratio_measured_separately(self):
        self.store.close_daily_segment(self.day, today="2026-08-16")
        res = self.store.compress_segment(self.day, today="2026-08-16")
        self.assertGreater(res["rawBytes"], 0)
        self.assertGreater(res["compressedBytes"], 0)
        self.assertLess(res["compressionRatio"], 1.0)


# ── 1. v1.x 동결 유지 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=1)
