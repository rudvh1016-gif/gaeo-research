#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenDART 일일 호출 예산 — 설정을 한 곳에 모은다.

⚠️ 10,000건을 다 쓰는 설계는 실패다.
   목표는 하루 수백 회 수준이다. 아래 상한은 사고를 막는 안전장치일 뿐,
   평상시 도달할 값이 아니다.

⚠️ 이 숫자들은 **이 계정 기준으로 사용자가 확인해 준 값**이다.
   공식 정책이 바뀌면 여기 한 곳만 고친다. 코드 곳곳에 흩뿌리지 않는다.

원장(`research_archive/dart/api_budget.json`)은 **여러 실행 환경이 같은 날 함께 쓰는 하나의 계수기**다.
    · update-analysis 러너(30분 주기 · 오늘의 공시·재무)
    · corporate-action-evidence 러너(07:10·17:10 KST 전체 갱신)
    · dart-live-smoke-test(dispatch)
  각자 자기 clone 에서 증가분을 더해 커밋하고 main 으로 push 한다. 그래서 합산이 **두 층**에서 맞아야 한다.
    ① 같은 컴퓨터 안(프로세스 겹침·저장 실패·재시도) — `DailyBudget.save()` 가 잠금 + 증가분 병합으로 지킨다.
    ② 서로 다른 컴퓨터 사이(git 병합·rebase) — `merge_ledgers()` 를 git 병합 드라이버(`--git-merge`)로 등록해
       조상·우리·상대 세 판본을 **더한다**. `.gitattributes` 의 `merge=dartbudget` 과 짝이다.
  ⚠️ 2026-09-23 실측: ②가 없던 동안 분석 러너의 `merge -X ours` 는 증거 러너의 회차를 **통째로 지웠고**(09:32 KST,
     51+1건 소실), 증거 러너의 `git pull --rebase` 는 원장 한 줄 충돌로 **run 전체(2,600종목·2,956요청)를 유실**했다
     (run 35673408325 · 35802153387). 원장이 실제 사용량보다 수천 건 적게 적혀 있었다 — 그 원장을 읽는 예산 보호는
     발동할 수 없었다(교훈 ⑥).
