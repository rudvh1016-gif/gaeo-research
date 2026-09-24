#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""회사별 기업행사 증거 수집 — GAEO Private 판정부가 그대로 소비하는 증거를 만든다.

이 파일은 **판정하지 않는다.** 조회하고, 끝까지 받았는지 대조하고, 증거를 남길 뿐이다.
상태(EVENT_FOUND / VERIFIED_NONE / UNKNOWN / REVIEW_REQUIRED)는 Private 이 정한다.

왜 회사별로 부르나
  전체 신규공시 목록에 그 종목이 안 보였다는 것은 '그 종목에 공시가 없었다'의 증거가 아니다.
  부재를 증명하려면 회사별로 조회하고 페이지를 끝까지 받아 건수를 대조해야 한다.

무엇을 절대 하지 않나
  조회 실패·전송 실패·페이지 누락·건수 불일치를 0건으로 바꾸지 않는다.
  회사명 문자열로 종목을 잇지 않는다(공식 corp_code↔stock_code 완전일치만).
  인증키를 URL·로그·산출물에 남기지 않는다(dart_client.redact).

과거 확인 범위와 그 한계
  BACKFILL_DAYS 만큼만 거슬러 본다. 기준가격을 바꾸는 행사(무상증자·주식배당·액면분할·감자·
  합병·분할)는 결정에서 적용까지 통상 수개월 안에 끝나므로 12개월이면 아직 유효한 것을 담는다.
  그보다 오래된 구간은 **미확인**이며, 이 수집은 그 구간에 대해 아무 말도 하지 않는다.

쓰는 법
  python3 collect_corporate_action_evidence.py [--tickers 50] [--requests 400] [--days 365]
  python3 collect_corporate_action_evidence.py --tickers-file due.txt --tickers 600   # 채점 후보만(커서 보존)
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

import corporate_action_classify as classify
import disclosure_scope as comparison
import dart_client
import dart_budget
import due_targets
import dart_pipeline

#: 이 수집기가 만드는 증거의 계약 버전. Private 이 이 이름으로 계약을 확인한다.
CONTRACT_VERSION = 'corporate-action-evidence-v1'
PARSER_VERSION = 'opendart-list-json-v3-effects'
SOURCE = 'OPENDART_API'
RETRIEVAL_PATH = 'opendart:list.json?corp_code'
IDENTITY_BASIS = 'corp_code_map'
#: 과거 확인 범위(일). 위 docstring 의 근거로 정한 값이며 바꾸면 문서도 함께 바꾼다.
BACKFILL_DAYS = 365
#: 증거 유효시간(시간). 지나면 Private 이 EVIDENCE_EXPIRED 로 닫는다.
EVIDENCE_TTL_HOURS = 20
#: 이만큼 종목을 볼 때마다 일일 원장을 중간 저장한다(요청 약 230건 · 4~5분어치). 죽은 run 의 사용량이 통째로 사라지지 않게.
CHECKPOINT_EVERY = 200
#: 기준가격·주식수·상장상태에 영향을 주는 공시 제목 낱말. 현금배당은 주식 수를 바꾸지 않아 뺀다.
RELEVANT_TERMS = ('합병', '분할', '감자', '액면', '무상증자', '유상증자', '권리락',
                  '주식교환', '주식이전', '공개매수', '주식배당', '상장폐지', '거래정지')
OUT_DIR = 'gaeo_coverage'
OUT_FILE = os.path.join(OUT_DIR, 'corporate_action_evidence.json')
BUDGET_FILE = os.path.join('research_archive', 'dart', 'api_budget.json')
UNIVERSE_FILE = os.path.join('config', 'evidence_universe.json')


def _today():
    return datetime.datetime.now(datetime.timezone.utc)


def _ymd(value):
    return value.strftime('%Y%m%d')


def _relevant(title):
    return sorted({t for t in RELEVANT_TERMS if t in (title or '')})


