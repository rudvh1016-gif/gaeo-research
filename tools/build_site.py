#!/usr/bin/env python3
"""공개 사이트 조립기 (네트워크 0 · LLM 0).

GitHub Pages 에 올라가는 것은 이 스크립트가 만든 _site/ **뿐**이다. 저장소의 나머지(수집기 코드·원장·
원문 아카이브·재무 원자료·문서)는 사이트 주소로 나가지 않는다. 무엇을 싣는지는 아래 허용목록이 정한다.

  site/                     손으로 쓴 화면(html·css·js·이미지·서체)
  content/*.js · *.json     공부 글·계산기·과거 분석 세척본
  dart_today.js             오늘의 공시(수집기 산출물)
  disclosure_research/*.json 공시 연구 산출물(수집기 산출물)

과거 정밀분석 쪽(content/past_analysis.json)은 여기서 정적 html 로 만든다. 옛 주소
/research/deep-analysis/<종목>/<시각>/ 을 그대로 쓴다(옛 링크 유지) · 목록은 /past-analysis/ 와 같은 내용.
사용: python3 tools/build_site.py [출력 폴더(기본 _site)]
환경변수 BASE_PATH(예: /gaeo-research): 커스텀 도메인 연결 전 임시 주소(https://<계정>.github.io/<저장소>/)에서도
링크가 맞도록 html·js 의 사이트 절대경로 앞에 붙인다. 커스텀 도메인이면 빈 값.
"""
import re
import html
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'https://gaeoteam.com'
DATA_FILES = ['dart_today.js', 'disclosure_research/contract.json', 'disclosure_research/disclosure_changes.json',
              'disclosure_research/financial_changes.json', 'disclosure_research/event_timelines.json']
CONTENT_FILES = ['content/stock_study.js', 'content/stock_lessons.js', 'content/estate_lessons.js',
                 'content/calculators.js', 'content/past_analysis.json']
STATIC_PAGES = ['', 'disclosure-research.html', 'past-analysis/', 'study.html', 'learn.html', 'calculators.html',
                'about.html', 'disclaimer.html', 'privacy.html', 'contact.html']
e = html.escape

# 머리말 메뉴 — site/assets/site.js 의 NAV 와 같은 순서(자바스크립트가 꺼져도 보이게 빌드 때 미리 그린다).
NAV = [('/', '홈', 'home'), ('/disclosure-research.html', '기업 리서치', 'research'), ('/past-analysis/', '과거 정밀분석', 'past'),
       ('/study.html', '종목 공부', 'study'), ('/learn.html', '투자 공부', 'learn'), ('/calculators.html', '계산기', 'calc')]
FOOTER = ('<footer id="site-foot" class="site-foot"><div class="wrap">'
          '<p>GAEO는 공시·기업 공부를 돕는 개인 리서치 노트입니다. 투자 권유가 아니며, 판단과 책임은 읽는 분에게 있습니다. '
          '매수·매도 추천, 1:1 종목 상담, 유료 리딩을 하지 않습니다.</p>'
          '<p>공시 자료 출처: 금융감독원 전자공시시스템(DART) · OpenDART</p>'
          '<p class="foot-links"><a href="/about.html">사이트 소개</a><a href="/disclaimer.html">자료 출처·면책</a>'
          '<a href="/privacy.html">개인정보처리방침</a><a href="/contact.html">문의</a></p></div></footer>')

