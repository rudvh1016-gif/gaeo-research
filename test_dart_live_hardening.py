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
import re
import signal
import shutil
import subprocess
import sys
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


_TEST_RECEIPTS = {}
def _filing(no, corp="00126380", name="주요사항보고서"):
    if not re.fullmatch(r'[0-9]{14}', no):
        if no not in _TEST_RECEIPTS:
            _TEST_RECEIPTS[no] = len(_TEST_RECEIPTS) + 1
        no = f"20260815{_TEST_RECEIPTS[no]:06d}"
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
        data = dict(self.pages.get(page, {"list": [], "total_page": 1}))
        if 'status' not in data:
            if data.get('list') == []:
                return {'status':C.OK, 'data':{'status':'013'}, 'noData':True}
            data.update(status='000', page_no=page, total_count=len(data.get('list', [])))
        return {"status": C.OK, "data": data, "error": None}

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
        return P.collect_new_filings(client, cmap, seen_path=self.seen, bgn_de='20260815', end_de='20260815')

    def test_collection_only_marks_pending(self):
        """수집 단계에서 ACKNOWLEDGED로 확정하면 안 된다."""
        res = self._collect()
        reg = res["registry"]
        self.assertEqual(reg.seen[_filing('A1')['rcept_no']]["state"], P.SeenRegistry.PENDING)
        self.assertEqual(res["events"][0]["processing_status"], P.SeenRegistry.PENDING)

    def test_pending_is_still_new_next_run(self):
        """저장 전에 죽으면 다음 실행에서 반드시 다시 수집한다."""
        res = self._collect()
        res["registry"].save()                     # ACK 없이 저장(=크래시 흉내)
        res2 = self._collect()
        self.assertEqual([e["rcept_no"] for e in res2["events"]], [_filing('A1')['rcept_no']],
                         "저장 실패한 공시가 재시도되지 않았다")

    def test_acknowledged_is_skipped(self):
        res = self._collect()
        res["registry"].acknowledge_many([_filing('A1')['rcept_no']])
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
        self.assertNotEqual(reg.seen[_filing('A1')['rcept_no']]["state"], P.SeenRegistry.ACKNOWLEDGED)
        res2 = self._collect()
        self.assertEqual([e["rcept_no"] for e in res2["events"]], [_filing('A1')['rcept_no']])

    def test_ack_only_after_readback(self):
        """저장 후 실제로 읽히는 것만 ACK한다."""
        res = self._collect()
        reg = res["registry"]
        store = S.ResearchArchiveStore(root=os.path.join(self.tmp, "arc2"),
                                       record_type=S.RECORD_DART)
        day = T.today_kst()
        store.append_predictions(day, [dict(e, date=day) for e in res["events"]], today=day)
        saved = {str(r.get("rcept_no")) for r in store.read_day(day)}
        self.assertIn(_filing('A1')['rcept_no'], saved)
        reg.acknowledge_many([n for n in [_filing('A1')['rcept_no']] if n in saved])
        self.assertEqual(reg.seen[_filing('A1')['rcept_no']]["state"], P.SeenRegistry.ACKNOWLEDGED)

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
        return P.collect_new_filings(client, cmap, seen_path=self.seen, bgn_de='20260815', end_de='20260815',
                                     max_pages=max_pages)

    class RawClient:
        has_key = True
        def __init__(self, responses):
            self.responses = responses
            self.calls = []
        def list_filings(self, **kw):
            self.calls.append(kw)
            return self.responses[kw['page_no'] - 1]

    def raw(self, responses):
        return self._run({}, client=self.RawClient(responses))

    @staticmethod
    def response(rows, total_page=1, total_count=1, page_no=1):
        return {'status': C.OK, 'error': None, 'data': {'status':'000', 'page_no':page_no,
                'total_page':total_page, 'total_count':total_count, 'list':rows}}

    def test_later_no_data_does_not_certify_partial_listing(self):
        result = self.raw([self.response([_filing('A1')], total_page=2, total_count=2),
                           {'status':C.OK,'data':{'status':'013'},'noData':True}])
        self.assertFalse(result['pagination']['coverage_complete'])
        self.assertNotIn(P.coverage_state(result['events'],result['errors'],True,result['pagination'])[0], P.COMPLETE_STATES)
        self.assertEqual([event['rcept_no'] for event in result['events']], [_filing('A1')['rcept_no']])
        self.assertEqual(result['registry'].pending_count(), 1)

    def test_changing_page_or_total_count_is_not_complete(self):
        for second in (self.response([_filing('A2')], total_page=2, total_count=2, page_no=2),
                       self.response([_filing('A2')], total_page=3, total_count=3, page_no=2)):
            with self.subTest(second=second):
                result = self.raw([self.response([_filing('A1')], total_page=2, total_count=3), second])
                self.assertFalse(result['pagination']['coverage_complete'])
                self.assertEqual(result['registry'].pending_count(), 1)

    def test_unrecognized_or_contradictory_page_metadata_is_incomplete(self):
        for payload in ({'status':'000'},
                        {'status':'000','list':[],'total_page':1,'total_count':3},
                        {'status':'000','list':[_filing('A1')],'total_page':True,'total_count':1},
                        {'status':'000','list':[_filing('A1')],'total_page':1,'total_count':0},
                        {'status':'000','list':[None],'total_page':1,'total_count':1},
                        {'status':'000','list':[_filing('A1')],'total_page':1,'total_count':1,'page_no':2}):
            with self.subTest(payload=payload):
                result = self.raw([{'status':C.OK,'error':None,'data':payload}])
                self.assertFalse(result['pagination']['coverage_complete'])
                self.assertNotIn(P.coverage_state(result['events'],result['errors'],True,result['pagination'])[0], P.COMPLETE_STATES)

    def test_count_checks_include_unmatched_and_repeated_rows(self):
        valid = self.raw([self.response([_filing('A1',corp='77777777'), _filing('A2')], total_count=2)])
        self.assertTrue(valid['pagination']['coverage_complete'])
        self.assertEqual(len(valid['events']), 1)
        repeated = self.raw([self.response([_filing('A1')], total_page=2, total_count=2),
                             self.response([_filing('A1')], total_page=2, total_count=2, page_no=2)])
        self.assertFalse(repeated['pagination']['coverage_complete'])

    def test_invalid_identifier_or_query_date_never_certifies_coverage(self):
        for row in (dict(_filing('A1'), corp_code='N/A'), dict(_filing('A1'), rcept_no='notid'),
                    dict(_filing('A1'), rcept_dt='20260816'), dict(_filing('A1'), rcept_dt='20260230'),
                    dict(_filing('A1'), rcept_dt=None),
                    dict(_filing('A1'), rcept_no='20260816000001')):
            with self.subTest(row=row):
                result = self.raw([self.response([row])])
                self.assertFalse(result['pagination']['coverage_complete'])
                self.assertEqual(result['events'], [])

    def test_first_page_official_no_data_is_complete(self):
        result = self.raw([{'status':C.OK,'data':{'status':'013'},'noData':True}])
        self.assertTrue(result['pagination']['coverage_complete'])
        self.assertEqual(P.coverage_state([], [], True, result['pagination'])[0],P.NO_OFFICIAL_EVENT_DETECTED)

    def test_received_time_is_not_before_each_page_response(self):
        from unittest import mock
        clock = {'now':'2026-08-15T00:00:00+00:00'}
        responses = [self.response([_filing('A1')],total_page=2,total_count=2),
                     self.response([_filing('A2')],total_page=2,total_count=2,page_no=2)]
        class Client(self.RawClient):
            def list_filings(self, **kw):
                clock['now'] = ('2026-08-15T00:00:05+00:00' if kw['page_no'] == 1
                                else '2026-08-15T00:00:10+00:00')
                return super().list_filings(**kw)
        with mock.patch.object(T, 'iso_now', side_effect=lambda:clock['now']):
            result = self._run({}, client=Client(responses))
        self.assertEqual([e['detected_at'] for e in result['events']],
                         ['2026-08-15T00:00:05+00:00','2026-08-15T00:00:10+00:00'])
        self.assertFalse(P.event_visible_at(result['events'][0], '2026-08-15T00:00:04+00:00'))
        self.assertFalse(P.event_visible_at(result['events'][1], '2026-08-15T00:00:09+00:00'))

    def test_clock_rollback_between_pages_is_unverified(self):
        from unittest import mock
        clock = {'now':'2026-08-15T00:00:00+00:00'}
        responses = [self.response([_filing('A1')],total_page=2,total_count=2),
                     self.response([_filing('A2')],total_page=2,total_count=2,page_no=2)]
        class Client(self.RawClient):
            def list_filings(self, **kw):
                clock['now'] = ('2026-08-15T00:00:05+00:00' if kw['page_no'] == 1
                                else '2026-08-15T00:00:02+00:00')
                return super().list_filings(**kw)
        mark = P.SeenRegistry.mark_pending
        def mark_then_rollback(registry, receipt, meta):
            mark(registry, receipt, meta)
            clock['now'] = '2026-08-15T00:00:01+00:00'
        with mock.patch.object(T, 'iso_now', side_effect=lambda:clock['now']), \
             mock.patch.object(P.SeenRegistry, 'mark_pending', mark_then_rollback):
            result = self._run({},client=Client(responses))
        self.assertFalse(result['pagination']['coverage_complete'])
        self.assertEqual(len(result['events']), 1)

    def test_clock_rollback_before_request_is_not_hidden_by_later_recovery(self):
        from unittest import mock
        clock = {'now':'2026-08-15T00:00:00+00:00'}
        responses = [self.response([_filing('A1')],total_page=2,total_count=2),
                     self.response([_filing('A2')],total_page=2,total_count=2,page_no=2)]
        class Client(self.RawClient):
            def list_filings(self, **kw):
                clock['now'] = ('2026-08-15T00:00:05+00:00' if kw['page_no'] == 1
                                else '2026-08-15T00:00:06+00:00')
                return super().list_filings(**kw)
        mark = P.SeenRegistry.mark_pending
        def mark_then_rollback(registry, receipt, meta):
            mark(registry, receipt, meta)
            clock['now'] = '2026-08-15T00:00:01+00:00'
        with mock.patch.object(T, 'iso_now', side_effect=lambda:clock['now']), \
             mock.patch.object(P.SeenRegistry, 'mark_pending', mark_then_rollback):
            result = self._run({},client=Client(responses))
        self.assertFalse(result['pagination']['coverage_complete'])

    def test_partial_pages_are_saved_pending_and_retry_before_ack(self):
        from unittest import mock
        import collect_dart as CD
        first = _filing('A1',name='원본 공시')
        unrelated = [_filing('U'+str(i),corp='77777777') for i in range(99)]
        p1 = self.response([first] + unrelated,total_page=2,total_count=101)
        partial = self.raw([p1,{'status':C.OK,'data':{'status':'013'},'noData':True}])
        self.assertFalse(partial['pagination']['coverage_complete'])
        class Store:
            def __init__(self): self.records = {}
            def segment_state(self, *a, **kw): return 'ACTIVE'
            def append_predictions(self, day, rows, **kw):
                for row in rows: self.records[row['rcept_no']] = row
                return len(rows), 0
            def read_day(self, day): return list(self.records.values())
        store = Store()
        with mock.patch.object(CD, '_dart_store', return_value=store):
            stored, acked, errors = CD._store_and_ack(partial['events'], partial['registry'], allow_ack=False)
            self.assertEqual((stored, acked, errors), (1, 0, []))
            self.assertEqual(partial['registry'].seen[first['rcept_no']]['state'], P.SeenRegistry.PENDING)
            changed = _filing('A1',name='[기재정정]원본 공시')
            correction = _filing('A2',name='[첨부정정]원본 공시')
            complete = self.raw([self.response([changed] + unrelated,total_page=2,total_count=101),
                                 self.response([correction],total_page=2,total_count=101,page_no=2)])
            self.assertTrue(complete['pagination']['coverage_complete'])
            self.assertEqual(len(complete['events']), 2)
            CD._store_and_ack(complete['events'], complete['registry'], allow_ack=True)
        self.assertEqual(store.records[first['rcept_no']]['report_name'], '[기재정정]원본 공시')
        self.assertEqual(complete['registry'].seen[first['rcept_no']]['state'], P.SeenRegistry.ACKNOWLEDGED)

    def test_full_collector_does_not_ack_an_incomplete_interval(self):
        from unittest import mock
        import collect_dart as CD
        first = _filing('A1', name='원본 공시')
        changed = _filing('A1', name='[기재정정]원본 공시')
        class Store:
            def __init__(self): self.records = {}
            def segment_state(self, *a, **kw): return 'ACTIVE'
            def append_predictions(self, day, rows, **kw):
                for row in rows: self.records[row['rcept_no']] = row
                return len(rows), 0
            def read_day(self, day): return list(self.records.values())
        class DayClient:
            has_key = True
            def __init__(self, incomplete): self.incomplete = incomplete
            def list_filings(self, **kw):
                if kw['bgn_de'] == '20260814':
                    return {'status':C.OK,'data':{'status':'013'},'noData':True}
                if self.incomplete:
                    # Two rows claim the same receipt with contradictory titles.
                    return PaginationCoverage.response([first, changed],total_count=2)
                return PaginationCoverage.response([changed])
            def efficiency_report(self, extra=None): return extra or {}
        store = Store()
        cmap = P.build_corp_map(DART_ROWS, UNIVERSE)
        with mock.patch.object(CD, '_dart_store', return_value=store), \
             mock.patch.object(P, 'DART_ROOT', self.tmp), \
             mock.patch.object(T, 'today_kst', return_value='2026-08-15'):
            partial = CD.collect(DayClient(True), cmap)
            self.assertEqual(partial['eventState'], P.EVENT_COVERAGE_INCOMPLETE)
            self.assertEqual(partial['eventsAcknowledged'], 0)
            with open(os.path.join(self.tmp, 'seen_rcept.json'), encoding='utf-8') as f:
                self.assertEqual(json.load(f)['seen'][first['rcept_no']]['state'], P.SeenRegistry.PENDING)
            complete = CD.collect(DayClient(False), cmap)
            self.assertEqual(complete['eventState'], P.EVENT_DETECTED)
            self.assertEqual(complete['eventsAcknowledged'], 1)
        self.assertEqual(store.records[first['rcept_no']]['report_name'], '[기재정정]원본 공시')

    def test_ack_requires_exact_unique_readback(self):
        from unittest import mock
        import collect_dart as CD
        result = self.raw([self.response([_filing('A1',name='정정된 공시')])])
        event = result['events'][0]
        class Store:
            def __init__(self, duplicate): self.duplicate = duplicate
            def segment_state(self, *a, **kw): return 'ACTIVE'
            def append_predictions(self, day, rows, **kw): self.rows = rows; return len(rows), 0
            def read_day(self, day):
                if self.duplicate: return self.rows + self.rows
                return [dict(self.rows[0], report_name='이전 내용')]
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), mock.patch.object(CD, '_dart_store', return_value=Store(duplicate)):
                _, acked, errors = CD._store_and_ack([event], result['registry'], allow_ack=True)
                self.assertEqual(acked, 0)
                self.assertTrue(errors)
                self.assertEqual(result['registry'].seen[event['rcept_no']]['state'], P.SeenRegistry.PENDING)

    def test_already_acknowledged_receipt_with_changed_title_is_not_silently_ignored(self):
        first = self.raw([self.response([_filing('A1',name='원본 공시')])])
        first['registry'].acknowledge_many([first['events'][0]['rcept_no']])
        first['registry'].save()
        later = self.raw([self.response([_filing('A1',name='[기재정정]원본 공시')])])
        self.assertFalse(later['pagination']['coverage_complete'])
        self.assertEqual(later['events'], [])
        self.assertEqual(later['registry'].seen[_filing('A1')['rcept_no']]['report_name'], '원본 공시')

    def test_full_coverage_marked_complete(self):
        res = self.raw([self.response([_filing("A1")])])
        self.assertTrue(res["pagination"]["coverage_complete"])
        self.assertEqual(res["pagination"]["incomplete_reasons"], [])

    def test_page_limit_marks_incomplete(self):
        pages = {i: {"status":"000", "page_no":i, "total_count":500, "total_page":5,
                     "list": [_filing(f"A{i}-{j}") for j in range(100)]} for i in range(1, 6)}
        res = self._run(pages, max_pages=2)
        self.assertFalse(res["pagination"]["coverage_complete"])
        self.assertIn(P.PAGE_LIMIT_REACHED, res["pagination"]["incomplete_reasons"])
        self.assertEqual(res["pagination"]["pages_fetched"], 2)
        self.assertEqual(res["pagination"]["total_pages_reported"], 5)

    def test_incomplete_never_reports_no_event(self):
        """전체를 못 훑었으면 '공시 없음'이라고 말하면 안 된다."""
        pages = {i: {"status":"000", "page_no":i, "total_count":500, "total_page":5,
                     "list": [_filing(f"B{i}-{j}", corp="77777777") for j in range(100)]} for i in range(1, 6)}
        res = self._run(pages, max_pages=2)
        state, reasons = P.coverage_state([], [], True, res["pagination"])
        self.assertEqual(state, P.EVENT_COVERAGE_INCOMPLETE)
        self.assertNotEqual(state, P.NO_OFFICIAL_EVENT_DETECTED)
        self.assertIn(P.PAGE_LIMIT_REACHED, reasons)

    def test_complete_and_empty_is_no_event(self):
        res = self.raw([{'status':C.OK, 'data':{'status':'013'}, 'noData':True}])
        state, reasons = P.coverage_state([], [], True, res["pagination"])
        self.assertEqual(state, P.NO_OFFICIAL_EVENT_DETECTED)
        self.assertEqual(reasons, [])

    def test_api_error_marks_incomplete(self):
        pages = {1: {"status":"000", "page_no":1, "total_count":300, "total_page":3,
                     "list": [_filing(f"A{j}") for j in range(100)]}}
        res = self._run(pages, client=FakeClient(pages, fail_from=2))
        self.assertFalse(res["pagination"]["coverage_complete"])
        state, reasons = P.coverage_state(res["events"], res["errors"], True, res["pagination"])
        self.assertEqual(state, P.EVENT_DATA_ERROR)

    def test_walks_all_pages_when_allowed(self):
        pages = {i: {"status":"000", "page_no":i, "total_count":300, "total_page":3,
                     "list": [_filing(f"P{i}-{j}") for j in range(100)]} for i in range(1, 4)}
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

    def test_exact_retry_preserves_original_ciphertext(self):
        day = '2026-08-15'
        record = _dart_event('A1')
        self.store.append_predictions(day, [record], today=day)
        path = self.store.segment_path(day)
        with open(path, 'rb') as original:
            before = original.read()
        self.assertEqual(self.store.append_predictions(day, [record], today=day), (0, 1))
        with open(path, 'rb') as original:
            self.assertEqual(original.read(), before)

    def test_changed_retry_and_mixed_batch_preserve_the_original(self):
        day = '2026-08-15'
        record = _dart_event('A1')
        self.store.append_predictions(day, [record], today=day)
        path = self.store.segment_path(day)
        with open(path, 'rb') as original:
            before = original.read()
        for field, value in (('detected_at', '2026-08-15T15:00:00Z'),
                             ('fetched_at', '2026-08-15T15:00:01Z'),
                             ('report_name', 'Changed synthetic title')):
            with self.subTest(field=field):
                changed = dict(record, **{field: value})
                with self.assertRaisesRegex(ValueError, 'DART_RECORD_CONFLICT'):
                    self.store.append_predictions(day, [_dart_event('A2'), changed], today=day)
                with open(path, 'rb') as original:
                    self.assertEqual(original.read(), before)
                self.assertEqual(self.store.read_day(day), [record])

    def test_ambiguous_stored_and_incoming_duplicates_are_never_rewritten(self):
        day = '2026-08-15'
        record = _dart_event('A1')
        path = self.store.segment_path(day)
        for body in (json.dumps(record) + '\n' + json.dumps(record) + '\n',
                     json.dumps(record).replace('"rcept_no": "A1"',
                                                '"rcept_no":"OTHER","rcept_no":"A1"') + '\n'):
            CR.write_encrypted(path, body, self.store._label(day), gzip_first=True)
            with open(path, 'rb') as original:
                before = original.read()
            with self.assertRaisesRegex(ValueError, 'DART_ARCHIVE_AMBIGUOUS'):
                self.store.append_predictions(day, [_dart_event('A2')], today=day)
            with open(path, 'rb') as original:
                self.assertEqual(original.read(), before)

    def test_incoming_duplicate_batch_does_not_create_a_segment(self):
        day = '2026-08-15'
        with self.assertRaisesRegex(ValueError, 'DART_BATCH_AMBIGUOUS'):
            self.store.append_predictions(day, [_dart_event('A1'), _dart_event('A1')], today=day)
        self.assertIsNone(self.store.existing_segment(day))

    def test_new_receipt_keeps_prior_record_content(self):
        day = '2026-08-15'
        original, new = _dart_event('A1'), _dart_event('A2')
        self.store.append_predictions(day, [original], today=day)
        self.assertEqual(self.store.append_predictions(day, [new], today=day), (1, 0))
        self.assertEqual(self.store.read_day(day), [original, new])

    def test_research_prediction_replacement_remains_separate(self):
        day = '2026-08-15'
        store = S.ResearchArchiveStore(root=os.path.join(self.tmp, 'research'),
                                       record_type=S.RECORD_RESEARCH)
        old = {'code': 'synthetic', 'date': day, 'value': 1}
        new = dict(old, value=2)
        store.append_predictions(day, [old], today=day)
        self.assertEqual(store.append_predictions(day, [new], today=day), (0, 1))
        self.assertEqual(store.read_day(day), [new])

    def test_collector_does_not_ack_a_changed_retry(self):
        from unittest import mock
        import collect_dart as collector
        day = '2026-08-15'
        record = _dart_event('A1')
        self.store.append_predictions(day, [record], today=day)
        registry = mock.Mock()
        changed = dict(record, detected_at='2026-08-15T15:00:00Z')
        with mock.patch.object(collector, '_dart_store', return_value=self.store), \
             mock.patch.object(T, 'today_kst', return_value=day):
            stored, acked, errors = collector._store_and_ack([changed], registry, allow_ack=True)
        self.assertEqual((stored, acked), (0, 0))
        self.assertTrue(errors)
        registry.mark_stored.assert_not_called()
        registry.acknowledge_many.assert_not_called()
        self.assertEqual(self.store.read_day(day), [record])


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