def collect_one(client, ticker, corp_code, bgn_de, end_de, budget):
    """한 종목의 증거 한 건. budget['left'] 를 깎아 쓴다.

    실패는 실패로 남긴다 — ok=False 인 증거도 그대로 돌려준다(빠뜨리면 조용한 0건이 된다).
    """
    queried_at = _today()
    base = {
        'source': SOURCE, 'retrievalPath': RETRIEVAL_PATH, 'ticker': ticker,
        'identityBasis': IDENTITY_BASIS, 'from': bgn_de, 'to': end_de,
        'queriedAt': queried_at.isoformat(),
        'expiresAt': (queried_at + datetime.timedelta(hours=EVIDENCE_TTL_HOURS)).isoformat(),
        'parserVersion': PARSER_VERSION, 'contractVersion': CONTRACT_VERSION,
        'tickerMatched': True, 'structureVerified': False, 'ok': False,
        'apiStatus': None, 'httpStatus': None,
        'pagesExpected': None, 'pagesCollected': 0, 'totalCount': None,
        'collectedIds': [], 'findings': [], 'events': [], 'eventCounts': None,
        'listClassified': False, 'documentsInterpreted': False, 'uninterpreted': 0,
        'historicalBackfillComplete': False, 'unresolvedHistorical': 0,
        'responseRef': None, 'error': None,
        'comparisonScopeVersion': comparison.SCOPE_VERSION, 'comparisonFindings': []}
    if budget['left'] <= 0:
        base['error'] = 'REQUEST_BUDGET_EXHAUSTED'
        return base

    rows, pages_expected, digest = [], None, hashlib.sha256()
    page_no = 1
    while True:
        if budget['left'] <= 0:
            base['error'] = 'REQUEST_BUDGET_EXHAUSTED'
            return base
        daily = budget.get('daily')
        # 대기 가능한 작업이다 — 오늘 못 받은 증거는 내일 받을 수 있다. 그래서 재무(OPTIONAL)가 끊기는 선
        # (soft budget) 앞에 몫(dart_budget.DEFERRABLE_RESERVE)을 남기고 물러난다.
        # allow() 만 쓰면 이 요청은 'list'(ESSENTIAL)라 soft budget 에 전혀 걸리지 않았다(2026-09-22 발견).
        # 2026-09-23: 몫을 하드 상한 기준으로 재던 것을 soft budget 기준으로 고쳤다(재무보다 먼저 물러난다).
        if daily is not None and not daily.allow_for_deferrable('list'):
            base['error'] = dart_budget.DART_BUDGET_EXCEEDED
            return base
        budget['left'] -= 1
        if daily is not None:
            daily.spend('list')
        result = client.list_issuer_filings(corp_code, bgn_de, end_de, page_no=page_no)
        if result['status'] != dart_client.OK:
            # 전송 실패와 API 오류를 구분해 남긴다. 둘 다 0건이 아니다.
            base['error'] = result['status']
            base['apiStatus'] = str((result.get('data') or {}).get('status') or '') or None
            return base
        data = result.get('data') or {}
        base['apiStatus'] = str(data.get('status') or '')
        digest.update(json.dumps(data, ensure_ascii=False, sort_keys=True).encode('utf-8'))
        if result.get('noData'):
            # 013 = 그 조회 범위에 자료 없음. 대상·기간이 검증된 이 조회에 한해서만 0건이다.
            pages_expected, rows = 1, []
            base['pagesCollected'] = 1
            base['structureVerified'] = True
            break
        if not isinstance(data.get('list'), list) or 'total_page' not in data or 'total_count' not in data:
            base['error'] = 'RESPONSE_SHAPE_UNEXPECTED'      # 구조가 다르면 0건으로 읽지 않는다
            return base
        base['structureVerified'] = True
        pages_expected = int(data['total_page'] or 0)
        base['totalCount'] = int(data['total_count'] or 0)
        rows.extend(data['list'])
        base['pagesCollected'] = page_no
        if page_no >= max(pages_expected, 1):
            break
        page_no += 1

    base['pagesExpected'] = pages_expected if pages_expected is not None else 0
    if base['totalCount'] is None:
        base['totalCount'] = 0
    ids, findings, uninterpreted = [], [], 0
    for row in rows:
        rcept = str(row.get('rcept_no') or '')
        title = str(row.get('report_nm') or '')
        stock = str(row.get('stock_code') or '').strip()
        if not rcept or not title:
            uninterpreted += 1                 # 식별·제목이 없는 줄은 해석하지 못한 자료다
            continue
        if stock and stock != ticker:
            # 회사 단위 공시가 다른 종목코드를 가리키면 우리가 판단하지 않는다.
            uninterpreted += 1
            continue
        ids.append(rcept)
        # Reuse the same response for result safety; preserve all existing Private fields.
        if comparison.relevant(title):
            base['comparisonFindings'].append({'id': rcept, 'title': title,
                                               'receivedOn': str(row.get('rcept_dt') or '')})
        hit = _relevant(title)
        if hit:
            findings.append({'id': rcept, 'title': title, 'terms': hit,
                             'receivedOn': str(row.get('rcept_dt') or '')})
    base['collectedIds'] = ids
    base['findings'] = findings
    # 공시 건수를 사건 수로 세지 않는다. 정정은 같은 사건이고, 종속회사 사안은 이 주식의 사건이 아니다.
    summary = classify.summarize(findings)
    base['events'] = summary['events']
    base['eventCounts'] = {'openSelf': summary['openSelf'], 'subsidiary': summary['subsidiary'],
                           'documents': len(findings), 'needsDocument': summary['needsDocument'],
                           'companyDoneAwaitingExchange': summary['companyDoneAwaitingExchange'],
                           'fullyResolved': summary['fullyResolved'],
                           'events': len(summary['events'])}
    # 목록 분류는 끝났지만 본문 확인이 필요한 건은 '해석 완료' 가 아니다 — 소비자가 보류하게 한다.
    base['uninterpreted'] = uninterpreted + summary['needsDocument']
    base['listClassified'] = True
    base['documentsInterpreted'] = False      # 본문은 아직 한 건도 읽지 않았다
    # 이 회사 자신의 사건만, 사건 단위로 센다. 거래소 반영 확인 경로가 없어 종료보고서가 있어도 연다고 하지 않는다.
    base['unresolvedHistorical'] = summary['openSelf']
    base['historicalBackfillComplete'] = True
    base['responseRef'] = 'sha256:' + digest.hexdigest()
    base['ok'] = True
    return base


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', type=int, default=50, help='이번 회차에 볼 종목 수 상한')
    parser.add_argument('--requests', type=int, default=400, help='이번 회차 API 요청 수 상한')
    parser.add_argument('--require-complete', action='store_true',
                        help='전체 매핑 대상 갱신이 끝나지 않으면 실패로 종료한다')
    parser.add_argument('--days', type=int, default=BACKFILL_DAYS, help='과거 확인 범위(일)')
    parser.add_argument('--tickers-file', default=None,
                        help='채점 대상 중심 모드: 이 파일의 종목(한 줄 하나)만 본다. 커서를 건드리지 않는다. '
                             '파일이 비어 있으면 0종목을 처리한 것으로 적는다(전체 순회로 되돌아가지 않는다).')
    args = parser.parse_args(argv)

    daily = dart_budget.DailyBudget(BUDGET_FILE)
    # 시작 전에도 같은 기준으로 판단한다 — 재무가 끊기는 선(soft budget) 앞의 몫만 남았으면 아예 시작하지 않는다.
    if args.requests < 1 or not daily.allow_for_deferrable('mapping'):
        print(json.dumps({'ok': False, 'stage': 'budget',
                          'status': dart_budget.DART_BUDGET_EXCEEDED,
                          'remaining': daily.remaining,
                          'deferrableHeadroom': max(0, daily.deferrable_headroom()),
                          'deferrableCutoff': dart_budget.deferrable_cutoff(),
                          'deferrableReserve': dart_budget.DEFERRABLE_RESERVE}))
        return 2
    try:
        return _collect(args, daily)
    finally:
        # Mapping, failed requests and every page count toward the same existing
        # account budget used by the disclosure/financial collectors.
        daily.save()


