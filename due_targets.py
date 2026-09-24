#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""채점 대상 중심 수집 — 기업행사 증거 수집기 둘(DART·KIND)이 같은 방식으로 대상을 고르게 한다.

왜 있나(2026-09-16)
  증거 TTL 은 20시간인데 수집기는 회차마다 커서를 돌려 40종목씩 훑는다. 600종목을 유지하려면
  하루 15회가 필요하고, 실제로는 예약이 없어 증거가 전부 만료돼 있었다(9/12 이후 유효 0).
  채점에 필요한 것은 "결과일이 도착해 지금 채점 후보가 된 종목"의 증거만이다. 그래서
  planner(price_proof_planner.due_tickers) 가 고른 종목 목록 파일을 받아 **그것만** 수집하는
  제한 모드를 둔다. 기존 전체 순회 모드는 그대로 두고, 이 모드에서는 커서를 건드리지 않는다.

이 파일은 네트워크·판정을 하지 않는다. 대상 목록을 읽고 고르는 규칙만 있다.
"""
import os

MODE_ROTATION = 'cursor_rotation'      # 기존: 커서부터 cap 개
MODE_TICKERS_FILE = 'tickers_file'     # 신규: 파일에 적힌 종목 중 유니버스에 있는 것만


def read_tickers_file(path):
    """한 줄에 종목코드 하나. 빈 줄·`#` 주석 무시. 6자리 숫자만 받고 순서·중복 제거를 보존한다.

    파일이 없거나 비어 있으면 빈 목록이다 — 그때 수집기는 **0종목을 처리한 것**으로 정직하게
    적어야 하고, 조용히 전체 순회로 되돌아가면 안 된다.
    """
    if not path or not os.path.exists(path):
        return []
    seen, out = set(), []
    with open(path, encoding='utf-8') as handle:
        for raw in handle:
            code = raw.split('#', 1)[0].strip()
            if len(code) == 6 and code.isdigit() and code not in seen:
                seen.add(code)
                out.append(code)
    return out


def select_targets(order, cursor, cap, file_codes=None):
    """이번 회차 대상.

    반환 dict:
      todo            실제로 볼 종목(cap 적용)
      mode            MODE_ROTATION | MODE_TICKERS_FILE
      notInUniverse   파일에는 있는데 유니버스(order)에 없어 뺀 종목
      requested       파일 모드에서 파일이 요구한 종목 수(cap 전)
    파일 모드는 커서를 쓰지 않는다 — 호출자는 이 모드에서 커서를 갱신하지 않아야 한다.
    """
    order = list(order)
    cap = max(0, int(cap))
    if file_codes is not None:
        universe = set(order)
        wanted = [c for c in file_codes if c in universe]
        return {'todo': wanted[:cap], 'mode': MODE_TICKERS_FILE,
                'notInUniverse': [c for c in file_codes if c not in universe],
                'requested': len(file_codes)}
    cursor = str(cursor or '')
    start = next((i for i, t in enumerate(order) if t > cursor), 0) if cursor else 0
    return {'todo': (order[start:] + order[:start])[:cap], 'mode': MODE_ROTATION,
            'notInUniverse': [], 'requested': None}