# 공시 종류 → 관련 공부 글(투자 공부 · 주식 · id). 사람이 고른 작은 표다 — 자동 추측으로 글을 잇지 않는다.
# 표에 없는 종류는 BASIC_LESSONS(DART 공시 보는 법)만 잇는다.
LESSONS_BY_CATEGORY = {
    'share_cancel': [77],          # 자사주 매입과 소각
    'buyback': [77],               # 자사주 매입과 소각
    'dividend': [18, 69],          # 배당락일 · 국내주식 세금(배당 과세)
    'capital_increase': [33],      # 유상증자·무상증자
    'capital_reduction': [74],     # 액면분할과 액면병합(감자·액면 분류의 '액면' 공시)
    'equity_linked_bond': [34],    # 전환사채(CB)·신주인수권부사채(BW)
    'merger_split': [80],          # 인적분할과 물적분할
    'trading_status': [70],        # 상장폐지 완전정복(거래정지~정리매매)
    'earnings': [67],              # 재무제표 보는 법
    'periodic_report': [67],       # 재무제표 보는 법
}
BASIC_LESSONS = [68]               # DART 공시 보는 법
# 사건 흐름(chain) → 공시 종류. 흐름만 있는 회사도 같은 표로 공부 글을 잇는다.
CHAIN_CATEGORY = {'buyback': 'buyback', 'buyback_disposal': 'buyback', 'dividend': 'dividend',
                  'capital_increase': 'capital_increase', 'bonus_issue': 'capital_increase',
                  'capital_reduction': 'capital_reduction', 'merger': 'merger_split', 'split': 'merger_split',
                  'equity_linked_bond': 'equity_linked_bond'}
KEY_ACCOUNTS = ('revenue', 'operatingIncome', 'netIncome')
HOME_EXAMPLES = ('삼성전자', '대한항공')


def head(title, desc, path, extra=''):
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · GAEO</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{BASE}{path}">
<meta name="theme-color" content="#FFFFFF">
<link rel="icon" href="/img/favicon.ico" sizes="any">
<meta property="og:type" content="article">
<meta property="og:title" content="{e(title)} · GAEO">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{BASE}{path}">
{extra}<link rel="stylesheet" href="/assets/fonts/wanted-sans/WantedSansVariable.css">
<link rel="stylesheet" href="/assets/site.css">
</head>
<body data-page="past">
<header id="site-head"></header>
<main id="main" class="wrap read">
'''


TAIL = '''</main>
<footer id="site-foot"></footer>
<script src="/assets/site.js"></script>
</body>
</html>
'''


def stamp(snapshot_id):
    """'005930-202608121215' → '2026-08-12-1215' (옛 주소 모양)."""
    s = snapshot_id.split('-', 1)[1]
    return f'{s[0:4]}-{s[4:6]}-{s[6:8]}-{s[8:12]}'


def when(analyzed_at):
    d, t = analyzed_at.split(' ')
    y, m, dd = d.split('-')
    return f'{int(y)}년 {int(m)}월 {int(dd)}일 {t}'


def ul(items):
    return '<ul>' + ''.join(f'<li>{e(x)}</li>' for x in items) + '</ul>'


def facts_block(r):
    facts = r.get('dartFacts') or []
    if not facts:
        return ('<h3>공시 재무 사실</h3><p class="small">이 회사의 사업보고서 재무 자료가 아직 수집되지 않았습니다 — '
                '재무가 없다는 뜻이 아닙니다. <a href="/disclosure-research.html?code=' + e(r["ticker"]) + '">재무 변화표에서 확인 →</a></p>')
    return (f'<h3>공시 재무 사실 <span class="meta">{e(r.get("editedAt", ""))} 편집에서 덧붙임 · 당시 분석의 근거가 아님</span></h3>'
            + ul([f['text'] for f in facts])
            + f'<p class="small">출처: {e(facts[0]["source"])} · 영업이익률·ROE 는 공시 값으로 직접 계산했습니다. '
            + f'<a href="/disclosure-research.html?code={e(r["ticker"])}">재무 변화표 →</a></p>')


def record_page(r):
    path = f'/research/deep-analysis/{r["ticker"]}/{stamp(r["snapshotId"])}/'
    title = f'{r["stockName"]} 과거 분석 기록 ({r["analyzedAt"][:10]})'
    body = head(title, f'{r["stockName"]} — {r["title"]}. 작성 당시 기준의 과거 분석 기록이며 현재의 매수·매도 추천이 아닙니다.', path)
    edited = f' · 이번 편집일 {e(r["editedAt"])}' if r.get('editedAt') else ''
    facts = facts_block(r)
    body += f'''<p class="small"><a href="/past-analysis/">← 과거 정밀분석 목록</a></p>