def _collect(args, daily):

    client = dart_client.DartClient()
    daily.spend('mapping')
    corp_zip = client.corp_code_zip()
    if corp_zip['status'] != dart_client.OK:
        print(json.dumps({'ok': False, 'stage': 'corp_code', 'status': corp_zip['status'],
                          'error': corp_zip.get('error')}, ensure_ascii=False))
        return 2
    dart_rows = dart_pipeline.parse_corp_code_zip(corp_zip['data'])

    # 대상 범위: OpenDART 고유번호 목록(corpCode)에서 종목코드가 있는 회사 중 config/evidence_universe.json 에 적힌 것.
    # 옛 저장소는 KIND 상장법인목록(krx_list.json)을 읽었다 — 새 저장소는 KIND 자료를 쓰지 않는다.
    with open(UNIVERSE_FILE, encoding='utf-8') as handle:
        allowed = set(json.load(handle).get('codes') or [])
    universe = {}
    for row in dart_rows:
        code = str(row.get('stock_code') or '').strip()
        if len(code) == 6 and code.isdigit() and code in allowed:
            universe[code] = {'name': row.get('corp_name') or '', 'sector': None}
    corp_map = dart_pipeline.build_corp_map(dart_rows, universe)
    mapped = corp_map.get('mapped') or {}

    now = _today()
    # DART dates are Korean calendar dates. At 07:10 KST UTC still says
    # yesterday: ending there omits today's filings and fails at market open.
    # Keep the old start (never narrow history), extend only to the actual
    # Korean date, and preserve the real UTC queriedAt/20-hour expiry.
    korean_now = now.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    end_de, bgn_de = _ymd(korean_now), _ymd(now - datetime.timedelta(days=args.days))
    budget = {'left': args.requests - 1, 'daily': daily}
    # 진행 위치는 검증과 저장이 끝난 뒤에만 옮긴다. 중간에 끊겨도 다음 회차가 이어받는다.
    previous = {}
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE, encoding='utf-8') as handle:
            previous = json.load(handle)
    cursor = str((previous.get('cursor') or ''))
    order = sorted(mapped)
    # 대상 선정 — 기본은 커서 순회(기존 그대로), --tickers-file 이면 채점 후보만(커서 보존).
    file_codes = due_targets.read_tickers_file(args.tickers_file) if args.tickers_file else None
    target = due_targets.select_targets(order, cursor, args.tickers, file_codes)
    todo = target['todo']

    evidence = dict(previous.get('evidence') or {})
    done = []
    attempted = []
    reserve_reached = False
    for ticker in todo:
        attempted.append(ticker)
        record = collect_one(client, ticker, mapped[ticker]['corp_code'], bgn_de, end_de, budget)
        evidence[ticker] = record
        if record['ok']:
            done.append(ticker)
        # 중간 저장 — run 이 도중에 죽어도(60분 시간초과 취소 등, 2026-09-22 run 35732956954) 쓴 만큼은 원장에 남는다.
        # save() 는 증가분만 더하고 회차는 프로세스당 한 번만 세므로 몇 번을 저장해도 두 번 더해지지 않는다.
        if len(attempted) % CHECKPOINT_EVERY == 0:
            daily.save()
        # 대기 가능한 작업이다 — 몫(재무가 끊기기 전 여유)에 닿으면 **여기서 멈춘다.** 예전에는 daily.allow('list')
        # (필수 경로 기준)만 봐서 몫에 닿은 뒤에도 남은 종목 전부를 돌며 기존의 멀쩡한 증거를 DART_BUDGET_EXCEEDED
        # 실패 기록으로 덮어썼다(2026-09-23 발견). 남은 종목은 손대지 않고 notProcessed 로 센다.
        if not daily.allow_for_deferrable('list'):
            reserve_reached = True
            break
        if budget['left'] <= 0:
            break

    os.makedirs(OUT_DIR, exist_ok=True)
    # 파일 모드에서는 커서를 옮기지 않는다 — 전체 순회의 진행 위치는 그 모드의 것이다.
    rotation = target['mode'] == due_targets.MODE_ROTATION
    payload = {'contractVersion': CONTRACT_VERSION, 'generatedAt': now.isoformat(),
               'window': {'from': bgn_de, 'to': end_de,
                          'days': (korean_now.date() - (now - datetime.timedelta(days=args.days)).date()).days},
               'cursor': (done[-1] if done else cursor) if rotation else cursor,
               'universeMapped': len(mapped), 'attempted': len(todo), 'succeeded': len(done),
               'requestsUsed': args.requests - budget['left'],
               'targetMode': target['mode'],
               'targetRequested': target['requested'],
               'notInUniverse': len(target['notInUniverse']),
               'efficiency': client.efficiency_report(), 'evidence': evidence}
    with open(OUT_FILE, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
    summary = {k: payload[k] for k in ('attempted', 'succeeded', 'requestsUsed', 'universeMapped',
                                       'targetMode', 'targetRequested', 'notInUniverse')}
    summary['withDocuments'] = sum(1 for t in done if evidence[t]['findings'])
    summary['withOpenEvent'] = sum(1 for t in done if evidence[t]['unresolvedHistorical'])
    summary['subsidiaryOnly'] = sum(1 for t in done if evidence[t]['findings']
                                    and not evidence[t]['unresolvedHistorical'])
    summary['clean'] = sum(1 for t in done if not evidence[t]['findings'])
    # 예산이 떨어져 손도 못 댄 종목을 실패로 세지 않는다(2026-09-15 수리).
    # 실제로 시도한 것만 분모로 쓰고, 못 댄 것은 notProcessed 로 따로 남긴다.
    summary['failed'] = len(attempted) - len(done)
    summary['notProcessed'] = len(todo) - len(attempted)
    summary['notProcessedReason'] = ((('daily_reserve_reached' if reserve_reached else 'budget_exhausted_before_attempt'))
                                     if len(todo) > len(attempted) else None)
    print(json.dumps(summary, ensure_ascii=False))
    if args.require_complete and (not order or len(done) != len(order) or len(done) != len(todo)):
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
