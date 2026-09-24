#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증거 수집기 불변식 — 실패가 0건으로 바뀌지 않는지, 대조가 실제로 되는지.

네트워크를 쓰지 않는다. 가짜 응답으로 수집기의 판단만 시험한다.
실제 수집이 됐다는 증거가 아니다 — 그것은 워크플로 실행 기록으로만 말한다.
"""
import unittest

import collect_corporate_action_evidence as collector
import dart_client


class FakeClient:
    def __init__(self, pages):
        self.pages = pages          # [{'status':..,'data':..,'noData':..}, ...]
        self.calls = 0

    def list_issuer_filings(self, corp_code, bgn_de, end_de, page_no=1, **kw):
        self.calls += 1
        return self.pages[min(page_no - 1, len(self.pages) - 1)]


def page(rows, total_page=1, total_count=None, status='000'):
    return {'status': dart_client.OK, 'error': None,
            'data': {'status': status, 'total_page': total_page,
                     'total_count': len(rows) if total_count is None else total_count,
                     'list': rows}}


def filing(rcept, title, stock='005930'):
    return {'rcept_no': rcept, 'report_nm': title, 'stock_code': stock, 'rcept_dt': '20260901'}


def run(client, budget=50):
    return collector.collect_one(client, '005930', '00126380', '20250911', '20260911', {'left': budget})


class CollectorTests(unittest.TestCase):
    def test_price_comparison_scope_is_additive_without_extra_requests(self):
        client = FakeClient([page([filing('20260901000001', '현금·현물배당 결정'),
                                  filing('20260901000002', '주식병합 안내')])])
        out = run(client)
        self.assertEqual(out['comparisonScopeVersion'], 'price-comparison-v1')
        self.assertEqual(len(out['comparisonFindings']), 2)
        self.assertEqual(out['findings'], [])
        self.assertEqual(out['unresolvedHistorical'], 0)
        self.assertEqual(client.calls, 1)

    def test_a_clean_company_reports_zero_with_full_reconciliation(self):
        out = run(FakeClient([page([filing('R1', '현금·현물배당 결정')])]))
        self.assertTrue(out['ok'])
        self.assertEqual((out['pagesExpected'], out['pagesCollected']), (1, 1))
        self.assertEqual((out['totalCount'], out['collectedIds']), (1, ['R1']))
        self.assertEqual(out['findings'], [])            # 현금배당은 주식 수를 바꾸지 않는다
        self.assertEqual(out['unresolvedHistorical'], 0)

    def test_a_relevant_filing_is_reported_and_counted_unresolved(self):
        out = run(FakeClient([page([filing('R2', '주요사항보고서(무상증자결정)')])]))
        self.assertEqual([f['id'] for f in out['findings']], ['R2'])
        self.assertEqual(out['unresolvedHistorical'], 1)
        self.assertEqual(out['eventCounts']['openSelf'], 1)

    def test_documents_are_not_counted_as_events(self):
        # 정정은 같은 사건이다. 공시 3건이 사건 1건으로 세어져야 한다.
        rows = [filing('R1', '주요사항보고서(감자결정)'),
                filing('R2', '[기재정정]주요사항보고서(감자결정)'),
                filing('R3', '[첨부정정]주요사항보고서(감자결정)')]
        out = run(FakeClient([page(rows)]))
        self.assertEqual(out['eventCounts'], {'openSelf': 1, 'subsidiary': 0, 'documents': 3,
                                              'needsDocument': 0, 'companyDoneAwaitingExchange': 0,
                                              'fullyResolved': 0, 'events': 1})
        self.assertEqual(out['unresolvedHistorical'], 1)

    def test_a_subsidiary_filing_does_not_block_this_stock(self):
        out = run(FakeClient([page([filing('R9', '유상증자결정(종속회사의주요경영사항)')])]))
        self.assertEqual(out['unresolvedHistorical'], 0)
        self.assertEqual(out['eventCounts']['subsidiary'], 1)
        self.assertEqual(len(out['findings']), 1)          # 발견은 그대로 보존한다

    def test_a_title_needing_the_document_is_not_counted_as_interpreted(self):
        out = run(FakeClient([page([filing('R8', '매매거래정지및정지해제(중요내용공시)')])]))
        self.assertGreaterEqual(out['uninterpreted'], 1)
        self.assertTrue(out['listClassified'])
        self.assertFalse(out['documentsInterpreted'])

    def test_no_data_is_zero_only_for_that_query(self):
        empty = {'status': dart_client.OK, 'error': None, 'noData': True,
                 'data': {'status': '013'}}
        out = run(FakeClient([empty]))
        self.assertTrue(out['ok'])
        self.assertEqual(out['apiStatus'], '013')
        self.assertEqual((out['totalCount'], out['pagesExpected'], out['pagesCollected']), (0, 1, 1))

    def test_a_transport_failure_is_never_zero(self):
        dead = {'status': dart_client.DART_UNREACHABLE, 'data': None, 'error': 'x'}
        out = run(FakeClient([dead]))
        self.assertFalse(out['ok'])
        self.assertEqual(out['error'], dart_client.DART_UNREACHABLE)
        self.assertIsNone(out['totalCount'])
        self.assertEqual(out['collectedIds'], [])

    def test_an_api_error_is_never_zero(self):
        bad = {'status': dart_client.EVENT_DATA_ERROR, 'data': {'status': '020'}, 'error': 'x'}
        out = run(FakeClient([bad]))
        self.assertFalse(out['ok'])
        self.assertEqual(out['apiStatus'], '020')

    def test_an_unexpected_shape_is_never_zero(self):
        odd = {'status': dart_client.OK, 'error': None, 'data': {'status': '000', 'rows': []}}
        out = run(FakeClient([odd]))
        self.assertFalse(out['ok'])
        self.assertEqual(out['error'], 'RESPONSE_SHAPE_UNEXPECTED')

    def test_every_page_is_collected_before_completion(self):
        client = FakeClient([page([filing('R' + i, '기타 안내')], total_page=3, total_count=3)
                             for i in ('1', '2', '3')])
        out = run(client)
        self.assertEqual((out['pagesExpected'], out['pagesCollected']), (3, 3))
        self.assertEqual(client.calls, 3)

    def test_a_budget_stop_is_reported_not_completed(self):
        client = FakeClient([page([filing('R1', '기타')], total_page=5, total_count=5)])
        out = collector.collect_one(client, '005930', '00126380', '20250911', '20260911', {'left': 2})
        self.assertFalse(out['ok'])
        self.assertEqual(out['error'], 'REQUEST_BUDGET_EXHAUSTED')

    def test_rows_for_another_stock_are_left_uninterpreted(self):
        out = run(FakeClient([page([filing('R1', '합병 결정', stock='000660')])]))
        self.assertEqual(out['uninterpreted'], 1)
        self.assertEqual(out['findings'], [])
        self.assertEqual(out['collectedIds'], [])

    def test_the_evidence_carries_a_way_back_to_the_real_response(self):
        out = run(FakeClient([page([filing('R1', '기타')])]))
        self.assertTrue(out['responseRef'].startswith('sha256:'))
        self.assertEqual(out['identityBasis'], 'corp_code_map')
        self.assertEqual(out['source'], 'OPENDART_API')
        self.assertLess(out['queriedAt'], out['expiresAt'])


class DueTargetMode(unittest.TestCase):
    """채점 대상 중심 모드(2026-09-16) — 파일의 종목만 보고, 커서는 건드리지 않고, 빈 파일은 0종목이다."""

    def test_파일은_6자리_코드만_순서대로_중복없이_읽는다(self):
        import os, tempfile
        import due_targets
        path = os.path.join(tempfile.mkdtemp(), 'due.txt')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('# 머리말\n005930\n000660 # 주석\n\nabcdef\n005930\n12345\n035720\n')
        self.assertEqual(due_targets.read_tickers_file(path), ['005930', '000660', '035720'])
        self.assertEqual(due_targets.read_tickers_file(path + '.none'), [])

    def test_기본_모드는_예전과_같이_커서부터_순회한다(self):
        import due_targets
        got = due_targets.select_targets(['000010', '000020', '000030'], '000010', 2)
        self.assertEqual(got['todo'], ['000020', '000030'])
        self.assertEqual(got['mode'], due_targets.MODE_ROTATION)
        wrap = due_targets.select_targets(['000010', '000020', '000030'], '000030', 2)
        self.assertEqual(wrap['todo'], ['000010', '000020'])

    def test_파일_모드는_커서를_무시하고_유니버스에_있는_것만_상한까지_본다(self):
        import due_targets
        got = due_targets.select_targets(['000010', '000020', '000030'], '000020', 2,
                                         ['000030', '999999', '000010', '000020'])
        self.assertEqual(got['todo'], ['000030', '000010'])       # 파일 순서 · cap 2
        self.assertEqual(got['mode'], due_targets.MODE_TICKERS_FILE)
        self.assertEqual(got['notInUniverse'], ['999999'])
        self.assertEqual(got['requested'], 4)

    def test_빈_파일은_0종목이고_전체_순회로_되돌아가지_않는다(self):
        import due_targets
        got = due_targets.select_targets(['000010', '000020'], '', 50, [])
        self.assertEqual(got['todo'], [])
        self.assertEqual(got['mode'], due_targets.MODE_TICKERS_FILE)

    def test_수집기_main이_파일_모드에서_커서를_보존하고_대상만_본다(self):
        """실제 main() 을 임시 폴더에서 돈다 — 네트워크 0(클라이언트·수집 함수를 대역으로)."""
        import json, os, tempfile
        from unittest import mock
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, 'config'))
        with open(os.path.join(tmp, collector.UNIVERSE_FILE), 'w', encoding='utf-8') as fh:
            json.dump({'codes': ['000010', '000020', '000030', '000040']}, fh)
        os.makedirs(os.path.join(tmp, collector.OUT_DIR))
        with open(os.path.join(tmp, collector.OUT_FILE), 'w', encoding='utf-8') as fh:
            json.dump({'cursor': '000020', 'evidence': {'000010': {'ok': True, 'findings': [],
                                                                    'unresolvedHistorical': 0}}}, fh)
        due = os.path.join(tmp, 'due.txt')
        with open(due, 'w', encoding='utf-8') as fh:
            fh.write('000040\n000010\n999999\n')

        class Client:
            def corp_code_zip(self): return {'status': dart_client.OK, 'data': b''}
            def efficiency_report(self, extra=None): return {}
        seen = []
        def fake_collect(client, ticker, corp_code, bgn, end, budget):
            seen.append(ticker); budget['left'] -= 1
            return {'ok': True, 'findings': [], 'unresolvedHistorical': 0, 'error': None}
        mapped = {c: {'corp_code': 'X' + c} for c in ('000010', '000020', '000030', '000040')}
        cwd = os.getcwd(); os.chdir(tmp)
        try:
            with mock.patch.object(collector.dart_client, 'DartClient', Client), \
                 mock.patch.object(collector.dart_pipeline, 'parse_corp_code_zip', lambda data: []), \
                 mock.patch.object(collector.dart_pipeline, 'build_corp_map', lambda rows, uni: {'mapped': mapped}), \
                 mock.patch.object(collector, 'collect_one', fake_collect), \
                 mock.patch('sys.stdout', new=__import__('io').StringIO()):
                code = collector.main(['--tickers-file', due, '--tickers', '50', '--requests', '10'])
            self.assertEqual(code, 0)
            saved = json.load(open(collector.OUT_FILE, encoding='utf-8'))
        finally:
            os.chdir(cwd)
        self.assertEqual(seen, ['000040', '000010'])            # 파일 순서 · 유니버스 밖 999999 제외
        self.assertEqual(saved['cursor'], '000020', '파일 모드가 전체 순회의 커서를 옮겼다')
        self.assertEqual(saved['targetMode'], 'tickers_file')
        self.assertEqual(saved['notInUniverse'], 1)
        self.assertEqual(saved['attempted'], 2)
        self.assertEqual(saved['succeeded'], 2)
        self.assertIn('000010', saved['evidence'])               # 이전 회차 증거는 덮어써 갱신


class CorporateBudget(unittest.TestCase):
    def test_shared_daily_limit_stops_before_any_api_call(self):
        import tempfile, os, json, io
        import dart_budget
        from unittest import mock
        with tempfile.TemporaryDirectory() as root:
            budget_path = os.path.join(root, 'budget.json')
            daily = dart_budget.DailyBudget(budget_path)
            daily.spend('list', daily.hard_limit)
            daily.save()
            with mock.patch.object(collector, 'BUDGET_FILE', budget_path, create=True), \
                 mock.patch.object(collector.dart_client, 'DartClient') as client, \
                 mock.patch('sys.stdout', new=io.StringIO()):
                client.return_value.corp_code_zip.return_value = {'status': dart_client.DART_UNREACHABLE}
                result = collector.main(['--tickers', '40', '--requests', '300'])
            self.assertEqual(result, 2)
            client.assert_not_called()

    def test_each_page_uses_the_existing_shared_budget(self):
        """페이지마다 공유 예산을 깎고, 몫이 바닥나면 그 자리에서 멈춘다.

        ⚠️ 2026-09-22 경계 변경: 예전에는 `hard_limit - 1` 로 **하드 상한 직전**을 썼다.
           지금은 하드 상한보다 `dart_budget.DEFERRABLE_RESERVE`(필수 경로 몫)가 **먼저** 막는다.
        ⚠️ 2026-09-23 경계 재변경: 몫은 하드 상한이 아니라 **재무가 끊기는 선(soft budget)** 기준이다
           (`dart_budget.deferrable_cutoff()` = 6,500). 재무(8,000)보다 늦게 물러나던 역전을 고쳤다.
           시험의 뜻(페이지마다 공유 예산을 쓴다 · 바닥나면 멈춘다)은 그대로 두고 경계만 옮겼다.
        """
        import tempfile, os
        import dart_budget
        with tempfile.TemporaryDirectory() as root:
            daily = dart_budget.DailyBudget(os.path.join(root, 'budget.json'))
            daily.spend('list', dart_budget.deferrable_cutoff() - 1)
            client = FakeClient([page([filing('R1', '기타')], total_page=2, total_count=2)])
            out = collector.collect_one(client, '005930', '00126380', '20250911', '20260911',
                                        {'left': 300, 'daily': daily})
            self.assertFalse(out['ok'])
            self.assertEqual(out['error'], 'DART_BUDGET_EXCEEDED')
            self.assertEqual(client.calls, 1)        # 1건은 썼다(몫 위였다)
            self.assertEqual(daily.total, dart_budget.deferrable_cutoff())
            # 필수 경로(오늘의 공시)와 재무는 같은 순간에도 계속 허용돼야 한다 — 이게 몫의 목적이다.
            self.assertTrue(daily.allow('list'))
            self.assertTrue(daily.allow('financial'))
            self.assertFalse(daily.allow_for_deferrable('list'))

class FullRefreshContract(unittest.TestCase):
    def exercise(self, when, requests=10, shared_remaining=10000):
        import tempfile, os, io, json, zipfile, datetime
        from unittest import mock
        import dart_budget
        with tempfile.TemporaryDirectory() as root:
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, 'w') as archive:
                archive.writestr('CORPCODE.xml', '<result><list><corp_code>00126380</corp_code><corp_name>Fixture</corp_name><stock_code>005930</stock_code></list></result>')
            client = FakeClient([{'status': dart_client.OK, 'noData': True, 'data': {'status': '013'}}])
            client.corp_code_zip = lambda: {'status': dart_client.OK, 'data': raw.getvalue()}
            client.efficiency_report = lambda: {}
            budget_path = os.path.join(root, 'budget.json')
            daily = dart_budget.DailyBudget(budget_path)
            daily.spend('list', daily.hard_limit - shared_remaining)
            daily.save()
            os.makedirs(os.path.join(root, 'config'))
            with open(os.path.join(root, collector.UNIVERSE_FILE), 'w') as handle:
                json.dump({'codes': ['005930']}, handle)
            old = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(collector, 'BUDGET_FILE', budget_path), \
                     mock.patch.object(collector.dart_client, 'DartClient', return_value=client), \
                     mock.patch.object(collector, '_today', return_value=when), \
                     mock.patch('sys.stdout', new=io.StringIO()):
                    code = collector.main(['--tickers', '4000', '--requests', str(requests), '--require-complete'])
                # 시작 전에 거절되면 산출물 파일이 아예 없다 — 없음을 없음으로 돌려준다(빈 dict 로 위조하지 않는다).
                evidence = None
                if os.path.exists(collector.OUT_FILE):
                    with open(collector.OUT_FILE) as handle:
                        evidence = json.load(handle)
                with open(budget_path) as handle:
                    spent = json.load(handle)['counts']
            finally:
                os.chdir(old)
            return code, evidence, spent, client.calls

    def test_preopen_query_includes_the_actual_korean_date(self):
        import datetime
        # Real date conversion, no future timestamp and no synthetic freshness.
        when = datetime.datetime(2026, 9, 21, 22, 10, tzinfo=datetime.timezone.utc)
        code, saved, spent, calls = self.exercise(when)
        self.assertEqual(code, 0)
        record = saved['evidence']['005930']
        self.assertEqual(record['to'], '20260922')
        self.assertLessEqual(record['from'], '20250921')
        self.assertEqual(record['queriedAt'], when.isoformat())
        self.assertEqual(record['expiresAt'], (when + datetime.timedelta(hours=20)).isoformat())
        self.assertEqual((spent['mapping'], spent['list'], calls), (1, 1, 1))

    def test_mapping_alone_cannot_report_complete_refresh(self):
        import datetime
        when = datetime.datetime(2026, 9, 22, 8, 10, tzinfo=datetime.timezone.utc)
        code, saved, spent, calls = self.exercise(when, requests=1)
        self.assertEqual(code, 2)
        self.assertEqual((saved['succeeded'], calls, spent['mapping']), (0, 0, 1))
        self.assertFalse(saved['evidence']['005930']['ok'])

    def test_existing_shared_usage_is_preserved(self):
        """공유 예산이 거의 다 찼으면 새 목록 요청을 하지 않고, 기존 사용량을 그대로 보존한다.

        ⚠️ 2026-09-22 경계 변경: `shared_remaining=1`(하드 상한 직전)이 아니라 몫이 경계다.
        ⚠️ 2026-09-23: 몫은 soft budget 기준(`deferrable_cutoff()` = 6,500)이다 — 누적 6,499 에서 시작하면
           mapping 1건까지는 가고(6,500 도달) 목록 요청은 0건이다.
        """
        import datetime
        import dart_budget
        when = datetime.datetime(2026, 9, 22, 8, 10, tzinfo=datetime.timezone.utc)
        spent_before = dart_budget.deferrable_cutoff() - 1
        code, saved, spent, calls = self.exercise(when, shared_remaining=10000 - spent_before)
        self.assertEqual(code, 2)
        self.assertEqual(sum(spent.values()), spent_before + 1)        # 기존 사용량 + mapping 1건
        self.assertEqual(spent['list'], spent_before)                  # 목록은 한 건도 더 안 썼다
        self.assertEqual(calls, 0)

    def test_deferrable_reserve_refuses_before_the_run_starts(self):
        """남은 예산이 필수 경로 몫뿐이면 **시작조차 하지 않는다**(2026-09-22 신설).

        왜: 증거 수집기는 요청을 `list`(ESSENTIAL)로 센다. 그래서 soft budget 이 이것을 전혀
        막지 못했고, 정작 굶는 것은 그날 놓치면 영구 결손인 **오늘의 공시**와 **재무**였다.
        오늘 못 받은 증거는 내일 받을 수 있다 — 그래서 대기 가능한 쪽이 물러난다.
        """
        import datetime
        import dart_budget
        when = datetime.datetime(2026, 9, 22, 8, 10, tzinfo=datetime.timezone.utc)
        cutoff = dart_budget.deferrable_cutoff()             # 2026-09-23: soft budget 기준 6,500
        code, saved, spent, calls = self.exercise(when, shared_remaining=10000 - cutoff)
        self.assertEqual(code, 2)
        self.assertEqual(calls, 0)
        self.assertEqual(spent['mapping'], 0, 'mapping 조차 쓰지 않아야 한다 — 시작 전에 물러난다')
        self.assertIsNone(saved, '산출물을 쓰지 않는다')
        self.assertEqual(sum(spent.values()), cutoff)


class DeferrableReserveContract(unittest.TestCase):
    """`dart_budget` 의 몫 계약 — 급한 것과 미룰 수 있는 것을 구분한다 (2026-09-22 신설)."""

    def budget(self, spent):
        import tempfile, os
        import dart_budget
        self._tmp = getattr(self, '_tmp', None) or tempfile.mkdtemp()
        b = dart_budget.DailyBudget(os.path.join(self._tmp, f'b{spent}.json'))
        b.spend('list', spent)
        return b

    def test_reserve_is_smaller_than_the_soft_budget(self):
        import dart_budget
        self.assertLess(dart_budget.DEFERRABLE_RESERVE, dart_budget.SOFT_BUDGET)
        self.assertLess(dart_budget.OBSERVATION_NOTICE, dart_budget.SOFT_BUDGET)
        self.assertGreater(dart_budget.OBSERVATION_NOTICE, dart_budget.NORMAL_TARGET_PER_DAY)

    def test_essential_path_is_never_blocked_by_the_reserve(self):
        """오늘의 공시(`list`)·매핑은 몫 안에서도 계속 허용된다 — 몫은 그들을 위한 것이다."""
        import dart_budget
        b = self.budget(dart_budget.DAILY_HARD_LIMIT - 1)
        for kind in dart_budget.ESSENTIAL:
            self.assertTrue(b.allow(kind), kind)
            self.assertFalse(b.allow_for_deferrable(kind), kind)

    def test_deferrable_stops_at_the_reserve_line(self):
        """2026-09-23: 몫의 기준선은 하드 상한이 아니라 재무가 끊기는 soft budget 이다(`deferrable_cutoff()`)."""
        import dart_budget
        cutoff = dart_budget.deferrable_cutoff()
        self.assertEqual(cutoff, dart_budget.SOFT_BUDGET - dart_budget.DEFERRABLE_RESERVE)
        just_above = self.budget(cutoff - 1)
        exactly_at = self.budget(cutoff)
        self.assertTrue(just_above.allow_for_deferrable('list'))
        self.assertFalse(exactly_at.allow_for_deferrable('list'))
        self.assertTrue(exactly_at.allow('financial'), '대기 가능한 작업이 물러난 자리에서 재무는 열려 있다')

    def test_hard_limit_still_stops_everything(self):
        import dart_budget
        b = self.budget(dart_budget.DAILY_HARD_LIMIT)
        self.assertFalse(b.allow('list'))
        self.assertFalse(b.allow_for_deferrable('list'))

    def test_overlapping_processes_do_not_erase_each_other(self):
        """CAE-2 (2026-09-23) — 겹쳐 돈 두 수집기 중 나중에 저장하는 쪽이 먼저 것을 지우고 있었다."""
        import tempfile, os, json
        import dart_budget
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'budget.json')
            a = dart_budget.DailyBudget(path)      # 07:10 증거 수집 — 오래 돈다
            b = dart_budget.DailyBudget(path)      # 09:00 오늘의 공시 — 먼저 끝난다
            a.spend('list', 2958)
            b.spend('list', 7)
            b.save()
            a.save()                               # 예전 코드: 여기서 b 의 7건이 사라졌다
            with open(path, encoding='utf-8') as fh:
                saved = json.load(fh)
        self.assertEqual(saved['counts']['list'], 2958 + 7)
        self.assertEqual(saved['runs'], 2)

    def test_saving_twice_does_not_double_count(self):
        """2026-09-23: 회차(runs)는 **프로세스당 한 번**이다 — 수집기가 중간 저장(체크포인트)을 해도 회차가 부풀지 않는다."""
        import tempfile, os, json
        import dart_budget
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'budget.json')
            a = dart_budget.DailyBudget(path)
            a.spend('list', 10)
            a.save()
            a.spend('financial', 3)
            a.save()
            with open(path, encoding='utf-8') as fh:
                saved = json.load(fh)
        self.assertEqual((saved['counts']['list'], saved['counts']['financial'], saved['runs']), (10, 3, 1))

    def test_new_day_starts_from_own_counts(self):
        import tempfile, os, json
        import dart_budget
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'budget.json')
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump({'schemaVersion': 'dart_budget_v1', 'day': '2000-01-01',
                           'counts': {'list': 9999, 'mapping': 0, 'detail': 0, 'financial': 0, 'other': 0},
                           'runs': 40}, fh)
            a = dart_budget.DailyBudget(path)      # 어제 원장은 읽지 않는다(0부터)
            a.spend('list', 5)
            a.save()
            with open(path, encoding='utf-8') as fh:
                saved = json.load(fh)
        self.assertEqual((saved['counts']['list'], saved['runs']), (5, 1))

    def test_report_exposes_the_reserve(self):
        import dart_budget
        rep = self.budget(0).report()
        self.assertEqual(rep['deferrable_reserve'], dart_budget.DEFERRABLE_RESERVE)
        self.assertEqual(rep['deferrable_cutoff'], dart_budget.deferrable_cutoff())
        self.assertEqual(rep['observation_notice'], dart_budget.OBSERVATION_NOTICE)
        self.assertTrue(rep['deferrable_allowed'])


class ReserveReachedMidRunKeepsUntouchedEvidence(unittest.TestCase):
    """몫에 닿으면 **그 자리에서 멈춘다** — 남은 종목의 멀쩡한 증거를 실패 기록으로 덮지 않는다 (2026-09-23 발견).

    수리 전: 루프가 daily.allow('list')(필수 경로 기준)만 봐서, 몫에 닿은 뒤에도 남은 종목 전부를 돌며
    각 종목에 DART_BUDGET_EXCEEDED 실패 기록을 써 넣었다(요청 0건이지만 기존 ok=True 증거가 전부 UNKNOWN 이 됐다).
    """

    def test_remaining_tickers_keep_their_previous_evidence(self):
        import tempfile, os, io, json, datetime
        from unittest import mock
        import dart_budget
        tickers = ['000010', '000020', '000030']
        mapped = {t: {'corp_code': f'C{t}'} for t in tickers}
        previous = {t: {'ok': True, 'ticker': t, 'error': None, 'findings': [], 'unresolvedHistorical': 0,
                        'queriedAt': '2026-09-23T00:00:00+00:00'} for t in tickers}
        client = FakeClient([{'status': dart_client.OK, 'noData': True, 'data': {'status': '013'}}])
        client.corp_code_zip = lambda: {'status': dart_client.OK, 'data': b''}
        client.efficiency_report = lambda: {}
        with tempfile.TemporaryDirectory() as root:
            budget_path = os.path.join(root, 'budget.json')
            daily = dart_budget.DailyBudget(budget_path)
            daily.spend('list', dart_budget.deferrable_cutoff() - 2)      # mapping 1 + 첫 종목 1 = 몫 도달
            daily.save()
            os.makedirs(os.path.join(root, 'config'))
            with open(os.path.join(root, collector.UNIVERSE_FILE), 'w') as handle:
                json.dump({'codes': list(tickers)}, handle)
            os.makedirs(os.path.join(root, collector.OUT_DIR))
            with open(os.path.join(root, collector.OUT_FILE), 'w', encoding='utf-8') as handle:
                json.dump({'cursor': '', 'evidence': previous}, handle)
            old = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(collector, 'BUDGET_FILE', budget_path), \
                     mock.patch.object(collector.dart_client, 'DartClient', return_value=client), \
                     mock.patch.object(collector.dart_pipeline, 'parse_corp_code_zip', lambda data: []), \
                     mock.patch.object(collector.dart_pipeline, 'build_corp_map', lambda rows, uni: {'mapped': mapped}), \
                     mock.patch('sys.stdout', new=io.StringIO()) as out:
                    code = collector.main(['--tickers', '10', '--requests', '100'])
                    summary = json.loads(out.getvalue().strip().splitlines()[-1])
                with open(collector.OUT_FILE, encoding='utf-8') as handle:
                    saved = json.load(handle)
            finally:
                os.chdir(old)
        self.assertEqual(code, 0)
        self.assertEqual(client.calls, 1, '몫에 닿은 뒤 요청이 더 나가면 안 된다')
        self.assertTrue(saved['evidence']['000010']['ok'], '첫 종목은 몫 안에서 정상 수집됐다')
        self.assertEqual(saved['evidence']['000020'], previous['000020'], '손대지 않은 종목의 증거는 그대로다')
        self.assertEqual(saved['evidence']['000030'], previous['000030'])
        # summary['attempted'] 는 이번 회차의 **대상 수**(len(todo))다 — 수리 전 (3, 2, 0) → 지금 (3, 0, 2)
        self.assertEqual((summary['attempted'], summary['failed'], summary['notProcessed']), (3, 0, 2))
        self.assertEqual(summary['notProcessedReason'], 'daily_reserve_reached')


if __name__ == '__main__':
    unittest.main()