<article>
<h1>{e(r["stockName"])} <span class="meta">{e(r["ticker"])}</span></h1>
<p class="note past"><b>과거 분석 기록</b> · 원래 분석일 {e(when(r["analyzedAt"]))}{edited} · <b>현재의 매수·매도 추천이 아님</b></p>
<h2>{e(r["title"])}</h2>
<h3>당시 기록 <span class="meta">원래 분석일 {e(r["analyzedAt"][:10])} · 수치 없이 다시 정리</span></h3>
<dl class="qa">
<dt>당시 무엇을 봤나</dt><dd>{ul(r["whatWeSaw"])}</dd>
<dt>왜 그렇게 봤나</dt><dd>{ul(r["whyViewed"])}</dd>
</dl>
<h3>이번 편집에서 정리·보충한 생각 <span class="meta">{e(r.get("editedAt") or "편집일 미기록")} · 당시의 판단이 아님</span></h3>
<dl class="qa">
<dt>무엇이면 틀릴 수 있었나</dt><dd>{ul(r["wrongIf"])}</dd>
<dt>이후 공부할 점</dt><dd>{ul(r["studyNext"])}</dd>
<dt>지금 DART에서 확인할 것</dt><dd>{ul(r["dartCheck"])}<p><a href="/disclosure-research.html?code={e(r["ticker"])}">{e(r["stockName"])}의 최근 공시·재무 변화 보기 →</a></p></dd>
</dl>
{facts}
<p class="small">옮기면서 뺀 것: 당시 시세와 주가배수, 컨센서스·목표주가, 투자자별 매매 수치, 증권사·기사 인용, 점수와 매수·매도 판단. 출처가 확인되는 공시 재무 사실은 위 「공시 재무 사실」에 편집일 기준으로 따로 붙였습니다.</p>
</article>
'''
    return path, body + TAIL


def index_page(records, path):
    by = {}
    for r in records:
        by.setdefault(r['ticker'], []).append(r)
    rows = []
    for r in sorted(records, key=lambda x: x['analyzedAt'], reverse=True):
        rows.append(f'<li><a href="/research/deep-analysis/{e(r["ticker"])}/{stamp(r["snapshotId"])}/"><b>{e(r["stockName"])}</b></a> '
                    f'<span class="meta">{e(r["analyzedAt"])}</span><br><span class="small">{e(r["title"])}</span></li>')
    body = head('과거 정밀분석', '예전에 남긴 종목 분석 기록을 「당시 무엇을 봤고, 무엇이면 틀릴 수 있었는지」 중심으로 다시 정리했습니다. 작성 당시 기준이며 매수·매도 추천이 아닙니다.', path)
    body += f'''<h1>과거 정밀분석</h1>
