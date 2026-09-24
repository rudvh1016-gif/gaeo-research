#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenDART 일일 원장 계약 (2026-09-23 신설) — 두 가지를 잠근다.

① 우선순위: **나중에 받아도 되는** 작업(기업행사 증거)은 재무(OPTIONAL)가 끊기기 **전에** 물러난다.
   재현한 결함: 재무는 누적 8,000 에서 끊기는데 증거 수집은 8,500 까지 허용됐다(몫을 하드 상한 기준으로 쟀다).
② 합산: 여러 실행 환경의 사용 횟수가 사라지지도, 두 번 더해지지도 않는다.
   재현한 결함(실측): 분석 러너의 `merge -X ours` 가 증거 러너의 회차를 지웠고(2026-09-23 09:32 KST · 52건),
   증거 러너의 `git pull --rebase` 는 원장 한 줄 충돌로 run 전체(2,600종목·2,956요청)를 유실했다
   (run 35673408325 · 35802153387). 같은 컴퓨터 안의 저장 실패·재시도는 두 번 더했고, 동시 저장은 한쪽을 지웠다.

네트워크 0. git 은 임시 저장소로 **실제로** 돌린다 — 러너가 하는 병합·rebase 를 그대로 재현해야 이 사고가 잡힌다.
'통제군(control)' 시험은 수리 전 동작(드라이버 없음 · 잠금 없음)이 여전히 결함을 **보이는지** 확인한다.
그것이 없으면 이 시험들이 헛도는지 아무도 모른다(교훈: 안전장치가 발동할 수 있는 상태인지 확인해라).
"""
import contextlib
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import dart_budget
import dart_time

HERE = os.path.dirname(os.path.abspath(__file__))
GITATTR_LINE = 'research_archive/dart/api_budget.json merge=dartbudget'


def _ledger(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


# ── ① 우선순위 — 재무보다 먼저 물러난다 ─────────────────────────────────────────────────

class DeferrableYieldsBeforeFinancialIsCut(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='gaeo-ledger-')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def budget(self, spent):
        b = dart_budget.DailyBudget(os.path.join(self.tmp, f'b{spent}.json'))
        b.spend('list', spent)
        return b

    def test_reproduction_financial_blocked_at_8000_so_deferrable_must_be_blocked_too(self):
        """보고된 불일치 그대로: 8,000~8,499 에서 재무는 이미 막혔는데 증거 수집이 허용되면 우선순위 역전이다."""
        for spent in (8000, 8250, 8499):
            b = self.budget(spent)
            self.assertFalse(b.allow('financial'), spent)
            self.assertFalse(b.allow_for_deferrable('list'),
                             f'누적 {spent}: 재무는 막혔는데 대기 가능한 작업이 허용됐다(수리 전 동작)')

    def test_deferrable_never_runs_while_financial_is_blocked(self):
        """0 ~ 10,000 전 구간 불변식: 대기 가능한 작업이 허용되는 곳에서는 재무도 허용되고, 몫만큼 여유가 남아 있다."""
        for spent in range(0, dart_budget.DAILY_HARD_LIMIT + 1, 37):
            b = self.budget(spent)
            if b.allow_for_deferrable('list'):
                self.assertTrue(b.allow('financial'), spent)
                self.assertGreater(b.soft_budget - b.total, dart_budget.DEFERRABLE_RESERVE, spent)

    def test_cutoff_is_the_reserve_below_the_financial_line(self):
        cutoff = dart_budget.deferrable_cutoff()
        self.assertEqual(cutoff, dart_budget.SOFT_BUDGET - dart_budget.DEFERRABLE_RESERVE)
        self.assertTrue(self.budget(cutoff - 1).allow_for_deferrable('list'))
        at = self.budget(cutoff)
        self.assertFalse(at.allow_for_deferrable('list'))
        self.assertFalse(at.allow_for_deferrable('mapping'))
        # 몫은 필수 경로와 재무를 위한 것이다 — 같은 자리에서 그들은 계속 허용된다
        self.assertTrue(at.allow('list'))
        self.assertTrue(at.allow('mapping'))
        self.assertTrue(at.allow('financial'))

    def test_limits_themselves_are_unchanged(self):
        """하루 상한과 재무 중단선을 올려서 해결하지 않았다."""
        self.assertEqual(dart_budget.DAILY_HARD_LIMIT, 10000)
        self.assertEqual(dart_budget.SOFT_BUDGET, 8000)
        self.assertEqual(dart_budget.DEFERRABLE_RESERVE, 1500)
        self.assertEqual(dart_budget.deferrable_cutoff(), 6500)

    def test_report_exposes_cutoff_and_headroom(self):
        rep = self.budget(6000).report()
        self.assertEqual(rep['deferrable_cutoff'], 6500)
        self.assertEqual(rep['deferrable_headroom'], 500)
        self.assertTrue(rep['deferrable_allowed'])
        rep = self.budget(7000).report()
        self.assertEqual(rep['deferrable_headroom'], 0)
        self.assertFalse(rep['deferrable_allowed'])


class ExistingScheduleStillCompletesWithHeadroom(unittest.TestCase):
    """기존 예약(07:10·17:10 전체 갱신 + 09:00~16:00 분석 15회)을 실측 물량으로 하루 돌려 본다.

    자료 완전성(전체 갱신이 끝까지 가는가)과 요청 여유(재무가 한 번도 막히지 않는가)를 함께 본다.
    숫자는 추정이 아니라 실측이다: 전체 갱신 2,957(= mapping 1 + list 2,956 · 2026-09-22 run #4 · 09-23 run #8),
    분석 회차당 list 6~8(9/22~23 원장 증분), 재무 137(9/23 원장).
    """
    FULL_REFRESH = 2957
    ANALYSIS_CYCLES = 15
    LIST_PER_CYCLE_MEASURED = 8
    FINANCIAL_MEASURED = 137
    LIST_PER_CYCLE_MAX = 30          # dart_pipeline.DEFAULT_MAX_PAGES — 설계 최대치
    FINANCIAL_MAX = 150              # collect_dart_financials.DEFAULT_MAX_CALLS

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='gaeo-day-')
        self.budget = dart_budget.DailyBudget(os.path.join(self.tmp, 'ledger.json'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def refresh(self):
        """전체 갱신 한 회차 — 수집기와 같은 규칙(allow_for_deferrable)으로 본다. 쓴 요청 수를 돌려준다."""
        b = self.budget
        if not b.allow_for_deferrable('mapping'):
            return 0
        b.spend('mapping')
        used = 1
        for _ in range(self.FULL_REFRESH - 1):
            if not b.allow_for_deferrable('list'):
                break
            b.spend('list')
            used += 1
        return used

    def analysis_day(self, list_per_cycle, financial):
        """분석 러너 하루 — 회차마다 오늘의 공시, 09:30 회차에 재무 1회. 재무가 막힌 횟수를 돌려준다."""
        b = self.budget
        blocked = 0
        for cycle in range(self.ANALYSIS_CYCLES):
            for _ in range(list_per_cycle):
                self.assertTrue(b.allow('list'), '오늘의 공시가 막히면 그날 공시를 통째로 놓친다')
                b.spend('list')
            if cycle == 1:
                for _ in range(financial):
                    if b.allow('financial'):
                        b.spend('financial')
                    else:
                        blocked += 1
        return blocked

    def test_measured_volumes_both_refreshes_complete_and_financial_is_never_blocked(self):
        self.assertEqual(self.refresh(), self.FULL_REFRESH, '아침 전체 갱신이 끝까지 가야 한다')
        self.assertEqual(self.analysis_day(self.LIST_PER_CYCLE_MEASURED, self.FINANCIAL_MEASURED), 0)
        self.assertEqual(self.refresh(), self.FULL_REFRESH, '저녁 전체 갱신도 끝까지 가야 한다')
        self.assertTrue(self.budget.allow('financial'))
        self.assertLessEqual(self.budget.total, dart_budget.deferrable_cutoff())
        # 실측 물량으로는 몫(1,500) 전체가 그대로 남는다
        self.assertGreaterEqual(dart_budget.SOFT_BUDGET - self.budget.total, dart_budget.DEFERRABLE_RESERVE)

    def test_design_maximum_essentials_financial_is_still_never_blocked(self):
        """필수 경로가 설계 최대치(공시 450 · 재무 150)를 쓰는 날 — 재무는 여전히 한 번도 막히지 않고,
        대신 저녁 전체 갱신이 몇 건 모자란다. 그것이 의도된 우선순위다(증거는 내일, 공시·재무는 오늘)."""
        self.assertEqual(self.refresh(), self.FULL_REFRESH)
        self.assertEqual(self.analysis_day(self.LIST_PER_CYCLE_MAX, self.FINANCIAL_MAX), 0)
        evening = self.refresh()
        self.assertGreaterEqual(evening, self.FULL_REFRESH - 20, f'저녁 갱신 {evening}/{self.FULL_REFRESH}')
        self.assertLessEqual(self.budget.total, dart_budget.deferrable_cutoff())
        self.assertTrue(self.budget.allow('financial'), '대기 가능한 작업이 물러난 자리에서 재무는 열려 있어야 한다')


# ── ② 같은 컴퓨터 안 — 저장 실패·재시도 · 동시 저장 ─────────────────────────────────────────

class SaveIsExactUnderFailureAndRetry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='gaeo-save-')
        self.path = os.path.join(self.tmp, 'ledger.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_failed_write_then_retry_adds_my_increment_exactly_once(self):
        """수리 전: 실패한 save() 가 병합값을 self 에 먼저 넣어, 재시도에서 상대 증가분(7)이 한 번 더 더해지고
        회차도 두 번 세어졌다(list 24 · runs 4). 지금은 성공한 뒤에만 기준점을 옮긴다."""
        mine = dart_budget.DailyBudget(self.path)
        mine.spend('list', 10)
        other = dart_budget.DailyBudget(self.path)       # 그 사이 다른 프로세스가 7건 저장
        other.spend('list', 7)
        other.save()
        with mock.patch.object(dart_budget.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                mine.save()
        self.assertEqual(mine.pending_increment()['list'], 10, '실패했으니 내 증가분은 그대로 대기 중이어야 한다')
        mine.save()                                       # 재시도
        saved = _ledger(self.path)
        self.assertEqual(saved['counts']['list'], 17)
        self.assertEqual(saved['runs'], 2)

    def test_checkpoint_saves_count_one_run_and_add_only_the_delta(self):
        """수집기 중간 저장: 한 프로세스가 여러 번 저장해도 회차는 1, 증가분은 정확히 한 번씩."""
        b = dart_budget.DailyBudget(self.path)
        for _ in range(3):
            b.spend('list', 100)
            b.save()
        saved = _ledger(self.path)
        self.assertEqual((saved['counts']['list'], saved['runs']), (300, 1))
        again = dart_budget.DailyBudget(self.path)       # 다음 프로세스
        again.spend('financial', 1)
        again.save()
        self.assertEqual(_ledger(self.path)['runs'], 2)

    def test_lock_file_lives_outside_the_repository_tree(self):
        """저장소 안에 잠금 파일을 두면 분석 러너의 verify_save_closure(--untracked-files=all)가 그 사이클 커밋을 보류한다."""
        b = dart_budget.DailyBudget(self.path)
        b.spend('list', 1)
        b.save()
        self.assertEqual(sorted(os.listdir(self.tmp)), ['ledger.json'])


def _save_in_child(path, kind, amount, delay, use_lock):
    """다른 프로세스 — 읽은 뒤 잠깐 멈춰 다른 프로세스가 끼어들 틈을 만든다."""
    original = dart_budget._read_ledger

    def slow_read(p):
        doc = original(p)
        time.sleep(delay)
        return doc

    dart_budget._read_ledger = slow_read
    if not use_lock:
        @contextlib.contextmanager
        def no_lock(_path):
            yield
        dart_budget._ledger_lock = no_lock
    b = dart_budget.DailyBudget(path)
    b.spend(kind, amount)
    b.save()


class ConcurrentSavesOnOneMachine(unittest.TestCase):
    AMOUNTS = (100, 200, 300)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='gaeo-conc-')
        self.path = os.path.join(self.tmp, 'ledger.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_children(self, use_lock):
        ctx = multiprocessing.get_context('fork')
        procs = [ctx.Process(target=_save_in_child, args=(self.path, 'list', n, 0.4, use_lock))
                 for n in self.AMOUNTS]
        for p in procs:
            p.start()
        for p in procs:
            p.join(30)
        self.assertTrue(all(p.exitcode == 0 for p in procs), [p.exitcode for p in procs])
        return _ledger(self.path)

    @unittest.skipIf(dart_budget.fcntl is None, 'flock 이 없는 플랫폼')
    def test_three_processes_saving_at_once_lose_nothing(self):
        saved = self.run_children(use_lock=True)
        self.assertEqual(saved['counts']['list'], sum(self.AMOUNTS))
        self.assertEqual(saved['runs'], len(self.AMOUNTS))

    @unittest.skipIf(dart_budget.fcntl is None, 'flock 이 없는 플랫폼')
    def test_control_without_the_lock_an_increment_is_lost(self):
        """통제군: 잠금을 빼면 같은 겹침에서 한쪽 이상이 사라진다 — 위 시험이 실제로 경합을 만들고 있다는 증거."""
        saved = self.run_children(use_lock=False)
        self.assertLess(saved['counts']['list'], sum(self.AMOUNTS))


# ── ② 서로 다른 컴퓨터 사이 — git 병합·rebase ────────────────────────────────────────────

def _git(repo, *args, check=True):
    return subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, timeout=60, check=check)


class _Runners:
    """origin(bare) + clone 들. 원장은 실제 DailyBudget 으로 쓰고, 커밋·push 는 러너와 같은 git 명령으로 한다."""
    LEDGER = dart_budget.LEDGER_REPO_PATH
    EVIDENCE = 'gaeo_coverage/corporate_action_evidence.json'

    def __init__(self, tmp, seed_ledger):
        self.tmp = tmp
        self.origin = os.path.join(tmp, 'origin.git')
        _git(tmp, 'init', '--bare', '-q', self.origin)
        seed = self.clone('seed')
        self._write(seed, self.LEDGER, json.dumps(seed_ledger, separators=(',', ':')))
        self._write(seed, self.EVIDENCE, '{"seed":true}')
        self._write(seed, '.gitattributes', GITATTR_LINE + '\n')
        _git(seed, 'add', '-A')
        _git(seed, 'commit', '-q', '-m', 'seed')
        _git(seed, 'push', '-q', 'origin', 'HEAD:main')

    def clone(self, name):
        path = os.path.join(self.tmp, name)
        _git(self.tmp, 'clone', '-q', '-b', 'main', self.origin, path, check=False)
        if not os.path.isdir(path):                      # 빈 origin 에 첫 clone
            _git(self.tmp, 'clone', '-q', self.origin, path)
            _git(path, 'checkout', '-q', '-b', 'main')
        _git(path, 'config', 'user.name', 'runner')
        _git(path, 'config', 'user.email', 'runner@example.com')
        return path

    @staticmethod
    def _write(repo, rel, text):
        full = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as fh:
            fh.write(text)

    def spend_and_commit(self, repo, spends, evidence=None, message='collector'):
        b = dart_budget.DailyBudget(os.path.join(repo, self.LEDGER))
        for kind, n in spends:
            b.spend(kind, n)
        b.save()
        if evidence is not None:
            self._write(repo, self.EVIDENCE, evidence)
        _git(repo, 'add', '-A')
        _git(repo, 'commit', '-q', '-m', message)

    def push(self, repo):
        return _git(repo, 'push', '-q', 'origin', 'HEAD:main', check=False).returncode

    def ledger(self, repo):
        return _ledger(os.path.join(repo, self.LEDGER))

    def origin_ledger(self):
        return json.loads(_git(self.tmp, '--git-dir', self.origin, 'show', 'main:' + self.LEDGER).stdout)

    def analysis_merge(self, repo):
        """분석 러너의 실제 병합(decision_records.safe_merge 와 같은 명령)."""
        _git(repo, 'fetch', '-q', 'origin', 'main')
        merged = _git(repo, 'merge', '-X', 'ours', '--no-ff', '--no-commit', 'origin/main', check=False)
        if merged.returncode == 0:
            _git(repo, 'commit', '-q', '-m', 'merge')
        return merged.returncode

    def evidence_rebase(self, repo):
        """증거 러너의 실제 재시도(corporate-action-evidence.yml: git pull --rebase origin main)."""
        return _git(repo, 'pull', '-q', '--rebase', 'origin', 'main', check=False).returncode


def _yesterday_ledger():
    return {'schemaVersion': 'dart_budget_v1', 'day': '2000-01-01',
            'counts': {'list': 3053, 'mapping': 1, 'detail': 0, 'financial': 129, 'other': 0},
            'runs': 27, 'updatedAt': '2000-01-01T07:25:46+00:00'}


class RunnersMergeTheirLedgers(unittest.TestCase):
    """2026-09-23 아침을 그대로 재현한다 — 두 러너가 어제 원장에서 시작해 각자 오늘 회차를 더한다."""
    R1 = [('mapping', 1), ('list', 51)]        # 증거 러너(08:45 스모크 회차)
    R2 = [('list', 7), ('financial', 137)]     # 분석 러너 첫 사이클

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='gaeo-git-')
        self.run = _Runners(self.tmp, _yesterday_ledger())
        self.today = dart_time.today_kst()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def expected(self, *spend_lists):
        counts = {k: 0 for k in dart_budget.KINDS}
        for spends in spend_lists:
            for kind, n in spends:
                counts[kind] += n
        return counts

    def test_control_without_driver_the_analysis_runner_merge_discards_the_other_run(self):
        """통제군(수리 전 동작): merge -X ours 가 원장 충돌을 '우리 것' 으로 골라 증거 러너의 52건을 지운다."""
        r1, r2 = self.run.clone('evidence'), self.run.clone('analysis')
        self.run.spend_and_commit(r1, self.R1, evidence='{"round":"r1"}')
        self.assertEqual(self.run.push(r1), 0)
        self.run.spend_and_commit(r2, self.R2)
        self.assertNotEqual(self.run.push(r2), 0, '증거 러너가 먼저 저장했으니 거부돼야 한다')
        self.assertEqual(self.run.analysis_merge(r2), 0)
        merged = self.run.ledger(r2)
        self.assertEqual(merged['counts'], self.expected(self.R2), '통제군: 상대 회차가 사라지는 옛 동작이 재현돼야 한다')
        self.assertEqual(merged['runs'], 1)

    def test_analysis_runner_merge_keeps_both_runs_with_the_driver(self):
        r1, r2 = self.run.clone('evidence'), self.run.clone('analysis')
        self.run.spend_and_commit(r1, self.R1, evidence='{"round":"r1"}')
        self.assertEqual(self.run.push(r1), 0)
        self.run.spend_and_commit(r2, self.R2)
        self.assertNotEqual(self.run.push(r2), 0)
        self.assertTrue(dart_budget.ensure_git_merge_driver(r2))
        self.assertEqual(self.run.analysis_merge(r2), 0)
        merged = self.run.ledger(r2)
        self.assertEqual(merged['day'], self.today)
        self.assertEqual(merged['counts'], self.expected(self.R1, self.R2))
        self.assertEqual(merged['runs'], 2)
        self.assertEqual(self.run.push(r2), 0)
        self.assertEqual(self.run.origin_ledger()['counts'], self.expected(self.R1, self.R2))
        # 증거 파일은 상대(증거 러너) 것이 그대로 남는다 — 이 파일은 분석 러너가 만들지 않는다
        with open(os.path.join(r2, self.run.EVIDENCE), encoding='utf-8') as fh:
            self.assertEqual(json.load(fh), {'round': 'r1'})

    def test_control_without_driver_the_evidence_runner_rebase_conflicts_and_loses_the_run(self):
        """통제군(run 35802153387 그대로): 분석 러너가 먼저 저장하면 증거 러너의 rebase 가 원장 충돌로 멈춘다."""
        r1, r2 = self.run.clone('evidence'), self.run.clone('analysis')
        self.run.spend_and_commit(r2, self.R2)
        self.assertEqual(self.run.push(r2), 0)
        self.run.spend_and_commit(r1, self.R1, evidence='{"round":"full-refresh"}')
        self.assertNotEqual(self.run.push(r1), 0)
        self.assertNotEqual(self.run.evidence_rebase(r1), 0, '통제군: 충돌로 exit 1 — 워크플로는 여기서 죽었다')
        _git(r1, 'rebase', '--abort', check=False)
        self.assertNotIn('full-refresh', json.dumps(self.run.origin_ledger()) + _git(
            self.tmp, '--git-dir', self.run.origin, 'show', 'main:' + self.run.EVIDENCE).stdout)

    def test_evidence_runner_rebase_adds_both_with_the_driver_and_the_evidence_survives(self):
        r1, r2 = self.run.clone('evidence'), self.run.clone('analysis')
        self.run.spend_and_commit(r2, self.R2)
        self.assertEqual(self.run.push(r2), 0)
        self.run.spend_and_commit(r1, self.R1, evidence='{"round":"full-refresh"}')
        self.assertNotEqual(self.run.push(r1), 0)
        self.assertTrue(dart_budget.ensure_git_merge_driver(r1))
        self.assertEqual(self.run.evidence_rebase(r1), 0)
        self.assertEqual(self.run.ledger(r1)['counts'], self.expected(self.R1, self.R2))
        self.assertEqual(self.run.push(r1), 0)
        origin = self.run.origin_ledger()
        self.assertEqual(origin['counts'], self.expected(self.R1, self.R2))
        self.assertEqual(origin['runs'], 2)
        self.assertIn('full-refresh', _git(self.tmp, '--git-dir', self.run.origin, 'show',
                                           'main:' + self.run.EVIDENCE).stdout)

    def test_save_order_does_not_matter(self):
        """저장 순서를 바꿔도(증거 러너가 먼저 / 분석 러너가 먼저) 결과는 같은 합이다."""
        for first_is_evidence in (True, False):
            with self.subTest(evidence_first=first_is_evidence):
                tmp = tempfile.mkdtemp(prefix='gaeo-order-')
                try:
                    run = _Runners(tmp, _yesterday_ledger())
                    r1, r2 = run.clone('evidence'), run.clone('analysis')
                    dart_budget.ensure_git_merge_driver(r1)
                    dart_budget.ensure_git_merge_driver(r2)
                    run.spend_and_commit(r1, self.R1)
                    run.spend_and_commit(r2, self.R2)
                    first, second = (r1, r2) if first_is_evidence else (r2, r1)
                    self.assertEqual(run.push(first), 0)
                    self.assertNotEqual(run.push(second), 0)
                    if second is r2:
                        self.assertEqual(run.analysis_merge(second), 0)
                    else:
                        self.assertEqual(run.evidence_rebase(second), 0)
                    self.assertEqual(run.push(second), 0)
                    self.assertEqual(run.origin_ledger()['counts'], self.expected(self.R1, self.R2))
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

    def test_two_consecutive_conflicts_do_not_double_count(self):
        """저장 실패·재시도(rebase 두 번): 두 번째 rebase 는 첫 병합 결과를 조상으로 삼아 내 증가분만 다시 얹는다."""
        r1, r2, r3 = self.run.clone('evidence'), self.run.clone('analysis'), self.run.clone('smoke')
        R3 = [('list', 5)]
        dart_budget.ensure_git_merge_driver(r1)
        self.run.spend_and_commit(r2, self.R2)
        self.assertEqual(self.run.push(r2), 0)
        self.run.spend_and_commit(r1, self.R1)
        self.assertNotEqual(self.run.push(r1), 0)
        self.assertEqual(self.run.evidence_rebase(r1), 0)         # 첫 재시도
        _git(r3, 'pull', '-q', '--rebase', 'origin', 'main')       # 그 사이 세 번째 러너가 또 저장
        self.run.spend_and_commit(r3, R3)
        self.assertEqual(self.run.push(r3), 0)
        self.assertNotEqual(self.run.push(r1), 0)
        self.assertEqual(self.run.evidence_rebase(r1), 0)         # 두 번째 재시도
        self.assertEqual(self.run.push(r1), 0)
        origin = self.run.origin_ledger()
        self.assertEqual(origin['counts'], self.expected(self.R1, self.R2, R3))
        self.assertEqual(origin['runs'], 3)

    def test_same_day_base_only_adds_increments(self):
        """조상이 이미 오늘 원장일 때(둘째 사이클 이후): 조상 값에 두 쪽 증가분만 더한다."""
        tmp = tempfile.mkdtemp(prefix='gaeo-sameday-')
        try:
            today_seed = {'schemaVersion': 'dart_budget_v1', 'day': self.today,
                          'counts': {'list': 100, 'mapping': 0, 'detail': 0, 'financial': 137, 'other': 0},
                          'runs': 4, 'updatedAt': '2026-09-23T01:00:00+00:00'}
            run = _Runners(tmp, today_seed)
            r1, r2 = run.clone('evidence'), run.clone('analysis')
            dart_budget.ensure_git_merge_driver(r2)
            run.spend_and_commit(r1, [('list', 2956), ('mapping', 1)])
            self.assertEqual(run.push(r1), 0)
            run.spend_and_commit(r2, [('list', 8)])
            self.assertNotEqual(run.push(r2), 0)
            self.assertEqual(run.analysis_merge(r2), 0)
            merged = run.ledger(r2)
            self.assertEqual(merged['counts'], {'list': 3064, 'mapping': 1, 'detail': 0, 'financial': 137, 'other': 0})
            self.assertEqual(merged['runs'], 6)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class MergeLedgersUnit(unittest.TestCase):
    def doc(self, day, runs=1, **counts):
        c = {k: 0 for k in dart_budget.KINDS}
        c.update(counts)
        return {'schemaVersion': 'dart_budget_v1', 'day': day, 'counts': c, 'runs': runs, 'updatedAt': f'{day}T00:00:00'}

    def test_yesterday_base_today_sides_are_summed(self):
        out = dart_budget.merge_ledgers(self.doc('2026-09-22', list=3053, runs=27),
                                        self.doc('2026-09-23', list=7, financial=137, runs=2),
                                        self.doc('2026-09-23', list=51, mapping=1, runs=1))
        self.assertEqual((out['day'], out['counts']['list'], out['counts']['mapping'], out['counts']['financial'], out['runs']),
                         ('2026-09-23', 58, 1, 137, 3))

    def test_side_on_an_older_day_contributes_nothing(self):
        out = dart_budget.merge_ledgers(self.doc('2026-09-22', list=10), self.doc('2026-09-23', list=5), self.doc('2026-09-22', list=99))
        self.assertEqual((out['day'], out['counts']['list'], out['runs']), ('2026-09-23', 5, 1))

    def test_missing_base_and_missing_side(self):
        out = dart_budget.merge_ledgers(None, self.doc('2026-09-23', list=5), None)
        self.assertEqual(out['counts']['list'], 5)
        self.assertIsNone(dart_budget.merge_ledgers(None, None, None))

    def test_negative_increments_are_clamped_and_unknown_kinds_fold_into_other(self):
        base = self.doc('2026-09-23', list=100, runs=3)
        ours = self.doc('2026-09-23', list=90, runs=2)                    # 조상보다 줄었다 — 기여 0
        theirs = self.doc('2026-09-23', list=110, runs=4)
        theirs['counts']['weird'] = 2
        out = dart_budget.merge_ledgers(base, ours, theirs)
        self.assertEqual((out['counts']['list'], out['counts']['other'], out['runs']), (110, 2, 4))

    def test_driver_refuses_broken_json_instead_of_inventing_a_ledger(self):
        tmp = tempfile.mkdtemp(prefix='gaeo-drv-')
        try:
            paths = [os.path.join(tmp, n) for n in ('base', 'ours', 'theirs')]
            for p, text in zip(paths, ('', json.dumps(self.doc('2026-09-23', list=1)), '<<<<<<< garbage')):
                with open(p, 'w', encoding='utf-8') as fh:
                    fh.write(text)
            self.assertEqual(dart_budget.git_merge_driver(*paths), 1)
            with open(paths[1], encoding='utf-8') as fh:
                self.assertEqual(json.load(fh)['counts']['list'], 1, '실패 시 우리 쪽 파일을 건드리지 않는다')
            self.assertEqual(dart_budget.main(['--git-merge', paths[0], paths[1]]), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class DriverIsWiredWhereRunnersMerge(unittest.TestCase):
    """드라이버는 두 곳(gitattributes · 증거 러너 워크플로)이 맞아야 살아난다(새 저장소에는 분석 러너가 없다)."""

    def _read(self, rel):
        with open(os.path.join(HERE, rel), encoding='utf-8') as fh:
            return fh.read()

    def test_gitattributes_declares_the_ledger_driver(self):
        lines = [l.strip() for l in self._read('.gitattributes').splitlines() if l.strip() and not l.startswith('#')]
        self.assertIn(GITATTR_LINE, lines)
        self.assertEqual(GITATTR_LINE, f'{dart_budget.LEDGER_REPO_PATH} merge={dart_budget.MERGE_DRIVER_NAME}')
        self.assertTrue(os.path.exists(os.path.join(HERE, dart_budget.LEDGER_REPO_PATH)))

    def test_evidence_and_smoke_workflows_install_the_driver_before_their_rebase(self):
        for name in ('corporate-action-evidence.yml',):
            text = self._read(os.path.join('.github', 'workflows', name))
            install = text.find('python3 dart_budget.py --install-git-merge-driver')
            rebase = text.find('git pull --rebase origin main')
            self.assertGreater(install, -1, name)
            self.assertGreater(rebase, -1, name)
            self.assertLess(install, rebase, f'{name}: 드라이버 등록이 rebase 보다 앞이어야 한다')

    def test_install_command_writes_local_git_config(self):
        tmp = tempfile.mkdtemp(prefix='gaeo-cfg-')
        try:
            _git(tmp, 'init', '-q')
            self.assertEqual(dart_budget.main(['--install-git-merge-driver', tmp]), 0)
            value = _git(tmp, 'config', '--get', f'merge.{dart_budget.MERGE_DRIVER_NAME}.driver').stdout.strip()
            self.assertIn('--git-merge %O %A %B', value)
            self.assertIn('dart_budget.py', value)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
