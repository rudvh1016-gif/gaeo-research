#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공개 사이트 조립 계약 (2026-09-26 초보자 화면 개편) — 네트워크 0 · 저장소 안 자료만.

① 홈의 숫자는 contract.json 의 실제 값뿐이다(지어낸 숫자 0).
② 오늘의 변화 카드의 "왜 확인할까요?" 는 공시 분류표의 일반적인 읽는 법만 쓴다. 제목이 두 분류에 걸리면
   한 가지 읽는 법을 붙이지 않는다(예: 증권발행'실적'보고서가 실적 공시 설명을 받던 오해 방지).
③ 기업 한눈에 보기 요약은 결측을 0 으로 만들지 않고(NOT_COLLECTED 그대로), 판단·시세 키가 없다.
④ 공부 글 연결표의 글 번호는 실제 글이다. 모든 쪽에 메뉴가 미리 그려져 있다(자바스크립트 없이도 보임).
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
import build_site  # noqa: E402
from test_disclosure_research import FORBIDDEN_KEYS, FORBIDDEN_TEXT  # noqa: E402


def _keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v)


class BuiltSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='gaeo-site-')
        cls.out = os.path.join(cls.tmp, '_site')
        build_site.build(cls.out)
        with open(os.path.join(cls.out, 'index.html'), encoding='utf-8') as fh:
            cls.home = fh.read()
        with open(os.path.join(cls.out, 'assets', 'research-summary.json'), encoding='utf-8') as fh:
            cls.summary = json.load(fh)
        with open(os.path.join(HERE, 'disclosure_research', 'contract.json'), encoding='utf-8') as fh:
            cls.contract = json.load(fh)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_홈_숫자는_contract_값뿐이다(self):
        files = {f['kind']: f for f in self.contract['files']}
        strip = re.search(r'<dl class="facts-strip".*?</dl>', self.home, re.S).group(0)
        values = re.findall(r'<dd>([^<]*)</dd>', strip)
        self.assertEqual(values[:4], [self.contract['asOf'], f"{len(self.contract['companyNames']):,}곳",
                                      f"{files['financial_changes']['companies']:,}곳", f"{files['event_timelines']['companies']:,}곳"])
        self.assertNotIn('<!--HOME:', self.home)

    def test_오늘의_변화_카드(self):
        cards = re.findall(r'<article class="card change-card">.*?</article>', self.home, re.S)
        self.assertTrue(1 <= len(cards) <= 6, len(cards))
        for card in cards:
            self.assertIn('href="/disclosure-research.html?code=', card)
            self.assertIn('무슨 내용인가요?', card)
            self.assertIn('왜 확인할까요?', card)
        # 금지 어휘는 자동으로 만든 카드 내용에서 본다(홈의 안내문 "매수·매도 추천 없음" 같은 부정문은 대상이 아니다).
        for phrase in FORBIDDEN_TEXT:
            self.assertNotIn(phrase, ''.join(cards), phrase)

    def test_두_분류에_걸린_제목은_한_가지_읽는_법을_받지_않는다(self):
        with open(os.path.join(HERE, 'config', 'disclosure_research_vocab.json'), encoding='utf-8') as fh:
            cats = json.load(fh)['categories']
        title = '증권발행실적보고서'
        self.assertEqual(build_site.categories_of(title, cats), ['earnings', 'securities_filing'])
        dart = {'items': [{'code': '000001', 'name': '합성', 'title': title, 'receiptDate': '20260925',
                           'rceptNo': '20260925000001', 'isCorrection': False}], 'generatedAt': '2026-09-25 00:00'}
        contract = dict(self.contract, companyNames={'000001': '합성'})
        today = build_site.home_sections(contract, dart, {'categories': cats}, [], [])['TODAY']
        self.assertNotIn(cats['earnings']['howToRead']['why'].split('.')[0], today)
        self.assertIn('한 가지 읽는 법을 고르지 않았어요', today)

    def test_분류_규칙은_공시_연구_생산자와_같다(self):
        import build_disclosure_research as producer
        with open(os.path.join(HERE, 'config', 'disclosure_research_vocab.json'), encoding='utf-8') as fh:
            cats = json.load(fh)['categories']
        dart = build_site.read_js_object('dart_today.js', 'DART_TODAY')
        for it in dart['items']:
            self.assertEqual(build_site.category_of(it['title'], cats), producer.category_of(it['title'], cats), it['title'])

    def test_요약은_결측을_0으로_만들지_않고_판단_키가_없다(self):
        with open(os.path.join(HERE, 'disclosure_research', 'financial_changes.json'), encoding='utf-8') as fh:
            fin = json.load(fh)
        comp = self.summary['companies']
        for code in fin.get('notCollectedTickers') or []:
            if code in comp:
                self.assertEqual(comp[code].get('financial'), {'state': 'NOT_COLLECTED'}, code)
        self.assertEqual(set(comp), set(self.contract['companyNames']))
        self.assertEqual(set(_keys(self.summary)) & FORBIDDEN_KEYS, set())
        for phrase in FORBIDDEN_TEXT:
            self.assertNotIn(phrase, json.dumps(self.summary, ensure_ascii=False), phrase)

    def test_공부_글_연결표는_실제_글을_가리킨다(self):
        lessons = {x['id'] for x in build_site.content_meta('content/stock_lessons.js')}
        for ids in list(build_site.LESSONS_BY_CATEGORY.values()) + [build_site.BASIC_LESSONS]:
            for i in ids:
                self.assertIn(i, lessons, i)
        self.assertTrue(all(len(v) == len(build_site.LESSONS_BY_CATEGORY[k]) for k, v in self.summary['lessons'].items()))

    def test_모든_쪽에_메뉴와_꼬리말이_미리_그려져_있다(self):
        for d, _, files in os.walk(self.out):
            for f in files:
                if f.endswith('.html'):
                    with open(os.path.join(d, f), encoding='utf-8') as fh:
                        text = fh.read()
                    self.assertNotIn('<header id="site-head"></header>', text, f)
                    self.assertIn('<nav class="nav" aria-label="주 메뉴">', text, f)
                    self.assertNotIn('<footer id="site-foot"></footer>', text, f)


if __name__ == '__main__':
    unittest.main(verbosity=2)
