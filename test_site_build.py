#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공개 사이트 조립 계약 (2026-09-26 초보자 화면 개편) — 네트워크 0 · 저장소 안 자료만.

① 홈의 숫자는 contract.json 의 실제 값뿐이다(지어낸 숫자 0).
② 「최근 접수된 공시」 카드: 회사당 1장 · 중요도 순위라고 하지 않는다 · 같은 날 여러 건이면 건수와 「모두 보기」 링크.
   설명은 공시 사전(content/disclosure_guide.json · 가장 긴 제목 낱말)이 붙이고, 사전에 없으면 주 분류의 일반적인 읽는 법만 쓴다.
   제목이 "A또는B" 처럼 스스로 애매하면 한 가지 읽는 법을 고르지 않는다. 분류는 공시 연구 생산자와 같은 disclosure_classify 모듈이다.
③ 기업 한눈에 보기 요약은 결측을 0 으로 만들지 않고(NOT_COLLECTED 그대로), 판단·시세 키가 없다.
④ 공부 글 연결표의 글 번호는 실제 글이다. 모든 쪽에 메뉴가 미리 그려져 있다(자바스크립트 없이도 보임).
⑤ (2026-09-28) 글 본문은 1~2문장 문단으로 끊고 **굵게**는 그대로 둔다. 옛 사이트가 색인시킨 공부 글 주소(/snap/…)가
   살아 있고 sitemap·rss·robots(다음 확인 줄)·IndexNow 키가 있다. 공시 사전·회사 쪽이 만들어지고 얇은 회사 쪽은 색인하지 않는다.
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

    def test_최근_접수된_공시_카드(self):
        section = re.search(r'<section class="section" aria-labelledby="today-title">.*?</section>', self.home, re.S).group(0)
        self.assertIn('<h2 id="today-title">최근 접수된 공시</h2>', section)
        self.assertIn('중요도 순위가 아닙니다', section)
        self.assertNotIn('오늘', section)   # 여러 날 자료를 「오늘」이라고 부르지 않는다
        cards = re.findall(r'<article class="card change-card">.*?</article>', section, re.S)
        self.assertTrue(1 <= len(cards) <= 6, len(cards))
        codes = [re.search(r'/company/(\d{6})/', c).group(1) for c in cards]
        self.assertEqual(len(codes), len(set(codes)), '회사당 카드 1장')
        for card in cards:
            self.assertIn('href="/company/', card)
            self.assertIn('무슨 내용인가요?', card)
            self.assertIn('왜 확인할까요?', card)
            self.assertNotIn('대표 공시', card)
        # 금지 어휘는 자동으로 만든 카드 내용에서 본다(홈의 안내문 "매수·매도 추천 없음" 같은 부정문은 대상이 아니다).
        for phrase in FORBIDDEN_TEXT:
            self.assertNotIn(phrase, ''.join(cards), phrase)

    def _today(self, items):
        with open(os.path.join(HERE, 'config', 'disclosure_research_vocab.json'), encoding='utf-8') as fh:
            cats = json.load(fh)['categories']
        dart = {'items': items, 'generatedAt': '2026-09-25 00:00'}
        contract = dict(self.contract, companyNames={it['code']: it['name'] for it in items})
        today = build_site.home_sections(contract, dart, {'categories': cats}, [], [])['TODAY']
        cards = re.findall(r'<article class="card change-card">.*?</article>', today, re.S)
        return {re.search(r'/company/(\d{6})/', c).group(1): c for c in cards}, cats

    def test_같은_날_여러_공시는_건수와_모두_보기_링크(self):
        base = {'code': '000001', 'name': '합성', 'receiptDate': '20260925', 'isCorrection': False}
        cards, _ = self._today([
            dict(base, title='단일판매ㆍ공급계약체결', rceptNo='20260925000001', detectedAt='2026-09-25T02:00:00+00:00'),
            dict(base, title='주식등의대량보유상황보고서', rceptNo='20260925000002', detectedAt='2026-09-25T01:00:00+00:00'),
            dict(base, title='기업설명회(IR)개최', rceptNo='20260925000003', detectedAt='2026-09-25T00:00:00+00:00'),
            dict(base, title='분기보고서', receiptDate='20260924', rceptNo='20260924000001', detectedAt='2026-09-24T00:00:00+00:00')])
        self.assertEqual(list(cards), ['000001'])                       # 회사당 카드 1장
        card = cards['000001']
        self.assertIn('같은 날 공시 3건', card)                          # 다른 날(24일) 공시는 세지 않는다
        self.assertIn('href="/disclosure-research.html?code=000001&amp;tab=today">같은 날 공시 3건 모두 보기', card)
        self.assertIn('단일판매ㆍ공급계약체결', card)                     # 같은 날 가운데 GAEO 가 가장 나중에 모은 것
        one, _ = self._today([dict(base, title='분기보고서', rceptNo='20260925000009')])
        self.assertNotIn('같은 날 공시', one['000001'])

    def test_두_성격은_주_분류와_보조_태그_애매하면_한_가지_읽는_법_없음(self):
        base = {'name': '합성', 'receiptDate': '20260925', 'isCorrection': False}
        cards, cats = self._today([
            dict(base, code='000001', title='특수관계인으로부터자산양수', rceptNo='20260925000001'),
            dict(base, code='000002', title='증권발행실적보고서', rceptNo='20260925000002'),
            dict(base, code='000003', title='유상증자또는주식관련사채등의발행결과(자율공시)', rceptNo='20260925000003')])
        self.assertIn(f'<span class="cc-cat">{cats["merger_split"]["label"]}</span>', cards['000001'])
        self.assertIn(f'<span class="chip neutral">{cats["group"]["label"]}</span>', cards['000001'])
        self.assertIn(f'<span class="cc-cat">{cats["securities_filing"]["label"]}</span>', cards['000002'])
        self.assertIn('href="/guide/issuance-results/">쉬운 이름 · 새로 판 증권이 얼마나 팔렸는지 알리는 결과 보고', cards['000002'])   # 사전(증권발행실적보고서)
        self.assertNotIn(cats['earnings']['howToRead']['why'].split('.')[0], cards['000002'])       # '실적' 낱말에 끌려가지 않는다
        self.assertIn('둘 중 어느 쪽인지 알 수 없어서', cards['000003'])                              # 애매한 제목은 애매하다고 말한다
        self.assertNotIn(cats['capital_increase']['howToRead']['why'].split('.')[0], cards['000003'])

    def test_분류는_공시_연구_생산자와_같은_모듈이다(self):
        import build_disclosure_research as producer
        import disclosure_classify
        self.assertIs(build_site.disclosure_classify, disclosure_classify)
        with open(os.path.join(HERE, 'config', 'disclosure_research_vocab.json'), encoding='utf-8') as fh:
            cats = json.load(fh)['categories']
        dart = build_site.read_js_object('dart_today.js', 'DART_TODAY')
        for it in dart['items']:
            self.assertEqual(disclosure_classify.category_of(it['title'], cats), producer.category_of(it['title'], cats), it['title'])

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

    def test_문단은_1_2문장씩_끊고_굵게는_그대로(self):
        html_ = build_site.md_html('## 소제목\n**핵심이에요.** 첫 문장이에요. 둘째는 1.5조 원이에요. 셋째는 Inc. 이야기예요.\n'
                                   '- **굵은 항목**: 설명이에요. 덧붙임이에요. 또 덧붙임이에요.\n3. 셋째 줄이에요')
        self.assertIn('<h2>소제목</h2>', html_)
        self.assertIn('<p><b>핵심이에요.</b></p>', html_)                       # 통째로 굵은 문장은 한 줄로 따로
        self.assertIn('<p>첫 문장이에요. 둘째는 1.5조 원이에요.</p>', html_)      # 두 문장씩 · 숫자의 점에서 안 끊음
        self.assertIn('<p>셋째는 Inc. 이야기예요.</p>', html_)                   # 영문 약어에서 안 끊음
        self.assertIn('<li><b>굵은 항목</b>: 설명이에요. 덧붙임이에요.<p>또 덧붙임이에요.</p></li>', html_)
        self.assertIn('<ol start="3"><li>셋째 줄이에요</li></ol>', html_)
        self.assertEqual(build_site.split_sentences('그는 "좋아요." 라고 했어요. 다음이에요.'), ['그는 "좋아요." 라고 했어요.', '다음이에요.'])

    def test_옛_색인_주소와_검색엔진_파일(self):
        content = build_site.load_content()
        with open(os.path.join(self.out, 'sitemap.xml'), encoding='utf-8') as fh:
            sitemap = fh.read()
        for kind, (var, *_rest) in build_site.SECTIONS.items():
            for it in content[var]:
                rel = f'snap/{kind}/{it["id"]}.html'
                with open(os.path.join(self.out, rel), encoding='utf-8') as fh:
                    page = fh.read()
                self.assertIn(f'<link rel="canonical" href="https://gaeoteam.com/{rel}">', page)
                self.assertIn(f'<loc>https://gaeoteam.com/{rel}</loc>', sitemap)
        self.assertFalse(os.path.exists(os.path.join(self.out, 'snap', 'stock')))   # 옛 시세 스냅샷은 되살리지 않는다
        self.assertFalse(os.path.exists(os.path.join(self.out, 'snap', 'news')))
        with open(os.path.join(self.out, 'robots.txt'), encoding='utf-8') as fh:
            robots = fh.read()
        self.assertIn(build_site.DAUM_VERIFY, robots)
        self.assertIn('Sitemap: https://gaeoteam.com/sitemap.xml', robots)
        import xml.etree.ElementTree as ET
        items = ET.parse(os.path.join(self.out, 'rss.xml')).getroot().findall('./channel/item')
        self.assertTrue(10 <= len(items) <= 60, len(items))
        with open(os.path.join(self.out, build_site.INDEXNOW_KEY + '.txt'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), build_site.INDEXNOW_KEY)

    def test_공시_사전과_회사_쪽(self):
        guides = build_site.load_guides()['guides']
        lessons = {x['id'] for x in build_site.content_meta('content/stock_lessons.js')}
        blob = json.dumps(guides, ensure_ascii=False)
        for phrase in FORBIDDEN_TEXT:
            self.assertNotIn(phrase, blob, phrase)
        self.assertEqual(len({g['key'] for g in guides}), len(guides))
        for g in guides:
            self.assertTrue(g['name'] and g['plain'] and g['what'] and g['why'] and g['check'], g['key'])
            self.assertTrue(g.get('lesson') is None or g['lesson'] in lessons, g['key'])
            self.assertTrue(os.path.exists(os.path.join(self.out, 'guide', g['key'], 'index.html')), g['key'])
        with open(os.path.join(self.out, 'sitemap.xml'), encoding='utf-8') as fh:
            sitemap = fh.read()
        for code in self.contract['companyNames']:
            with open(os.path.join(self.out, 'company', code, 'index.html'), encoding='utf-8') as fh:
                page = fh.read()
            thin = 'noindex' in page
            self.assertEqual(f'/company/{code}/</loc>' in sitemap, not thin, code)
            body = page.replace('매수·매도 추천', '')   # 「매수·매도 추천 아님」 같은 부정 안내문은 대상이 아니다
            for phrase in FORBIDDEN_TEXT:
                self.assertNotIn(phrase, body, (code, phrase))

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