class CatchUpAfterOutage(unittest.TestCase):
    """2026-09-29 — 공시 목록 수집이 며칠 멈춘 뒤(9/26~9/29) 다시 돌 때 그 사이 접수일을 빠뜨리지 않는다.

    예전: 회차마다 [어제, 오늘]만 봐서 멈춘 기간의 공시를 영영 못 본 채 '확인 완료'가 됐다.
    이제: 끝까지 확인한 마지막 회차의 조회 끝날부터 오늘까지 하루씩 본다. 하루라도 못 보면 확인 완료가 아니다.
    """

    class DayClient(FakeClient):
        def __init__(self, fail_days=(), inconsistent_days=()):
            super().__init__({})
            self.fail_days = set(fail_days)
            self.inconsistent_days = set(inconsistent_days)

        def list_filings(self, **kw):
            if kw.get("bgn_de") in self.fail_days:
                self.calls.append(kw)
                return {"status": C.EVENT_DATA_ERROR, "data": None, "error": "HTTP 500"}
            self.calls.append(kw)
            if kw.get("bgn_de") in self.inconsistent_days and kw.get('page_no') == 1:
                return {'status': C.OK, 'data': {'status':'000','page_no':1,'total_page':2,
                        'total_count':2,'list':[dict(_filing('A1',corp='77777777'),rcept_dt=kw['bgn_de'],
                                                     rcept_no=kw['bgn_de']+'000001')]}}
            return {'status': C.OK, 'data': {'status':'013'}, 'noData':True}

    def setUp(self):
        import collect_dart as CD
        self.CD = CD
        self.tmp = tempfile.mkdtemp(prefix="gaeo-catchup-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.status = os.path.join(self.tmp, "collection_status.json")
        corp_map = {"mapped": {"005930": {"corp_code": "00126380", "ticker": "005930", "name": "삼성전자"}},
                    "universeSize": len(UNIVERSE)}
        from unittest import mock
        import io

        class Store:
            def maintain(self):
                return {}
        self.patches = [mock.patch.object(P, "DART_ROOT", self.tmp),
                        mock.patch.object(CD, "DART_ROOT", self.tmp),
                        mock.patch.object(CD, "STATUS_PATH", self.status),
                        mock.patch.object(CD, "BUDGET_PATH", os.path.join(self.tmp, "budget.json")),
                        mock.patch.object(P, "load_corp_map", return_value=corp_map),
                        mock.patch.object(P, "load_universe", return_value=UNIVERSE),
                        mock.patch.object(CD, "_dart_store", return_value=Store()),
                        mock.patch.object(T, "today_kst", return_value="2026-09-29"),
                        mock.patch("sys.argv", ["collect_dart.py"]),
                        mock.patch("sys.stdout", new=io.StringIO())]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def run_main(self, client):
        from unittest import mock
        with mock.patch.object(self.CD.dart_client, "DartClient", return_value=client):
            self.assertEqual(self.CD.main(), 0)
        with open(self.status, encoding="utf-8") as f:
            return json.load(f)

    def test_따라잡을_날짜는_가장_오래된_미확인_날부터_한_회차에_14일까지다(self):
        days, behind = self.CD.catchup_days("2026-09-29", None)
        self.assertEqual((days, behind), (["2026-09-28", "2026-09-29"], 0))          # 예전과 같은 [어제, 오늘]
        days, behind = self.CD.catchup_days("2026-09-29", "2026-09-26")
        self.assertEqual((days, behind), (["2026-09-26", "2026-09-27", "2026-09-28", "2026-09-29"], 0))
        days, behind = self.CD.catchup_days("2026-09-29", "2026-09-29")
        self.assertEqual(days, ["2026-09-28", "2026-09-29"])                           # 어제는 항상 다시 본다
        days, behind = self.CD.catchup_days("2026-09-29", "2026-09-01")
        self.assertEqual((days[0], days[-1], len(days)), ("2026-09-01", "2026-09-14", self.CD.MAX_CATCHUP_DAYS))
        self.assertEqual(behind, 15, "최근 14일만 보고 오래된 날을 버리지 않는다 — 가장 오래된 날부터")

    def test_멈춘_뒤_첫_회차는_빠진_날을_하루씩_다시_보고_확인_완료를_옮긴다(self):
        # 2026-09-29 이전 모양의 상태 파일(lastComplete 칸 없음) — 9/25 15:41Z 에 [9/25, 9/26] 을 끝까지 봤다.
        with open(self.status, "w", encoding="utf-8") as f:
            json.dump({"status": "OK", "eventState": P.NO_OFFICIAL_EVENT_DETECTED,
                       "finishedAt": "2026-09-25T15:41:33.305198+00:00",
                       "queryWindow": {"start": "2026-09-25", "end": "2026-09-26"}}, f)
        client = self.DayClient()
        status = self.run_main(client)
        self.assertEqual([(c["bgn_de"], c["end_de"]) for c in client.calls],
                         [(d, d) for d in ("20260926", "20260927", "20260928", "20260929")])
        self.assertEqual(status["queryWindow"], {"start": "2026-09-26", "end": "2026-09-29", "days": 4})
        self.assertEqual(status["eventState"], P.NO_OFFICIAL_EVENT_DETECTED)
        self.assertEqual(status["lastComplete"], {"finishedAt": status["finishedAt"],
                                                  "windowStart": "2026-09-26", "windowEnd": "2026-09-29",
                                                  "coveredUntil": P.covered_until(status["finishedAt"], "2026-09-29")})

    def test_하루라도_못_보면_확인_완료가_아니고_앞의_기록을_그대로_넘긴다(self):
        kept = {"finishedAt": "2026-09-25T15:41:33.305198+00:00", "windowStart": "2026-09-25", "windowEnd": "2026-09-26"}
        with open(self.status, "w", encoding="utf-8") as f:
            json.dump({"status": "OK", "eventState": P.NO_OFFICIAL_EVENT_DETECTED, "lastComplete": kept}, f)
        client = self.DayClient(fail_days={"20260927"})
        status = self.run_main(client)
        self.assertEqual(status["eventState"], P.EVENT_DATA_ERROR)     # 실패를 '공시 없음'으로 바꾸지 않는다
        self.assertEqual(status["lastComplete"], dict(kept, coveredUntil=P.covered_until(kept["finishedAt"], kept["windowEnd"])))
        self.assertEqual([e.get("day") for e in status["errors"]], ["2026-09-27"])
        self.assertEqual(len(client.calls), 4, "다른 날은 계속 본다 — 다음 회차가 다시 이어받는다")

    def test_불일치_페이지는_마지막_확인_시각을_옮기지_않고_다음에_재조회한다(self):
        kept = {"finishedAt":"2026-09-25T15:41:33.305198+00:00", "windowStart":"2026-09-25", "windowEnd":"2026-09-26"}
        with open(self.status, "w", encoding="utf-8") as f:
            json.dump({"status":"OK", "eventState":P.NO_OFFICIAL_EVENT_DETECTED, "lastComplete":kept},f)
        bad = self.DayClient(inconsistent_days={"20260927"})
        status = self.run_main(bad)
        self.assertEqual(status['eventState'], P.EVENT_COVERAGE_INCOMPLETE)
        self.assertEqual(status['lastComplete']['windowEnd'], '2026-09-26')
        retried = self.DayClient()
        recovered = self.run_main(retried)
        self.assertIn('20260927', [call['bgn_de'] for call in retried.calls])
        self.assertEqual(recovered['eventState'], P.NO_OFFICIAL_EVENT_DETECTED)
        self.assertEqual(recovered['lastComplete']['windowEnd'], '2026-09-29')

    def test_unexpected_list_exception_still_saves_attempted_budget(self):
        class ExplodingClient(self.DayClient):
            def list_filings(self, **kw):
                self.calls.append(kw)
                raise RuntimeError('unexpected response failure')
        status = self.run_main(ExplodingClient())
        self.assertEqual(status['eventState'], P.EVENT_DATA_ERROR)
        with open(os.path.join(self.tmp, 'budget.json'), encoding='utf-8') as f:
            saved = json.load(f)
        self.assertEqual(saved['counts']['list'], 1)

    def test_failed_mapping_early_return_still_saves_attempted_budget(self):
        from unittest import mock
        client = self.DayClient()
        client.corp_code_zip = lambda: {'status': C.EVENT_DATA_ERROR, 'data': None, 'error': 'offline'}
        with mock.patch.object(P, 'load_corp_map', return_value=None):
            status = self.run_main(client)
        self.assertEqual(status['eventState'], P.EVENT_COVERAGE_INCOMPLETE)
        with open(os.path.join(self.tmp, 'budget.json'), encoding='utf-8') as f:
            saved = json.load(f)
        self.assertEqual(saved['counts']['mapping'], 1)

    def test_unexpected_mapping_exception_still_saves_attempted_budget(self):
        from unittest import mock
        client = self.DayClient()
        def fail():
            raise RuntimeError('unexpected response failure')
        client.corp_code_zip = fail
        with mock.patch.object(P, 'load_corp_map', return_value=None):
            status = self.run_main(client)
        self.assertEqual(status['eventState'], P.EVENT_DATA_ERROR)
        with open(os.path.join(self.tmp, 'budget.json'), encoding='utf-8') as f:
            saved = json.load(f)
        self.assertEqual(saved['counts']['mapping'], 1)

    def test_interruption_saves_attempt_and_marks_status_unavailable(self):
        from unittest import mock
        class InterruptedClient(self.DayClient):
            def list_filings(self, **kw):
                self.calls.append(kw)
                raise SystemExit(143)
        with mock.patch.object(self.CD.dart_client, 'DartClient', return_value=InterruptedClient()):
            with self.assertRaises(SystemExit):
                self.CD.main()
        with open(os.path.join(self.tmp, 'budget.json'), encoding='utf-8') as f:
            saved = json.load(f)
        with open(self.status, encoding='utf-8') as f:
            status = json.load(f)
        self.assertEqual(saved['counts']['list'], 1)
        self.assertEqual(status['eventState'], P.EVENT_DATA_ERROR)
        self.assertEqual(status['error'], 'COLLECTION_INTERRUPTED')

    def test_sigterm_during_list_request_persists_reserved_attempt(self):
        script = '''import os, signal, sys
from unittest import mock
import collect_dart as C, dart_pipeline as P, dart_time as T
root = sys.argv[1]
C.STATUS_PATH = os.path.join(root, "signal-status.json")
C.BUDGET_PATH = os.path.join(root, "signal-budget.json")
P.DART_ROOT = root
class Client:
    has_key = True
    def list_filings(self, **kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
client = Client()
mapping = {"mapped": {"000001": {"corp_code": "00126380", "ticker": "000001"}}, "universeSize": 1}
with mock.patch.object(C.dart_client, "DartClient", return_value=client), \\
     mock.patch.object(P, "load_corp_map", return_value=mapping), \\
     mock.patch.object(P, "load_universe", return_value={"000001": {}}), \\
     mock.patch.object(T, "today_kst", return_value="2026-09-29"), \\
     mock.patch.object(sys, "argv", ["collect_dart.py"]):
    C.main()
'''
        result = subprocess.run([sys.executable, '-c', script, self.tmp], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 128 + signal.SIGTERM, result.stderr.decode('utf-8'))
        with open(os.path.join(self.tmp, 'signal-budget.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['counts']['list'], 1)
        with open(os.path.join(self.tmp, 'signal-status.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['error'], 'COLLECTION_INTERRUPTED')

    def test_budget_save_error_never_exposes_exception_text(self):
        from unittest import mock
        with mock.patch.object(dart_budget.DailyBudget, 'save', side_effect=OSError('sensitive-url-or-token')):
            status = self.run_main(self.DayClient())
        self.assertEqual(status.get('budgetSaveError'), 'BUDGET_SAVE_FAILED')
        self.assertNotIn('sensitive-url-or-token', json.dumps(status))

    def test_damaged_seen_registry_is_preserved_and_no_request_is_sent(self):
        path = os.path.join(self.tmp, 'seen_rcept.json')
        damaged = (b'{"seen":', b'[]', b'{"seen": []}',
                   b'{"seen": {"one": null}}', b'{"seen": {}, "count": 2}',
                   b'{"schemaVersion":"dart_seen_v2","updatedAt":"2026-09-29T00:00:00Z","count":1,"seen":{'
                   b'"20260901000001":{"state":"PENDING","ticker":"000001","report_name":"x",'
                   b'"detected_at":"2026-09-28T00:00:00Z"},'
                   b'"20260901000001":{"state":"PENDING","ticker":"000001","report_name":"x",'
                   b'"detected_at":"2026-09-28T00:00:00Z"}}}')
        for raw in damaged:
            with self.subTest(raw=raw):
                with open(path, 'wb') as f:
                    f.write(raw)
                client = self.DayClient()
                status = self.run_main(client)
                with open(path, 'rb') as f:
                    self.assertEqual(f.read(), raw)
                self.assertEqual(client.calls, [])
                self.assertEqual(status['eventState'], P.EVENT_DATA_ERROR)

    def test_corrupt_budget_reports_unknown_without_touching_seen_or_sending(self):
        budget_path = os.path.join(self.tmp, 'budget.json')
        seen_path = os.path.join(self.tmp, 'seen_rcept.json')
        with open(budget_path, 'w', encoding='utf-8') as f:
            f.write('{"damaged":')
        seen = '{"schemaVersion":"dart_seen_v2","updatedAt":"2026-09-29T00:00:00+00:00","count":0,"seen":{}}'
        with open(seen_path, 'w', encoding='utf-8') as f:
            f.write(seen)
        client = self.DayClient()
        status = self.run_main(client)
        self.assertEqual(client.calls, [])
        self.assertEqual(status['eventState'], P.EVENT_COVERAGE_INCOMPLETE)
        self.assertIn('DART_BUDGET_UNVERIFIED', status['coverageReasons'])
        self.assertEqual(status['budgetSaveError'], 'BUDGET_SAVE_FAILED')
        with open(budget_path, encoding='utf-8') as f:
            self.assertEqual(f.read(), '{"damaged":')
        with open(seen_path, encoding='utf-8') as f:
            self.assertEqual(f.read(), seen)

    def test_14일보다_오래_밀리면_회차마다_오래된_날부터_이어_보고_오늘까지_따라잡는다(self):
        kept = {"finishedAt": "2026-09-01T00:00:00+00:00", "windowStart": "2026-08-31", "windowEnd": "2026-09-01"}
        with open(self.status, "w", encoding="utf-8") as f:
            json.dump({"status": "OK", "eventState": P.NO_OFFICIAL_EVENT_DETECTED, "lastComplete": kept}, f)
        chunks = []
        for expected_end, behind in (("2026-09-14", 15), ("2026-09-27", 2), ("2026-09-29", 0)):
            client = self.DayClient()
            status = self.run_main(client)
            days = [c["bgn_de"] for c in client.calls]
            chunks.append((days[0], days[-1]))
            self.assertEqual(status["eventState"], P.NO_OFFICIAL_EVENT_DETECTED)     # 끝까지 본 구간은 확인 완료다
            self.assertEqual(status["lastComplete"]["windowEnd"], expected_end)       # 오늘로 건너뛰지 않는다
            self.assertEqual(status["catchUp"]["behindDays"], behind)
            self.assertEqual(status["catchUp"]["state"], P.CATCHUP_IN_PROGRESS if behind else P.CAUGHT_UP)
        self.assertEqual(chunks, [("20260901", "20260914"), ("20260914", "20260927"), ("20260927", "20260929")])

    def test_따라잡는_중에는_확인_시각이_끝날_다음_날_0시를_넘지_않는다(self):
        # 오늘 확인했어도 9/14 까지만 봤다면 '9/15 0시(KST)까지 접수분'만 확인한 것이다 — 공시 연구가 신선해 보이면 안 된다.
        self.assertEqual(P.covered_until("2026-09-29T00:05:00+00:00", "2026-09-14"), "2026-09-14T15:00:00+00:00")
        self.assertEqual(P.covered_until("2026-09-29T00:05:00+00:00", "2026-09-29"), "2026-09-29T00:05:00+00:00")
        legacy = P.last_complete({"status": "OK", "eventState": P.NO_OFFICIAL_EVENT_DETECTED,
                                  "finishedAt": "2026-09-25T15:41:33.305198+00:00",
                                  "queryWindow": {"start": "2026-09-25", "end": "2026-09-26"}})
        self.assertEqual(legacy["coveredUntil"], "2026-09-25T15:41:33.305198+00:00")

    def test_확인한_기록이_없는_옛_실패_상태는_확인_완료로_치지_않는다(self):
        self.assertIsNone(P.last_complete({"status": "EVENT_DATA_ERROR", "eventState": P.EVENT_DATA_ERROR,
                                           "finishedAt": "2026-09-29T00:00:00+00:00",
                                           "queryWindow": {"start": "2026-09-28", "end": "2026-09-29"}}))
        self.assertIsNone(P.last_complete({"lastComplete": None, "status": "OK",
                                           "eventState": P.NO_OFFICIAL_EVENT_DETECTED}))
        self.assertIsNone(P.last_complete({"lastComplete": {"finishedAt": "not-a-time", "windowEnd": "2026-09-29"}}))


# ── 1. v1.x 동결 유지 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=1)