"""
import contextlib
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

try:
    import fcntl                      # POSIX 전용. 러너(ubuntu)·이 세션은 있다. 없으면(Windows) 잠금 없이 진행한다.
except ImportError:                   # pragma: no cover
    fcntl = None

import dart_time

# ── 설정 (한 곳에서만 관리) ─────────────────────────────────────────────────
# 계정 기준 일일 안전 상한. 사용자 확인값(2026-08-15).
DAILY_HARD_LIMIT = 10000

# 이 선을 넘으면 '필수가 아닌' 요청(상세·재무)을 먼저 중단한다.
# 신규공시 목록 탐지는 계속한다 — 그걸 멈추면 그날 공시를 통째로 놓친다.
SOFT_BUDGET = 8000

# 평상시 목표. 이 값을 크게 넘으면 설계가 잘못된 것이다.
NORMAL_TARGET_PER_DAY = 500

# 관측 경고선. 여기를 넘으면 "아직 한도는 아니지만 평상시 설계에서 이탈했다"를 감시가 말해야 한다.
#
# ⚠️ 왜 이 선을 만들었나 (2026-09-22 실측)
#    `corporate-action-evidence.yml` 의 예약 2건(07:10·17:10 KST · 각 `--requests 4000`)이
#    처음 발화한 날, 하루 사용량이 **3,183건**이 됐다 — 직전 최대 252건(9/16)의 12.6배다.
#    그 도약을 **아무 감시도 보지 않았다.** `api_budget.json` 은 커밋되고 있었지만
#    그 파일을 읽는 점검이 저장소에 하나도 없었다. 이제 `ops_status.check_dart_budget` 이 읽는다.
OBSERVATION_NOTICE = 4000

# **나중에 다시 받아도 되는** 작업(기업행위 증거 수집 등)이 남겨 둬야 하는 몫.
#
# ⚠️ 왜 필요했나 — SOFT_BUDGET 이 증거 수집기를 전혀 막지 못한다
#    `collect_corporate_action_evidence.py` 는 페이지 요청을 `list` 로 센다. `list` 는 ESSENTIAL 이라
#    `allow()` 의 soft budget 차단에 걸리지 않는다. 그래서 증거 수집이 하드 상한까지 내달릴 수 있고,
#    정작 굶는 것은 **그날 놓치면 영구 결손인 오늘의 공시(`list`)** 와 **재무(`financial`, OPTIONAL)** 다.
#    우선순위가 거꾸로 선 상태였다.
#
# ⚠️ 어디를 기준으로 재나 (2026-09-23 정정)
#    이 몫은 **재무(OPTIONAL)가 끊기는 선(SOFT_BUDGET 8,000)** 을 기준으로 잰다. 9/22 판은 하드 상한(10,000)을
#    기준으로 재서 대기 가능한 작업이 누적 8,500까지 허용됐는데, 재무는 8,000에서 이미 끊겨 있었다 — 덜 급한
#    쪽이 더 급한 쪽보다 **늦게** 물러나는 역전이었다. 지금은 누적 6,500(= 8,000 − 1,500)에서 대기 가능한 작업이
#    먼저 물러난다. 하루 상한(10,000)과 재무 중단선(8,000)은 바꾸지 않았다(`deferrable_cutoff()` 참조).
#
# 산정 근거: 오늘의 공시 최대 필요치 = `dart_pipeline.DEFAULT_MAX_PAGES`(30) × 하루 실행 수(30분 주기
#    09:00~16:00 → 15회) = 450. 재무 실측 ≈ 130/일(2026-09-14~22). 합 580 의 약 2.5배를 남긴다.
#    전체 갱신 2회(회차당 약 2,957 · 2026-09-22~23 실측) + 실측 필수 사용(약 230) = 약 6,150 으로 6,500 안에 든다.
#    필수 경로가 설계 최대치(450 + 150)를 쓰는 날에는 두 번째 갱신이 몇 건 모자랄 수 있다 — 그것이 의도된
#    우선순위다(증거는 내일 받을 수 있고, 20시간 TTL 안에서는 아침 증거가 유효하다).
DEFERRABLE_RESERVE = 1500

# 요청 종류별 우선순위. 예산이 빠듯하면 낮은 것부터 끊는다.
ESSENTIAL = ("list", "mapping")           # 이걸 멈추면 수집 자체가 무의미
OPTIONAL = ("detail", "financial")        # 나중에 다시 받아도 되는 것
KINDS = ("list", "mapping", "detail", "financial", "other")

BUDGET_OK = "BUDGET_OK"
DART_BUDGET_WARNING = "DART_BUDGET_WARNING"
DART_BUDGET_EXCEEDED = "DART_BUDGET_EXCEEDED"

SCHEMA_VERSION = "dart_budget_v1"
#: 저장소 기준 원장 경로 — `.gitattributes` 의 항목과 같은 문자열이어야 한다(test_dart_budget_ledger 가 대조한다).
LEDGER_REPO_PATH = "research_archive/dart/api_budget.json"
#: git 병합 드라이버 이름 — `.gitattributes` 의 `merge=dartbudget` 과 같아야 한다.
MERGE_DRIVER_NAME = "dartbudget"


def deferrable_cutoff(hard_limit=DAILY_HARD_LIMIT, soft_budget=SOFT_BUDGET, reserve=DEFERRABLE_RESERVE):
    """대기 가능한 작업이 물러나야 하는 누적 사용량 — 재무가 끊기는 선에서 몫만큼 아래다."""
    return min(hard_limit, soft_budget) - reserve


def _empty_counts():
    return {k: 0 for k in KINDS}


def _read_ledger(path):
    """원장 파일 → dict. 없거나 깨졌으면 None(0건이라는 뜻이 아니다 — 호출자가 구분한다)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_ledger(path, doc):
    """임시 파일 → fsync → 원자 교체. 반쯤 쓰인 원장이 남지 않는다.

    임시 이름에 pid 를 넣는다 — 같은 이름을 두 프로세스가 쓰면 한쪽의 os.replace 가 '파일 없음' 으로 죽는다
    (잠금이 있으면 겹치지 않지만, 잠금 없는 플랫폼·통제군 시험에서 실제로 그렇게 죽었다).
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextlib.contextmanager
def _ledger_lock(path):
    """같은 컴퓨터의 두 프로세스가 읽기→합산→쓰기를 겹치지 못하게 한다.

    잠금 파일은 **저장소 밖**(임시 폴더)에 둔다 — 저장소 안에 두면 분석 러너의 `verify_save_closure.py`
    (`--untracked-files=all`)가 '예상 밖 파일' 로 잡아 그 사이클 커밋을 통째로 보류한다.
    """
    if fcntl is None:                                   # pragma: no cover — Windows
        yield
        return
    key = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:16]
    lock_path = os.path.join(tempfile.gettempdir(), f"gaeo-dart-budget-{key}.lock")
    with open(lock_path, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def merge_increment(on_disk, day, increment, run_increment):
    """디스크 원장 + 이 프로세스의 증가분. 날이 다르면 증가분이 곧 그날의 첫 기록이다."""
    counts = _empty_counts()
    runs = 0
    if isinstance(on_disk, dict) and on_disk.get("day") == day:
        for k, v in (on_disk.get("counts") or {}).items():
            counts[k if k in counts else "other"] += int(v or 0)
        runs = int(on_disk.get("runs") or 0)
    for k, v in increment.items():
        counts[k if k in counts else "other"] += int(v)
    return {"schemaVersion": SCHEMA_VERSION, "day": day, "counts": counts,
            "runs": runs + int(run_increment), "updatedAt": dart_time.iso_now()}


class DailyBudget:
    """하루 누적 호출 수를 파일로 이어서 센다(Runner가 매번 새로 뜨므로).

    날짜 기준은 Asia/Seoul이다. UTC 자정에 리셋되면 한국 장중에 카운터가
    끊겨서 실제 사용량을 못 본다.
    """

    def __init__(self, path, hard_limit=DAILY_HARD_LIMIT, soft_budget=SOFT_BUDGET):
        self.path = path
        self.hard_limit = hard_limit
        self.soft_budget = soft_budget
        self.day = dart_time.today_kst()
        self.counts = _empty_counts()
        self.runs = 0
        self._load()
        # 이 프로세스가 마지막으로 원장과 맞춘 값. save() 는 "내 증가분"(counts − _base)만 파일에 더한다.
        self._base = dict(self.counts)
        # 이 프로세스가 이미 회차 1건으로 세어졌는가 — 중간 저장(체크포인트)을 여러 번 해도 회차는 한 번만 센다.
        self._run_counted = False

    def _load(self):
        data = _read_ledger(self.path)
        if data is None or data.get("day") != self.day:
            return                     # 날이 바뀌면 0부터
        for k, v in (data.get("counts") or {}).items():
            if k in self.counts:
                self.counts[k] = int(v)
        self.runs = int(data.get("runs") or 0)

    @property
    def total(self):
        return sum(self.counts.values())

    @property
    def remaining(self):
        return max(0, self.hard_limit - self.total)

    def allow(self, kind):
        """이 종류의 요청을 지금 해도 되는가."""
        if self.total >= self.hard_limit:
            return False
        if kind in OPTIONAL and self.total >= self.soft_budget:
            return False           # 비필수부터 끊는다(Graceful Degradation)
        return True

    def deferrable_headroom(self, reserve=None):
        """**나중에 다시 받아도 되는** 작업이 지금 더 쓸 수 있는 양.

        재무(OPTIONAL)가 끊기는 선(`soft_budget`)에서 몫(`reserve`)을 뺀 자리까지만 쓴다. 0 이하면 물러난다.
        하드 상한이 아니라 소프트 예산을 기준으로 재는 이유는 위 `DEFERRABLE_RESERVE` 주석 참조.
        """
        floor = DEFERRABLE_RESERVE if reserve is None else reserve
        return deferrable_cutoff(self.hard_limit, self.soft_budget, floor) - self.total

    def allow_for_deferrable(self, kind, reserve=None):
        """**나중에 다시 받아도 되는** 작업용 허가. 필수 경로와 재무의 몫을 남긴다.

        `allow()` 는 요청 *종류*만 본다. 그래서 증거 수집처럼 `list`(ESSENTIAL)로 세는 대기 가능한
        작업이 soft budget 을 그대로 통과해 하드 상한까지 내달릴 수 있었다(2026-09-22 발견).
        이 함수는 **작업의 급함**을 따로 본다 — 재무가 끊기기 전에, 몫만큼 여유를 남기고 거절한다.

        오늘 못 받은 증거는 내일 받을 수 있다. 오늘 놓친 공시는 되돌릴 수 없다.
        """
        if not self.allow(kind):
            return False
        return self.deferrable_headroom(reserve) > 0

    def spend(self, kind, n=1):
        self.counts[kind if kind in self.counts else "other"] += n

    def status(self):
        if self.total >= self.hard_limit:
            return DART_BUDGET_EXCEEDED
        if self.total >= self.soft_budget:
            return DART_BUDGET_WARNING
        return BUDGET_OK

    def report(self):
        headroom = self.deferrable_headroom()
        return {
            "day": self.day,
            "requests_today": self.total,
            "byKind": dict(self.counts),
            "runs_today": self.runs,
            "hard_limit": self.hard_limit,
            "soft_budget": self.soft_budget,
            "normal_target_per_day": NORMAL_TARGET_PER_DAY,
            "observation_notice": OBSERVATION_NOTICE,
            "deferrable_reserve": DEFERRABLE_RESERVE,
            "deferrable_cutoff": deferrable_cutoff(self.hard_limit, self.soft_budget),
            "deferrable_headroom": max(0, headroom),
            "deferrable_allowed": headroom > 0 and self.allow("list"),
            "remaining": self.remaining,
            "usage_pct_of_hard_limit": round(self.total / self.hard_limit * 100, 2)
            if self.hard_limit else None,
            "status": self.status(),
            "note": "10,000건은 안전 상한이지 목표가 아니다. 평상시 수백 회 수준을 지향한다.",
        }

    def pending_increment(self):
        """아직 파일에 더하지 않은 내 증가분(종류별)."""
        return {k: self.counts[k] - self._base.get(k, 0) for k in self.counts}

    def save(self):
        """내 증가분만 원장에 더한다 — 겹쳐 돈 다른 프로세스의 기록을 덮지 않고, 실패해도 두 번 더하지 않는다.

        ⚠️ 왜 (2026-09-23 발견, CAE-2): 예전 save() 는 시작 때 읽은 값 + 내 사용량을 그대로 썼다.
           같은 날 두 수집기가 겹치면 나중에 저장하는 쪽이 먼저 저장한 쪽의 회차를 **통째로 지운다**.
           고치는 법: 저장 직전에 파일을 다시 읽고, 같은 날이면 on_disk + 내 증가분.
        ⚠️ 그리고 (2026-09-23 두 번째 발견): 9/23 판은 병합값을 **쓰기 전에** self 에 먼저 넣었다. 쓰기가
           실패하고 호출자가 재시도하면 회차가 2번 더해지고, 그 사이 다른 프로세스가 저장했으면 그쪽 증가분도
           내 것처럼 한 번 더 더해졌다. 지금은 성공한 뒤에만 기준점을 옮긴다.
        ⚠️ 잠금: 읽기→합산→쓰기 사이에 다른 프로세스가 끼어들면 한쪽 증가분이 사라진다. 같은 컴퓨터 안에서는
           flock 으로 막는다. 다른 컴퓨터(러너) 사이의 합산은 git 병합 드라이버(`merge_ledgers`)가 맡는다.
        회차(runs)는 **프로세스당 한 번**만 센다 — 중간 저장(체크포인트)을 여러 번 해도 회차 수는 늘지 않는다.
        """
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        increment = self.pending_increment()
        run_increment = 0 if self._run_counted else 1
        with _ledger_lock(self.path):
            merged = merge_increment(_read_ledger(self.path), self.day, increment, run_increment)
            _write_ledger(self.path, merged)
        # 여기까지 왔으면 파일에 들어갔다 — 이제야 기준점을 옮긴다(실패·재시도에서 두 번 더해지지 않게).
        self.counts = dict(merged["counts"])
        self.runs = merged["runs"]
        self._base = dict(self.counts)
        self._run_counted = True


# ── git 병합 드라이버: 서로 다른 러너의 원장을 더한다 ──────────────────────────────────────

def _normalize(doc):
    """원장 JSON → 비교 가능한 모양. dict 가 아니면 None."""
    if not isinstance(doc, dict) or not isinstance(doc.get("counts"), dict):
        return None
    counts = _empty_counts()
    for k, v in doc["counts"].items():
        counts[k if k in counts else "other"] += int(v or 0)
    return {"day": str(doc.get("day") or ""), "counts": counts,
            "runs": int(doc.get("runs") or 0), "updatedAt": str(doc.get("updatedAt") or "")}


def merge_ledgers(base, ours, theirs):
    """세 판본(공통 조상 · 우리 · 상대)의 원장을 **더한다** — 어느 쪽의 회차도 지우지 않고, 두 번 더하지도 않는다.

    규칙
      · 결과 날짜 = 두 쪽 중 늦은 날짜(ISO 문자열 비교). 원장은 하루치만 담는다.
      · 그 날짜에 있는 쪽만 기여한다.
        조상도 그 날짜면 각 쪽의 기여 = (그 쪽 − 조상) 증가분, 조상이 다른 날이면 기여 = 그 쪽 전체(그날 0부터 셌으므로).
      · 결과 = (조상이 그 날짜면 조상 값) + 기여(우리) + 기여(상대). 대칭이라 merge·rebase 어느 방향이든 같다.
      · 음수 증가분은 0 으로 본다(원장은 늘어나기만 한다 — 조상보다 줄어든 쪽은 기여하지 않는다).
      · 두 쪽 다 읽을 수 없으면 None(해결하지 않는다 — 사람이 본다).
    """
    b, o, t = _normalize(base), _normalize(ours), _normalize(theirs)
    sides = [s for s in (o, t) if s is not None]
    if not sides:
        return None
    day = max(s["day"] for s in sides)
    base_same_day = b is not None and b["day"] == day
    counts = dict(b["counts"]) if base_same_day else _empty_counts()
    runs = b["runs"] if base_same_day else 0
    updated = b["updatedAt"] if base_same_day else ""
    for side in sides:
        if side["day"] != day:
            continue
        for k in KINDS:
            gain = side["counts"][k] - (b["counts"][k] if base_same_day else 0)
            counts[k] += max(0, gain)
        runs += max(0, side["runs"] - (b["runs"] if base_same_day else 0))
        updated = max(updated, side["updatedAt"])
    return {"schemaVersion": SCHEMA_VERSION, "day": day, "counts": counts, "runs": runs, "updatedAt": updated}


_BROKEN = object()


def _load_for_merge(path):
    """드라이버 입력 파일 하나. 없거나 비었으면 None(그 쪽에 원장이 없었다), JSON 이 깨졌으면 _BROKEN."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _BROKEN


