#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공시 연구 산출물(build_disclosure_research.py) · 오늘의 공시(build_dart_today.py) · 공개 화면 계약 (2026-09-24).

무엇을 지키나
    · 결측은 0 이 아니다 — NOT_COLLECTED / NOT_APPLICABLE 로 적히고, 못 찾은 단계는 NOT_FOUND(≠ 미실행)다.
    · 연결/별도가 다른 연도 쌍은 비교하지 않는다. 전년 0 이하면 증감률을 만들지 않는다.
    · 공개 산출물·화면에 판단 어휘(매수/매도/저평가/위험기업/회계부정 …)와 시세·점수 키가 없다.
    · contract.json 의 sha256·recordId 가 실제 파일과 맞는다(Private 가 그 값으로 인수 기록을 남긴다).
    · 화면은 CDN 을 로드하지 않고 원문 링크·출처·자료 공급 종료 문구가 있다.
표준 라이브러리만 사용.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import unittest

import build_dart_today as DT
import build_disclosure_research as B

HERE = os.path.dirname(os.path.abspath(__file__))
# 소유자 지시 §5 의 금지 문구 그대로(부정문 '회계부정 여부를 단정하지 않는다' 는 금지가 아니다) + 판단 신호 낱말
FORBIDDEN_TEXT = ('상승 확정', '매수 기회 확정', '곧 오른다', '저평가 확정', '회계부정 단정', '위험기업 낙인', '검증된 고수익', 'AI들이 토론했다', '"BUY"', '"SELL"', '"HOLD"', '매수 추천', '매도 추천')
FORBIDDEN_KEYS = {'price', 'close', 'score', 'signal', 'verdict', 'buy', 'sell', 'hold', 'consensus', 'flow', 'holding', 'accountNo', 'accountSeq', 'memo', 'return', 'target'}

UNIVERSE = {'000100': {'name': '유한양행', 'sector': '제약'}, '000660': {'name': 'SK하이닉스', 'sector': '반도체'},
            '069260': {'name': 'TKG휴켐스', 'sector': '화학'}}