<p class="note past"><b>과거 분석 기록</b>입니다. 모두 작성 당시 기준이며 <b>현재의 매수·매도 추천이 아닙니다.</b></p>
<p class="lede">2026년 7~8월에 남긴 분석 {len(records)}건({len(by)}개 회사)입니다. 당시 시세·주가배수·컨센서스·수급 수치와 매매 판단은 빼고 생각의 흐름을 남겼습니다. 2026-09-24 편집에서 보충한 내용과 공시 재무 사실은 쪽마다 따로 표시했습니다.</p>
<ul class="list">{''.join(rows)}</ul>
'''
    return body + TAIL


def write(out, rel, text):
    path = os.path.join(out, rel.lstrip('/'))
    if rel.endswith('/'):
        path = os.path.join(path, 'index.html')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


LOCAL = ('assets/', 'img/', 'content/', 'disclosure_research/', 'dart_today.js', 'disclosure-research.html', 'past-analysis/',
         'research/', 'study.html', 'learn.html', 'calculators.html', 'about.html', 'disclaimer.html', 'privacy.html', 'contact.html')


def rebase(out, base):
    """사이트 절대경로('/…')에 BASE_PATH 를 붙인다. 외부 주소(https://)와 canonical 은 건드리지 않는다."""
    if not base:
        return 0
    rx = re.compile(r'(["\'])/(?=(' + '|'.join(re.escape(x) for x in LOCAL) + r')|\1)')
    changed = 0
    for d, _, files in os.walk(out):
        for f in files:
            if f.endswith(('.html', '.js')) and 'fonts' not in d and 'content' not in d and not f.startswith('dart_today'):
                path = os.path.join(d, f)
                text = open(path, encoding='utf-8').read()
                new = rx.sub(lambda m: m.group(1) + base + '/', text)
                if new != text:
                    changed += 1
                    open(path, 'w', encoding='utf-8').write(new)
    return changed


def header_html(active):
    links = ''.join('<a href="%s"%s>%s</a>' % (href, ' aria-current="page"' if key == active else '', label)
                    for href, label, key in NAV)
    return ('<header id="site-head" class="site-head"><a class="skip" href="#main">본문 바로가기</a>'
            '<div class="wrap head-row"><a class="brand" href="/">GAEO<small>기업 리서치</small></a>'
            f'<nav class="nav" aria-label="주 메뉴">{links}</nav></div></header>')


def inject_chrome(out):
    """모든 쪽의 머리말·꼬리말을 빌드 때 그린다 — 자바스크립트가 실패해도 메뉴와 출처 안내가 보인다."""
    count = 0
    for d, _, files in os.walk(out):
        for f in files:
            if not f.endswith('.html'):
                continue
            path = os.path.join(d, f)
            text = open(path, encoding='utf-8').read()
            page = re.search(r'<body data-page="([a-z]*)"', text)
            new = text.replace('<header id="site-head"></header>', header_html(page.group(1) if page else ''))
            new = new.replace('<footer id="site-foot"></footer>', FOOTER)
            if new != text:
                open(path, 'w', encoding='utf-8').write(new)
                count += 1
    return count


def content_meta(rel):
    """content/*.js 글 목록에서 id·날짜·제목·요약·분류·종목코드만 읽는다(본문은 읽지 않는다)."""
    text = open(os.path.join(ROOT, rel), encoding='utf-8').read()
    starts = list(re.finditer(r'"id"\s*:\s*(\d+)', text))
    items = []
    for i, m in enumerate(starts):
        chunk = text[m.start():starts[i + 1].start() if i + 1 < len(starts) else len(text)]
        item = {'id': int(m.group(1))}
        for key in ('date', 'name', 'summary', 'cat', 'code'):
            found = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % key, chunk)
            if found:
                item[key] = json.loads('"' + found.group(1) + '"')
        items.append(item)
    return items


def categories_of(title, categories):
    """정정 표식·공백을 뺀 제목에 분류 단어가 든 분류들(설정 순서). 첫 것이 build_disclosure_research.category_of 와 같다."""
    bare = re.sub(r'\s+', '', re.sub(r'\[[^\]]*\]', '', str(title or '')))
    return [key for key, spec in categories.items()
            if any(term.replace(' ', '') in bare for term in spec.get('terms') or [])]


def category_of(title, categories):
    """build_disclosure_research.category_of 와 같은 규칙: 분류 단어가 든 첫 분류, 없으면 other."""
    found = categories_of(title, categories)
    return found[0] if found else 'other'


def first_sentence(text):
    """첫 문장과 나머지. 긴 설명은 첫 문장만 먼저 보이고 나머지는 「자세히 보기」로 접는다."""
    text = str(text or '').strip()
    m = re.match(r'^(.+?[.!?])\s+(.+)$', text, re.S)
    return (m.group(1), m.group(2)) if m else (text, '')


def ymd(s):
    s = str(s or '')
    return f'{s[:4]}-{s[4:6]}-{s[6:]}' if re.fullmatch(r'\d{8}', s) else s


def kst(iso):
    from datetime import datetime, timedelta
    try:
        t = datetime.fromisoformat(str(iso).replace('Z', '+00:00')) + timedelta(hours=9)
        return t.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return str(iso or '')


def dart_url(rcept_no):
    return f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}' if re.fullmatch(r'\d{14}', str(rcept_no or '')) else ''


def read_js_object(rel, name):
    text = open(os.path.join(ROOT, rel), encoding='utf-8').read()
    return json.loads(text[text.index('{', text.index(name)):text.rindex('}') + 1])


def home_sections(contract, dart, vocab, study, lessons):
    """홈 화면 조각. 숫자는 contract.json 의 실제 값만, 설명은 공시 분류표(howToRead)의 일반적인 읽는 법만 쓴다."""
    files = {f['kind']: f for f in contract.get('files', [])}
    names = contract.get('companyNames') or {}
    status = (
        '<dl class="facts-strip" aria-label="자료 현황">'
        f'<div><dt>자료 기준일</dt><dd>{e(contract["asOf"])}</dd></div>'
        f'<div><dt>추적 회사</dt><dd>{len(names):,}곳</dd></div>'
        f'<div><dt>재무 자료가 있는 회사</dt><dd>{files["financial_changes"]["companies"]:,}곳</dd></div>'
        f'<div><dt>사건 흐름이 있는 회사</dt><dd>{files["event_timelines"]["companies"]:,}곳</dd></div>'
        '<div><dt>갱신</dt><dd>하루 2회 · OpenDART</dd></div></dl>'
        f'<p class="meta strip-note">자료 생성 {e(kst(contract["generatedAt"]))} (한국시간) · 출처 금융감독원 OpenDART</p>')

    cats = vocab['categories']
    cards, seen = [], set()
    for it in dart.get('items') or []:
        if it.get('code') in seen or not re.fullmatch(r'\d{6}', str(it.get('code') or '')):
            continue
        seen.add(it['code'])
        found = categories_of(it.get('title'), cats)
        spec = cats.get(found[0]) if len(found) == 1 else {}
        # 제목이 두 분류 이상에 걸리면(예: 증권발행'실적'보고서) 한 가지 읽는 법을 골라 붙이지 않는다 — 틀린 설명보다 원문 안내가 낫다.
        why = ((spec or {}).get('howToRead') or {}).get('why') or (
            '제목에 여러 종류의 낱말이 섞여 있어 한 가지 읽는 법을 고르지 않았어요. 원문에서 무엇을 결정·보고한 공시인지 먼저 확인해 보세요.'
            if len(found) > 1 else '공시 제목만으로는 내용을 다 알 수 없어요. 원문에서 결정 내용과 일정을 확인해 보세요.')
        lead, rest = first_sentence(why)
        more = f'<details class="more"><summary>자세히 보기</summary><p>{e(rest)}</p></details>' if rest else ''
        code, name, date = e(it['code']), e(it.get('name') or it['code']), e(ymd(it.get('receiptDate')))
        kind = '<span class="chip neutral">정정 공시</span>' if it.get('isCorrection') else '<span class="chip info">새 공시</span>'
        label = e(' · '.join(cats[k]['label'] for k in found) if len(found) > 1 else ((spec or {}).get('label') or '기타'))
        url = dart_url(it.get('rceptNo'))
        cards.append(
            '<article class="card change-card">'
            f'<p class="cc-top"><a class="cc-company" href="/disclosure-research.html?code={code}">{name}</a><span class="meta">{code}</span></p>'
            f'<p class="cc-meta">{kind}<time datetime="{date}">{date}</time><span class="cc-cat">{label}</span></p>'
            f'<h3 class="cc-title">{e(it.get("title") or "")}</h3>'
            '<dl class="cc-qa">'
            f'<dt>무슨 내용인가요?</dt><dd>{name}이(가) {date}에 이 공시를 냈어요. 금액·일정 같은 자세한 내용은 원문에 있어요.</dd>'
            f'<dt>왜 확인할까요?</dt><dd>{e(lead)}{more}</dd></dl>'
            '<p class="cc-actions">'
            f'<a class="btn btn-outline" href="/disclosure-research.html?code={code}">회사 변화 보기</a>'
            + (f'<a class="btn btn-quiet" href="{e(url)}" target="_blank" rel="noopener">DART 원문<span aria-hidden="true"> ↗</span></a>' if url else '')
            + '</p></article>')
        if len(cards) == 6:
            break
    today = ('<div class="grid three">' + ''.join(cards) + '</div>') if cards else (
        '<div class="state state-unknown"><p class="state-title">최근 공시 목록을 아직 받지 못했어요</p>'
        '<p>없는 자료를 빈 목록으로 채우지 않습니다. 기업 리서치에서 회사별 자료를 확인해 보세요.</p></div>')
    period = [ymd(x.get('receiptDate')) for x in (dart.get('items') or [])]
    today_note = (f'<p class="section-sub">공시 접수 {e(min(period))} ~ {e(max(period))} 가운데 회사별로 가장 새 공시를 골랐어요. '
                  f'공시 사실과 일반적인 읽는 법만 적습니다 · 모은 시각 {e(dart.get("generatedAt") or "")}</p>') if period else ''

    def recent(items, href, label):
        items = sorted(items, key=lambda x: (x.get('date') or '', x['id']), reverse=True)[:3]
        return ''.join(
            f'<a class="card link-card" href="{href}{x["id"]}"><span class="chip neutral">{label}</span>'
            f'<span class="lc-title">{e(x.get("name") or "")}</span>'
            f'<span class="lc-sub">{e(first_sentence(x.get("summary"))[0])}</span><span class="meta">{e(x.get("date") or "")}</span></a>'
            for x in items)
    studies = ('<div class="grid three">' + recent(study, '/study.html?id=', '종목 공부')
               + recent(lessons, '/learn.html?t=stock&id=', '투자 공부') + '</div>')

    by_name = {v: k for k, v in names.items()}
    examples = ' · '.join(f'<a class="chip-link" href="/disclosure-research.html?code={e(by_name[n])}">{e(n)}</a>'
                          for n in HOME_EXAMPLES if n in by_name)
    options = ''.join(f'<option value="{e(v)}" label="{e(k)}"></option>' for k, v in sorted(names.items()))
    return {'STATUS': status, 'TODAY': today_note + today, 'STUDY': studies,
            'EXAMPLES': (examples + ' · 종목코드 6자리') if examples else '종목코드 6자리', 'COMPANIES': options}


def research_summary(contract, changes, financial, timelines, lessons):
    """기업 한눈에 보기용 작은 요약(회사당 수백 바이트). 큰 자료 세 개를 한꺼번에 받지 않게 한다.

    공시 사실만 옮긴다. 결측은 0 으로 만들지 않는다: 재무를 아직 못 받은 회사는 state=NOT_COLLECTED,
    기록이 없는 회사는 키 자체가 없다(화면이 두 경우를 다른 말로 보여 준다)."""
    lesson_name = {x['id']: x.get('name') for x in lessons}
    not_collected = set(financial.get('notCollectedTickers') or [])
    stage_vocab = timelines.get('stageVocabulary') or {}
    companies = {}
    for code, name in sorted((contract.get('companyNames') or {}).items()):
        entry, cats = {'name': name}, []
        c = (changes.get('companies') or {}).get(code)
        if c:
            count = {}
            for f in c.get('filings') or []:
                if f.get('category'):
                    count[f['category']] = count.get(f['category'], 0) + 1
            cats += [k for k, _ in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))]
            entry['changes'] = {'filingCount': c.get('filingCount'), 'latestReceivedOn': c.get('latestReceivedOn'),
                                'recentCount': c.get('recentCount'), 'priorCount': c.get('priorCount'),
                                'lines': [x.get('text') for x in (c.get('changes') or [])[:2] if x.get('text')]}
        fc = (financial.get('companies') or {}).get(code)
        if fc:
            pairs = fc.get('comparablePairs') or []
            last = pairs[-1] if pairs else None
            rows = []
            for r in fc.get('rows') or []:
                if r.get('account') in KEY_ACCOUNTS:
                    ch = (r.get('changes') or {}).get(last['to']) if last else None
                    rows.append({'label': r.get('label'),
                                 'change': {k: ch.get(k) for k in ('abs', 'pct', 'pctReason')} if ch else None})
            entry['financial'] = {'state': 'OK', 'basis': fc.get('fsDivLabel'),
                                  'from': last['from'] if last else None, 'to': last['to'] if last else None, 'rows': rows}
        elif code in not_collected:
            entry['financial'] = {'state': 'NOT_COLLECTED'}
        tc = (timelines.get('companies') or {}).get(code)
        if tc and tc.get('timelines'):
            tls = sorted(tc['timelines'], key=lambda t: str(t.get('latestReceivedOn') or ''), reverse=True)
            items = []
            for t in tls[:2]:
                stage_items = [i for i in t.get('items') or [] if i.get('stage') == t.get('latestStage')]
                items.append({'label': t.get('label'), 'latestReceivedOn': t.get('latestReceivedOn'),
                              'stageLabel': (stage_items[-1].get('stageLabel') if stage_items
                                             else stage_vocab.get(t.get('latestStage'), t.get('latestStage')))})
            entry['timelines'] = {'count': len(tls), 'items': items}
            cats += [CHAIN_CATEGORY[t['chain']] for t in tls if t.get('chain') in CHAIN_CATEGORY]
        seen = []
        for k in cats:
            if k not in seen:
                seen.append(k)
        entry['categories'] = seen[:6]
        companies[code] = entry
    return {'schema': 'gaeo-research-summary-v1', 'generatedAt': contract.get('generatedAt'), 'asOf': contract.get('asOf'),
            'source': '금융감독원 OpenDART (disclosure_research/*.json 에서 줄임)',
            'companies': companies,
            'categoryLabels': {k: v.get('label') for k, v in (changes.get('categories') or {}).items()},
            'lessons': {cat: [[i, lesson_name[i]] for i in ids if i in lesson_name] for cat, ids in LESSONS_BY_CATEGORY.items()},
            'basicLessons': [[i, lesson_name[i]] for i in BASIC_LESSONS if i in lesson_name]}


def render_generated(out):
    """홈 화면과 기업 한눈에 보기 요약을 만든다(네트워크 0 · 저장소 안 자료만)."""
    def load(rel):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            return json.load(f)
    contract = load('disclosure_research/contract.json')
    with open(os.path.join(ROOT, 'config', 'disclosure_research_vocab.json'), encoding='utf-8') as f:
        vocab = json.load(f)
    dart = read_js_object('dart_today.js', 'DART_TODAY')
    study, lessons = content_meta('content/stock_study.js'), content_meta('content/stock_lessons.js')
    parts = home_sections(contract, dart, vocab, study, lessons)
    index = os.path.join(out, 'index.html')
    text = open(index, encoding='utf-8').read()
    for key, value in parts.items():
        marker = f'<!--HOME:{key}-->'
        if marker not in text:
            raise SystemExit(f'홈 화면 자리표시 없음: {marker}')
        text = text.replace(marker, value)
    open(index, 'w', encoding='utf-8').write(text)
    summary = research_summary(contract, load('disclosure_research/disclosure_changes.json'),
                               load('disclosure_research/financial_changes.json'),
                               load('disclosure_research/event_timelines.json'), lessons)
    with open(os.path.join(out, 'assets', 'research-summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, separators=(',', ':'))
    return len(summary['companies'])


def build(out):
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(ROOT, 'site'), out)
    for rel in DATA_FILES + CONTENT_FILES:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            raise SystemExit(f'필수 파일 없음: {rel} — 없는 자료로 사이트를 만들지 않는다')
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    with open(os.path.join(ROOT, 'content', 'past_analysis.json'), encoding='utf-8') as f:
        records = json.load(f)['records']
    urls = list(STATIC_PAGES)
    for r in records:
        path, text = record_page(r)
        write(out, path, text)
        urls.append(path.lstrip('/'))
    write(out, '/past-analysis/', index_page(records, '/past-analysis/'))
    write(out, '/research/deep-analysis/', index_page(records, '/past-analysis/'))
    with open(os.path.join(out, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in urls:
            f.write(f'  <url><loc>{BASE}/{u}</loc></url>\n')
        f.write('</urlset>\n')
    with open(os.path.join(out, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write(f'User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n')
    open(os.path.join(out, '.nojekyll'), 'w').close()
    summarized = render_generated(out)
    inject_chrome(out)
    base = os.environ.get('BASE_PATH', '').rstrip('/')
    rebased = rebase(out, base)
    files = sum(len(fs) for _, _, fs in os.walk(out))
    print(f'_site 조립 완료 · 파일 {files}개 · 과거 분석 {len(records)}쪽 · 회사 요약 {summarized}곳' + (f' · BASE_PATH {base} ({rebased}파일)' if base else ''))


if __name__ == '__main__':
    build(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '_site')))