def git_merge_driver(base_path, ours_path, theirs_path):
    """git 병합 드라이버 진입점(`%O %A %B`). 결과를 %A 에 쓴다. 0 = 해결 · 1 = 해결 못 함(충돌로 남긴다).

    깨진 JSON(충돌 표시가 남은 파일 등)은 만들어 내지 않고 사람에게 넘긴다 — 모른다를 괜찮다로 바꾸지 않는다.
    """
    docs = [_load_for_merge(p) for p in (base_path, ours_path, theirs_path)]
    if any(d is _BROKEN for d in docs):
        return 1
    merged = merge_ledgers(*docs)
    if merged is None:
        return 1
    with open(ours_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
    return 0


def merge_driver_command(python=None):
    """이 clone 에 등록할 드라이버 명령. 절대경로라 git 이 어느 cwd 에서 부르든 같은 파일을 쓴다."""
    exe = python or sys.executable or "python3"
    return f'"{exe}" "{os.path.abspath(__file__)}" --git-merge %O %A %B'


def ensure_git_merge_driver(repo=".", python=None):
    """원장 병합 드라이버를 이 clone 의 로컬 git config 에 등록한다(멱등). `.gitattributes` 의 `merge=dartbudget` 과 짝.

    git 은 보안상 저장소 안에 든 config 를 읽지 않는다. 그래서 러너마다 clone 뒤에 이 한 줄이 있어야
    드라이버가 살아난다 — 없으면 git 은 기본 텍스트 병합으로 물러나 충돌을 낸다(2026-09-23 까지의 동작).
    실패해도 예외를 던지지 않는다(병합 자체를 막지 않는다). 등록됐으면 True.
    """
    command = merge_driver_command(python)
    try:
        subprocess.run(["git", "config", f"merge.{MERGE_DRIVER_NAME}.driver", command],
                       cwd=repo, check=True, timeout=30, capture_output=True)
        subprocess.run(["git", "config", f"merge.{MERGE_DRIVER_NAME}.name", "OpenDART daily budget ledger (additive)"],
                       cwd=repo, check=False, timeout=30, capture_output=True)
    except (OSError, subprocess.SubprocessError) as ex:
        print(f"[dart_budget] 병합 드라이버 등록 실패 — 기본 병합으로 진행: {type(ex).__name__}", file=sys.stderr)
        return False
    return True


def project(list_requests_per_run, runs_per_day, mapping_per_day=0,
            financial_per_day=0, detail_per_day=0):
    """하루 예상 호출 수를 계산한다. 추측이 아니라 실측값을 넣어 쓴다."""
    per_day = list_requests_per_run * runs_per_day + mapping_per_day \
        + financial_per_day + detail_per_day
    return {
        "list_requests_per_run": list_requests_per_run,
        "runs_per_day": runs_per_day,
        "mapping_per_day": mapping_per_day,
        "financial_per_day": financial_per_day,
        "detail_per_day": detail_per_day,
        "expected_daily_requests": per_day,
        "pct_of_hard_limit": round(per_day / DAILY_HARD_LIMIT * 100, 2),
    }


def main(argv=None):
    """명령줄 — 워크플로·git 이 부른다.

      python3 dart_budget.py --install-git-merge-driver [repo]   # clone 에 드라이버 등록(멱등)
      python3 dart_budget.py --git-merge %O %A %B                # git 이 부르는 드라이버(직접 쓰지 않는다)
      python3 dart_budget.py --report [원장경로]                  # 원장 요약(읽기만)
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(main.__doc__)
        return 0
    if args[0] == "--git-merge":
        if len(args) != 4:
            print("usage: --git-merge <base> <ours> <theirs>", file=sys.stderr)
            return 2
        return git_merge_driver(args[1], args[2], args[3])
    if args[0] == "--install-git-merge-driver":
        repo = args[1] if len(args) > 1 else "."
        ok = ensure_git_merge_driver(repo)
        print(f"merge.{MERGE_DRIVER_NAME}.driver = {merge_driver_command()}" if ok else "등록 실패")
        return 0 if ok else 1
    if args[0] == "--report":
        path = args[1] if len(args) > 1 else LEDGER_REPO_PATH
        print(json.dumps(DailyBudget(path).report(), ensure_ascii=False, indent=1))
        return 0
    print(f"알 수 없는 인자: {args}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