def _fixture(root):
    seen = {'seen': {
        '20260915800321': {'ticker': '000100', 'report_name': '단일판매ㆍ공급계약체결', 'detected_at': '2026-09-15T01:00:00+00:00'},
        '20260908800264': {'ticker': '000100', 'report_name': '기업설명회(IR)개최(안내공시)', 'detected_at': '2026-09-08T01:00:00+00:00'},
        '20260820800100': {'ticker': '000100', 'report_name': '기업설명회(IR)개최(안내공시)', 'detected_at': '2026-08-20T01:00:00+00:00'},
        '20260901800001': {'ticker': '000660', 'report_name': '[기재정정]자기주식취득결정', 'detected_at': '2026-09-01T01:00:00+00:00'},
        '20260819800002': {'ticker': '000660', 'report_name': '자기주식취득결정', 'detected_at': '2026-08-19T01:00:00+00:00'},
        '20260901800003': {'ticker': '999999', 'report_name': '추적 종목 아님', 'detected_at': '2026-09-01T01:00:00+00:00'},
    }}
    os.makedirs(os.path.join(root, 'dart'), exist_ok=True)
    with open(os.path.join(root, 'dart', 'seen_rcept.json'), 'w', encoding='utf-8') as f:
        json.dump(seen, f)
    evidence = {'evidence': {
        '000660': {'comparisonFindings': [{'id': '20260819800002', 'receivedOn': '20260819', 'title': '자기주식취득결정   '},
                                          {'id': '20260701800009', 'receivedOn': '20260701', 'title': '유상증자결정'}]},
        '000100': {'comparisonFindings': []},
    }}
    with open(os.path.join(root, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(evidence, f)
    fin = os.path.join(root, 'fin')
    os.makedirs(fin, exist_ok=True)
    def year(status, fs, values, missing=(), na=()):
        return {'status': status, 'fsDiv': fs, 'reprtCode': '11011', 'collectedAt': '2026-09-14T04:10:11+00:00',
                'coverage': 0.9, 'values': values, 'missing': list(missing), 'notApplicable': list(na)}
    with open(os.path.join(fin, '000100.json'), 'w', encoding='utf-8') as f:
        json.dump({'ticker': '000100', 'years': {
            '2023': year('OK', 'CFS', {'revenue': 100, 'operatingIncome': -5, 'totalLiabilities': 50, 'totalEquity': 100}),
            '2024': year('OK', 'CFS', {'revenue': 110, 'operatingIncome': 10, 'totalLiabilities': 60, 'totalEquity': 100, 'interestExpense': 'NOT_AVAILABLE'}, missing=['interestExpense']),
            '2025': year('OK', 'OFS', {'revenue': 90, 'operatingIncome': 9, 'totalLiabilities': 70, 'totalEquity': 100}, na=['currentAssets']),
        }}, f)
    with open(os.path.join(fin, '000660.json'), 'w', encoding='utf-8') as f:
        json.dump({'ticker': '000660', 'years': {'2025': {'status': 'NO_DATA', 'checkedAt': 'x'}}}, f)
    return root


class Builder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        _fixture(self.tmp)
        import datetime as dt
        self.docs, self.blobs = B.build_all(
            universe=UNIVERSE, vocab=B.load_vocab(), as_of='2026-09-23',
            now=dt.datetime(2026, 9, 23, 14, 0, tzinfo=dt.timezone.utc),
            fin_dir=os.path.join(self.tmp, 'fin'), seen_path=os.path.join(self.tmp, 'dart', 'seen_rcept.json'),
            evidence_path=os.path.join(self.tmp, 'evidence.json'))

    def test_계약_파일의_sha_와_recordId_가_실제_파일과_맞는다(self):
        c = self.docs['contract']
        self.assertEqual(c['schemaVersion'], B.SCHEMA_VERSION)
        self.assertEqual(c['contractVersion'], B.CONTRACT_VERSION)
        self.assertEqual({f['kind'] for f in c['files']}, set(B.KINDS))
        for f in c['files']:
            sha = hashlib.sha256(self.blobs[f['kind']]).hexdigest()
            self.assertEqual(f['sha256'], sha)
            self.assertEqual(f['bytes'], len(self.blobs[f['kind']]))
            self.assertEqual(f['recordId'], f"{B.CONTRACT_VERSION}:{f['kind']}:{sha[:16]}")
            self.assertEqual(f['companies'], len(self.docs[f['kind']]['companies']))
        self.assertEqual(c['companyNames'], {'000100': '유한양행', '000660': 'SK하이닉스', '069260': 'TKG휴켐스'})
        self.assertTrue(c['notIncluded'])

    def test_공시_변화_창과_변화_문장(self):
        d = self.docs['disclosure_changes']
        self.assertEqual(d['kind'], 'disclosure_changes')
        w = d['windows']
        self.assertEqual(w['coverageFrom'], '2026-08-19')          # list 자료 시작
        self.assertEqual(w['recent']['to'], '2026-09-23')
        self.assertEqual(w['recent']['days'], w['prior']['days'])
        yh = d['companies']['000100']
        self.assertEqual(yh['filingCount'], 3)
        self.assertEqual(yh['latestReceivedOn'], '2026-09-15')
        self.assertEqual({c['type'] for c in yh['changes']} & {'NEW_CATEGORY', 'RECENT_ONLY', 'SAME', 'MORE', 'FEWER'} != set(), True)
        for f in yh['filings']:
            self.assertTrue(f['url'].startswith('https://dart.fss.or.kr/'))
            self.assertIn('list', f['sources'])
        self.assertNotIn('999999', d['companies'])                  # 추적 종목 아님

    def test_정정_공시는_정정으로_표시되고_출처가_합쳐진다(self):
        d = self.docs['disclosure_changes']['companies']['000660']
        by = {f['rceptNo']: f for f in d['filings']}
        self.assertTrue(by['20260901800001']['isCorrection'])
        self.assertEqual(by['20260901800001']['correctionKind'], '기재정정')
        self.assertEqual(sorted(by['20260819800002']['sources']), ['evidence', 'list'])
        self.assertEqual(by['20260701800009']['sources'], ['evidence'])
        self.assertEqual(d['filingCount'], 3)

    def test_재무_결측은_0이_아니고_연결_별도를_섞지_않는다(self):
        d = self.docs['financial_changes']
        self.assertEqual(d['targetYears'], ['2023', '2024', '2025'])
        c = d['companies']['000100']
        self.assertEqual(c['comparablePairs'], [{'from': '2023', 'to': '2024'}])     # 2024 CFS → 2025 OFS 는 비교 안 함
        self.assertEqual(c['correctionsApplied'], 'UNKNOWN')
        rows = {r['account']: r for r in c['rows']}
        self.assertEqual(rows['currentAssets']['values']['2025'], 'NOT_APPLICABLE')
        self.assertIn('2024', rows['interestExpense']['missing'])          # NOT_AVAILABLE 은 값이 아니라 결측
        self.assertNotIn('2024', rows['interestExpense']['values'])
        self.assertEqual(rows['revenue']['changes']['2024'], {'abs': 10, 'pct': 10.0, 'pctReason': None, 'vs': '2023'})
        self.assertEqual(rows['operatingIncome']['changes']['2024']['pct'], None)      # 전년 음수
        self.assertEqual(rows['operatingIncome']['changes']['2024']['pctReason'], 'prior_zero_or_negative')
        self.assertEqual(c['derived']['2024'], {'operatingMarginPct': 9.1, 'debtToEquityPct': 60.0})
        self.assertEqual(c['derived']['2023']['operatingMarginPct'], -5.0)     # 음수 영업이익률은 그대로(0 아님)
        self.assertTrue(any('연결/별도' in n for n in c['notes']))
        # NO_DATA 만 있는 회사·파일 없는 회사 = NOT_COLLECTED, 0 이 아니다
        self.assertNotIn('000660', d['companies'])
        self.assertEqual(sorted(d['notCollectedTickers']), ['000660', '069260'])
        self.assertEqual(d['coverage'], {'trackedCompanies': 3, 'companiesCollected': 1, 'companiesWithRows': 1,
                                          'notCollected': 2, 'notCollectedNote': d['coverage']['notCollectedNote']})

    def test_타임라인_못_찾은_단계는_NOT_FOUND_이지_미실행이_아니다(self):
        d = self.docs['event_timelines']
        c = d['companies']['000660']
        chains = {t['chain']: t for t in c['timelines']}
        self.assertIn('buyback', chains)
        bb = chains['buyback']
        self.assertEqual([i['stage'] for i in bb['items']], ['PLANNED', 'PLANNED'])
        self.assertTrue(bb['items'][1]['isCorrection'])
        self.assertEqual(bb['stagesSeen'], ['PLANNED'])
        self.assertEqual([s['stage'] for s in bb['stagesNotFound']], ['REPORTED', 'COMPLETED'])
        for s in bb['stagesNotFound']:
            self.assertEqual(s['state'], 'NOT_FOUND')
            self.assertIn('미실행이 아니다', s['meaning'])
        self.assertEqual(bb['latestStage'], 'PLANNED')
        self.assertIn('capital_increase', chains)
        self.assertNotIn('000100', d['companies'])                  # 사슬 공시 없음 → 파일에 없음(0 아님)

    def test_공개_산출물에_판단_어휘와_시세_키가_없다(self):
        for kind, blob in self.blobs.items():
            text = blob.decode('utf-8')
            for phrase in FORBIDDEN_TEXT:
                self.assertNotIn(phrase, text, (kind, phrase))
            keys = set(re.findall(r'"([A-Za-z][A-Za-z0-9_]*)"\s*:', text))
            self.assertEqual(keys & FORBIDDEN_KEYS, set(), kind)


class RealOutputs(unittest.TestCase):
    """저장소에 커밋된 산출물이 계약과 맞는가(생산자가 실제로 돌았다는 증거)."""

    def test_커밋된_산출물의_sha_가_계약과_맞는다(self):
        d = os.path.join(HERE, 'disclosure_research')
        if not os.path.isfile(os.path.join(d, 'contract.json')):
            self.skipTest('산출물 없음')
        with open(os.path.join(d, 'contract.json'), encoding='utf-8') as fh:
            c = json.load(fh)
        for f in c['files']:
            with open(os.path.join(HERE, f['file']), 'rb') as fh:
                blob = fh.read()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), f['sha256'], f['file'])
            doc = json.loads(blob)
            self.assertEqual(doc['kind'], f['kind'])
            self.assertEqual(doc['contractVersion'], B.CONTRACT_VERSION)
            self.assertEqual(len(doc['companies']), f['companies'])


class DartToday(unittest.TestCase):
    def test_종목당_최근_3건_7일_창_정정_표시(self):
        import datetime as dt
        seen = {}
        for i in range(5):
            seen[f'2026091{i}800001'] = {'ticker': '000100', 'report_name': f'공시 {i}', 'detected_at': f'2026-09-1{i}T01:00:00+00:00'}
        seen['20260830800001'] = {'ticker': '000100', 'report_name': '[정정] 오래된 공시', 'detected_at': '2026-08-30T01:00:00+00:00'}
        seen['20260914800002'] = {'ticker': '999999', 'report_name': '추적 아님', 'detected_at': '2026-09-14T01:00:00+00:00'}
        out = DT.build(seen, {'000100': '유한양행'}, {'eventState': 'EVENT_DETECTED'},
                       now_kst=dt.datetime(2026, 9, 24, 7, 0, tzinfo=dt.timezone(dt.timedelta(hours=9))))
        self.assertEqual(out['count'], 3)
        self.assertEqual([i['receiptDate'] for i in out['items']], ['20260914', '20260913', '20260912'])
        self.assertEqual(out['coverageState'], 'EVENT_DETECTED')
        self.assertEqual(out['generatedAt'], '2026-09-24 07:00')
        self.assertIn('시세 자료 공급 종료', out['priceLabel'])
        self.assertTrue(all(i['name'] == '유한양행' for i in out['items']))
        out2 = DT.build({'20260830800001': seen['20260830800001']}, {'000100': '유한양행'}, {'eventState': 'EVENT_DATA_ERROR'})
        self.assertTrue(out2['items'][0]['isCorrection'])
        self.assertEqual(out2['coverageState'], 'SOURCE_UNAVAILABLE')


class PublicPage(unittest.TestCase):
    """새 공개 사이트(site/)의 기업 리서치 화면 계약. 읽는 순서: 무슨 일 → 왜 → 모르는 것 → 다음 확인 → DART 원문."""
    HTML = os.path.join(HERE, 'site', 'disclosure-research.html')
    JS = os.path.join(HERE, 'site', 'assets', 'disclosure-research.js')

    def test_화면_계약(self):
        with open(self.HTML, encoding='utf-8') as fh:
            html = fh.read()
        with open(self.JS, encoding='utf-8') as fh:
            js = fh.read()
        for needle in ('id="view-today"', 'id="view-changes"', 'id="view-financial"', 'id="view-timeline"', '/disclosure_research/contract.json',
                       'rel="canonical" href="https://gaeoteam.com/disclosure-research.html"', 'DART'):
            self.assertIn(needle, html, needle)
        for host in ('cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com', 'googlesyndication', 'googletagmanager'):
            self.assertNotIn(host, html, host)
        for phrase in FORBIDDEN_TEXT:
            self.assertNotIn(phrase, html, phrase)
            self.assertNotIn(phrase, js, phrase)
        for needle in ('무슨 일이 있었어?', '왜 볼 필요가 있어?', '아직 모르는 건?', '다음에 확인할 건?', 'DART에서 직접 보기',
                       'NOT_COLLECTED', 'NOT_APPLICABLE', '미실행', '정정'):
            self.assertTrue(needle in js, f'disclosure-research.js 에 {needle!r} 가 없다')
        self.assertNotIn('http://', js)

    def test_홈에서_링크된다(self):
        with open(os.path.join(HERE, 'site', 'index.html'), encoding='utf-8') as fh:
            index = fh.read()
        self.assertIn('href="/disclosure-research.html"', index)


if __name__ == '__main__':
    unittest.main()
