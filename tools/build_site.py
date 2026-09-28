#!/usr/bin/env python3
"""공개 사이트 조립기 (네트워크 0 · LLM 0).

GitHub Pages 에 올라가는 것은 이 스크립트가 만든 _site/ **뿐**이다. 저장소의 나머지(수집기 코드·원장·
원문 아카이브·재무 원자료·문서)는 사이트 주소로 나가지 않는다. 무엇을 싣는지는 아래 허용목록이 정한다.

  site/                     손으로 쓴 화면(html·css·js·이미지·서체)
  content/*.js · *.json     공부 글·계산기·과거 분석 세척본·공시 사전
  dart_today.js             최근 접수 공시 목록(수집기 산출물)
  disclosure_research/*.json 공시 연구 산출물(수집기 산출물)

빌드가 그리는 정적 쪽(검색엔진이 자바스크립트 없이 읽는 쪽 · 2026-09-28)
  /snap/{study,lesson,estate,calc}/<id>.html  공부 글 한 편씩 — 옛 사이트가 색인시킨 주소를 그대로 되살린다
  /guide/ · /guide/<key>/                     공시 사전(content/disclosure_guide.json)
  /company/<종목코드>/                         회사별 공시·재무 요약(OpenDART 산출물만)
  /research/deep-analysis/…  · /past-analysis/ 과거 정밀분석(옛 주소 유지)
  sitemap.xml · rss.xml · robots.txt · llms.txt

글 본문은 문단을 1~2문장씩 끊어 그린다(md_html · 2026-09-28 소유자 지시 「문단마다 나눠 쉽게 끊어 읽게」).
공부 글 자료(content/*.js)는 브라우저와 똑같이 node 로 실행해 읽는다(tools/content_dump.js).
사용: python3 tools/build_site.py [출력 폴더(기본 _site)]
환경변수 BASE_PATH(예: /gaeo-research): 커스텀 도메인 연결 전 임시 주소(https://<계정>.github.io/<저장소>/)에서도
링크가 맞도록 html·js 의 사이트 절대경로 앞에 붙인다. 커스텀 도메인이면 빈 값.
"""
import re
import html
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import disclosure_classify  # noqa: E402  공시 제목 분류 — 공시 연구 생산자와 같은 모듈
BASE = 'https://gaeoteam.com'
OG_IMAGE = BASE + '/img/og-image.png'
SITE_NAME = 'GAEO 기업 리서치'
DATA_FILES = ['dart_today.js', 'disclosure_research/contract.json', 'disclosure_research/disclosure_changes.json',
              'disclosure_research/financial_changes.json', 'disclosure_research/event_timelines.json']
CONTENT_FILES = ['content/stock_study.js', 'content/stock_lessons.js', 'content/estate_lessons.js',
                 'content/calculators.js', 'content/past_analysis.json']
STATIC_PAGES = ['', 'disclosure-research.html', 'guide/', 'past-analysis/', 'study.html', 'learn.html', 'calculators.html',
                'snap/index.html', 'about.html', 'disclaimer.html', 'privacy.html', 'contact.html']
INDEXNOW_KEY = 'd96e570cc9c1cbbad053bee2b14a7e5d'   # 공개 키(검색엔진이 site/<키>.txt 로 소유를 확인한다) · 비밀값 아님
DAUM_VERIFY = '#DaumWebMasterTool:02d4f3c60a9d0eb9a109fda50288d278a24980e353d00231ab51251e64b1a8b3:VIegKZyO3wCgIgV8lIIfGA=='
e = html.escape

# 머리말 메뉴 — site/assets/site.js 의 NAV 와 같은 순서(자바스크립트가 꺼져도 보이게 빌드 때 미리 그린다).
NAV = [('/', '홈', 'home'), ('/disclosure-research.html', '기업 리서치', 'research'), ('/guide/', '공시 사전', 'guide'),
       ('/past-analysis/', '과거 정밀분석', 'past'), ('/study.html', '종목 공부', 'study'), ('/learn.html', '투자 공부', 'learn'),
       ('/calculators.html', '계산기', 'calc')]
FOOTER = ('<footer id="site-foot" class="site-foot"><div class="wrap">'
          '<p>GAEO는 공시·기업 공부를 돕는 개인 리서치 노트입니다. 투자 권유가 아니며, 판단과 책임은 읽는 분에게 있습니다. '
          '매수·매도 추천, 1:1 종목 상담, 유료 리딩을 하지 않습니다.</p>'
          '<p>공시 자료 출처: 금융감독원 전자공시시스템(DART) · OpenDART</p>'
          '<p class="foot-links"><a href="/about.html">사이트 소개</a><a href="/disclaimer.html">자료 출처·면책</a>'
          '<a href="/privacy.html">개인정보처리방침</a><a href="/contact.html">문의</a>'
          '<a href="/snap/index.html">글 전체 목록</a><a href="/rss.xml">RSS</a></p></div></footer>')

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
COMPANY_ACCOUNTS = ('revenue', 'operatingIncome', 'netIncome', 'operatingCashFlow', 'totalLiabilities', 'totalEquity')
HOME_EXAMPLES = ('삼성전자', '대한항공')

# 공부 글 묶음 — (주소 폴더, 자료 이름, 목록 이름, 목록 주소, 메뉴 키, 분류 이름). 분류 이름은 study/learn/calculators.html 과 같다.
SECTIONS = {
    'study': ('STOCK_STUDY', '종목 공부', '/study.html', 'study', {'kr': '국내 기업', 'global': '해외 기업'}),
    'lesson': ('STOCK_LESSONS', '투자 공부', '/learn.html', 'learn',
               {'beginner': '주식 첫걸음', 'chart': '차트 기초', 'crisis': '경제위기의 역사', 'tax': '세금·절세', 'isa': 'ISA',
                'product': '투자상품', 'macro': '시장을 움직이는 손', 'industry': '산업 공부', 'etf': 'ETF·연금', 'youth': '청년 돈생활'}),
    'estate': ('ESTATE_LESSONS', '부동산 공부', '/learn.html?t=estate', 'learn',
               {'buy': '내 집 마련', 'rent': '전월세', 'loan': '대출', 'auction': '경매·공매', 'strategy': '투자 접근법', 'tax': '부동산 세금'}),
    'calc': ('CALCULATORS', '계산기', '/calculators.html', 'calc',
             {'stock': '주식', 'tax': '세금', 'finance': '재테크', 'etf': 'ETF·연금', 'youth': '청년'}),
}


# ── 글 자료 읽기 ───────────────────────────────────────────────────────────────
_CONTENT = None


def load_content():
    """content/*.js 를 node 로 실행해 최종 글 목록을 받는다(본문 보강까지 적용된 모습 = 브라우저와 같음)."""
    global _CONTENT
    if _CONTENT is None:
        node = shutil.which('node')
        if not node:
            raise SystemExit('node 가 없다 — 공부 글(content/*.js)을 읽으려면 Node.js 가 필요하다')
        out = subprocess.run([node, os.path.join(ROOT, 'tools', 'content_dump.js')], capture_output=True, check=True)
        _CONTENT = json.loads(out.stdout.decode('utf-8'))
    return _CONTENT


def content_meta(rel):
    """content/*.js 글 목록(id·날짜·제목·요약·분류·종목코드 등). 예전 함수 이름과 뜻을 유지한다."""
    var = {'content/stock_study.js': 'STOCK_STUDY', 'content/stock_lessons.js': 'STOCK_LESSONS',
           'content/estate_lessons.js': 'ESTATE_LESSONS', 'content/calculators.js': 'CALCULATORS'}[rel]
    return load_content()[var]


def load_guides():
    with open(os.path.join(ROOT, 'content', 'disclosure_guide.json'), encoding='utf-8') as f:
        return json.load(f)


# ── 쉬운 읽기용 마크다운(## 소제목 · - 목록 · 1. 번호 · 문단 · **굵게** · [링크](https://)) ──────────────
HANGUL = re.compile(r'[가-힣]')
OPENERS, CLOSERS, TRAIL = '([{「『“‘', ')]}」』”’', '"\'”’」』)]'
BEFORE_END = set(')%」』”’"\'*')
# 문장 끝처럼 보여도 인용 뒤에 말이 이어지는 경우(… "좋아요." 라고 했다) — 끊지 않는다
CONTINUES = re.compile(r'(라고|이라고|라며|이라며|라는|이라는|하고|하며|란\s|고\s|며\s|처럼|같은|등\s)')
LINK = re.compile(r'\[([^\]]+)\]\((https://[^)\s]+)\)')
HEAD_RX = re.compile(r'^(#{2,4})\s+(.*)$')
BULLET = re.compile(r'^[-·*•]\s+')
OLNUM = re.compile(r'^(\d+)[.)]\s+')
IMG_MARK = re.compile(r'^\[\[img:[^\]]*\]\]$')


def plain(s):
    return str(s or '').replace('**', '')


def split_sentences(text):
    """문장 경계에서 나눈다. **굵게** 안·괄호/따옴표 안·숫자(1.5조)·영문 약어(Inc.)에서는 나누지 않는다."""
    text = str(text or '')
    n = len(text)
    balanced = text.count('"') % 2 == 0
    state, depth, bold, dq, i = [None] * n, 0, False, False, 0
    while i < n:
        if text.startswith('**', i):
            bold = not bold
            state[i] = state[i + 1] = (depth, bold, dq)
            i += 2
            continue
        ch = text[i]
        if ch in OPENERS:
            depth += 1
        elif ch in CLOSERS:
            depth = max(0, depth - 1)
        elif ch == '"' and balanced:
            dq = not dq
        state[i] = (depth, bold, dq)
        i += 1
    out, start, i = [], 0, 0
    while i < n:
        ch = text[i]
        if ch in '.!?' and i > 0 and (HANGUL.match(text[i - 1]) or text[i - 1] in BEFORE_END):
            j = i + 1
            while j < n and (text[j] in TRAIL or text.startswith('**', j)):
                j += 2 if text.startswith('**', j) else 1
            if j < n and text[j] in ' \t' and state[j - 1] == (0, False, False):
                rest = text[j:].lstrip()
                if rest and not CONTINUES.match(rest) and not re.match(r'[a-z]', rest):
                    out.append(text[start:j].strip())
                    start = i = j
                    continue
        i += 1
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def chunks(text, max_sent=2, max_len=90):
    """문단을 1~2문장 덩어리로 끊는다. 통째로 굵은 문장(핵심 한 줄)은 따로 한 줄로 세운다."""
    out, cur = [], []
    for s in split_sentences(text):
        if re.fullmatch(r'\*\*[^*]+\*\*[.!?]?', s.strip()):
            if cur:
                out.append(' '.join(cur))
                cur = []
            out.append(s)
            continue
        cur.append(s)
        if len(cur) >= max_sent or len(plain(' '.join(cur))) >= max_len:
            out.append(' '.join(cur))
            cur = []
    if cur:
        out.append(' '.join(cur))
    return out


def inline(s):
    s = e(str(s or ''))
    s = LINK.sub(r'<a href="\2" target="_blank" rel="noopener nofollow">\1</a>', s)
    return re.sub(r'\*\*([^*]+?)\*\*', r'<b>\1</b>', s)


def paras(text):
    """짧은 설명 글(공시 사전 등)을 1~2문장 문단으로."""
    return ''.join(f'<p>{inline(c)}</p>' for line in str(text or '').split('\n') if line.strip() for c in chunks(line.strip()))


def md_html(text):
    """공부 글 본문 → html. 긴 문단과 긴 목록 항목은 1~2문장씩 끊는다(내용은 바꾸지 않고 줄만 나눈다)."""
    out, items, kind, first = [], None, None, 1

    def flush():
        nonlocal items, kind
        if items:
            start = f' start="{first}"' if kind == 'ol' and first != 1 else ''
            out.append(f'<{kind}{start}>' + ''.join(items) + f'</{kind}>')
        items, kind = None, None

    for raw in str(text or '').split('\n'):
        t = raw.strip()
        if not t or IMG_MARK.match(t):
            flush()
            continue
        m = HEAD_RX.match(t)
        if m:
            flush()
            lv = 2 if len(m.group(1)) == 2 else 3
            out.append(f'<h{lv}>{inline(m.group(2))}</h{lv}>')
            continue
        mb, mo = BULLET.match(t), OLNUM.match(t)
        if mb or mo:
            k = 'ul' if mb else 'ol'
            if kind != k:
                flush()
                items, kind, first = [], k, int(mo.group(1)) if mo else 1
            body = t[(mb or mo).end():]
            todo = body[:4] in ('[ ] ', '[x] ', '[X] ')
            parts = chunks(body[4:] if todo else body) or ['']
            li = inline(parts[0]) + ''.join(f'<p>{inline(p)}</p>' for p in parts[1:])
            items.append(f'<li class="todo">{li}</li>' if todo else f'<li>{li}</li>')
            continue
        flush()
        out.extend(f'<p>{inline(c)}</p>' for c in chunks(t))
    flush()
    return '\n'.join(out)


def describe(text, limit=150):
    """검색 결과·공유 미리보기용 설명 한두 문장."""
    t = re.sub(r'\s+', ' ', plain(text)).strip()
    if len(t) <= limit:
        return t
    got = ''
    for s in split_sentences(t):
        if len(got) + len(s) + 1 > limit:
            break
        got = (got + ' ' + s).strip()
    return got or t[:limit - 1] + '…'


# ── 쪽 틀 ───────────────────────────────────────────────────────────────────────
def ld(obj):
    return ('<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
            + '</script>\n')


def crumbs_ld(items):
    return {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': BASE + p} for i, (n, p) in enumerate(items)]}


def article_ld(title, desc, path, date, section=None):
    obj = {'@context': 'https://schema.org', '@type': 'Article', 'headline': title[:110], 'description': desc,
           'inLanguage': 'ko-KR', 'image': OG_IMAGE, 'mainEntityOfPage': BASE + path,
           'author': {'@type': 'Organization', 'name': 'GAEO', 'url': BASE + '/about.html'},
           'publisher': {'@type': 'Organization', 'name': SITE_NAME, 'url': BASE + '/',
                         'logo': {'@type': 'ImageObject', 'url': BASE + '/img/app-icon-512.png'}}}
    if date:
        obj['datePublished'] = obj['dateModified'] = date
    if section:
        obj['articleSection'] = section
    return obj


def crumbs_html(items):
    return ('<nav class="crumbs" aria-label="현재 위치">'
            + '<span aria-hidden="true">›</span>'.join(f'<a href="{p}">{e(n)}</a>' for n, p in items) + '</nav>\n')


def head(title, desc, path, extra='', page='past', main='wrap read', og_type='article', jsonld=(), noindex=False):
    robots = '<meta name="robots" content="noindex,follow">\n' if noindex else ''
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · GAEO</title>
<meta name="description" content="{e(desc)}">
{robots}<link rel="canonical" href="{BASE}{path}">
<meta name="theme-color" content="#FFFFFF">
<link rel="icon" href="/img/favicon.ico" sizes="any">
<link rel="apple-touch-icon" sizes="180x180" href="/img/apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="GAEO 새 글·새 공시" href="/rss.xml">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{e(title)} · GAEO">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{BASE}{path}">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
{''.join(ld(x) for x in jsonld)}{extra}<link rel="stylesheet" href="/assets/fonts/wanted-sans/WantedSansVariable.css">
<link rel="stylesheet" href="/assets/site.css">
</head>
<body data-page="{page}">
<header id="site-head"></header>
<main id="main" class="{main}">
'''


def tail(scripts=''):
    return f'''</main>
<footer id="site-foot"></footer>
<script src="/assets/site.js"></script>
{scripts}</body>
</html>
'''


TAIL = tail()
SHARE = ('<div class="share"><button type="button" class="btn btn-outline" data-share>공유하기</button>'
         '<button type="button" class="btn btn-quiet" data-copy>링크 복사</button>'
         '<span class="meta" data-share-msg role="status" aria-live="polite"></span></div>\n')


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
                '재무가 없다는 뜻이 아닙니다. <a href="/company/' + e(r["ticker"]) + '/">회사 공시·재무 요약에서 확인 →</a></p>')
    return (f'<h3>공시 재무 사실 <span class="meta">{e(r.get("editedAt", ""))} 편집에서 덧붙임 · 당시 분석의 근거가 아님</span></h3>'
            + ul([f['text'] for f in facts])
            + f'<p class="small">출처: {e(facts[0]["source"])} · 영업이익률·ROE 는 공시 값으로 직접 계산했습니다. '
            + f'<a href="/company/{e(r["ticker"])}/">회사 공시·재무 요약 →</a></p>')


def record_page(r):
    path = f'/research/deep-analysis/{r["ticker"]}/{stamp(r["snapshotId"])}/'
    title = f'{r["stockName"]} 과거 분석 기록 ({r["analyzedAt"][:10]})'
    desc = f'{r["stockName"]} — {r["title"]}. 작성 당시 기준의 과거 분석 기록이며 현재의 매수·매도 추천이 아닙니다.'
    body = head(title, desc, path, jsonld=[crumbs_ld([('홈', '/'), ('과거 정밀분석', '/past-analysis/'), (title, path)])])
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
<dt>지금 DART에서 확인할 것</dt><dd>{ul(r["dartCheck"])}<p><a href="/company/{e(r["ticker"])}/">{e(r["stockName"])}의 최근 공시·재무 변화 보기 →</a></p></dd>
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
    body = head('과거 정밀분석', '예전에 남긴 종목 분석 기록을 「당시 무엇을 봤고, 무엇이면 틀릴 수 있었는지」 중심으로 다시 정리했습니다. 작성 당시 기준이며 매수·매도 추천이 아닙니다.', path, og_type='website')
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
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


LOCAL = ('assets/', 'img/', 'content/', 'disclosure_research/', 'dart_today.js', 'disclosure-research.html', 'past-analysis/',
         'research/', 'study.html', 'learn.html', 'calculators.html', 'about.html', 'disclaimer.html', 'privacy.html', 'contact.html',
         'snap/', 'guide/', 'company/', 'rss.xml')


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
                    open(path, 'w', encoding='utf-8', newline='\n').write(new)
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
                open(path, 'w', encoding='utf-8', newline='\n').write(new)
                count += 1
    return count


ENRICH = [
    ('og:image', f'<meta property="og:image" content="{OG_IMAGE}">'),
    ('og:site_name', f'<meta property="og:site_name" content="{SITE_NAME}">'),
    ('og:locale', '<meta property="og:locale" content="ko_KR">'),
    ('twitter:card', '<meta name="twitter:card" content="summary_large_image">'),
    ('application/rss+xml', '<link rel="alternate" type="application/rss+xml" title="GAEO 새 글·새 공시" href="/rss.xml">'),
    ('apple-touch-icon', '<link rel="apple-touch-icon" sizes="180x180" href="/img/apple-touch-icon.png">'),
]


def enrich_heads(out):
    """손으로 쓴 쪽(site/*.html)에도 공유 미리보기·RSS 안내 태그를 채운다(없는 것만)."""
    for f in os.listdir(out):
        if not f.endswith('.html'):
            continue
        path = os.path.join(out, f)
        text = open(path, encoding='utf-8').read()
        add = ''.join(tag + '\n' for key, tag in ENRICH if key not in text)
        if add and '<link rel="stylesheet"' in text:
            text = text.replace('<link rel="stylesheet"', add + '<link rel="stylesheet"', 1)
            open(path, 'w', encoding='utf-8', newline='\n').write(text)


def first_sentence(text):
    """첫 문장과 나머지."""
    text = str(text or '').strip()
    m = re.match(r'^(.+?[.!?])\s+(.+)$', text, re.S)
    return (m.group(1), m.group(2)) if m else (text, '')


def ymd(s):
    s = str(s or '')
    return f'{s[:4]}-{s[4:6]}-{s[6:]}' if re.fullmatch(r'\d{8}', s) else s


def kst(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace('Z', '+00:00')) + timedelta(hours=9)
        return t.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return str(iso or '')


def dart_url(rcept_no):
    return f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}' if re.fullmatch(r'\d{14}', str(rcept_no or '')) else ''


def dart_search(name):
    from urllib.parse import quote
    return 'https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm=' + quote(str(name or ''))


def read_js_object(rel, name):
    text = open(os.path.join(ROOT, rel), encoding='utf-8').read()
    return json.loads(text[text.index('{', text.index(name)):text.rindex('}') + 1])


def krw(v):
    """금액: 조·억·만 원. 음수는 빨강이 아니라 「−」."""
    if not isinstance(v, (int, float)):
        return '아직 못 받음' if v == 'NOT_COLLECTED' else '해당 없음' if v == 'NOT_APPLICABLE' else '—'
    a, s = abs(v), '−' if v < 0 else ''
    if a >= 1e12:
        return s + f'{a / 1e12:,.1f}'.rstrip('0').rstrip('.') + '조'
    if a >= 1e8:
        return s + f'{round(a / 1e8):,}억'
    if a >= 1e4:
        return s + f'{round(a / 1e4):,}만'
    return s + f'{a:,.0f}원'


def pct(c):
    if not c:
        return ''
    if isinstance(c.get('pct'), (int, float)):
        p = c['pct']
        return ('+' if p > 0 else '−' if p < 0 else '') + f'{abs(p):g}%'
    return '전년이 0 이하라 증감률 안 셈' if c.get('pctReason') == 'prior_zero_or_negative' else '—'


def study_url(kind, id_):
    return f'/snap/{kind}/{id_}.html'


# ── 공시 사전 ───────────────────────────────────────────────────────────────────
class Guide:
    """content/disclosure_guide.json — 공시 제목 → 초보자용 설명(가장 긴 낱말이 이긴다)."""

    def __init__(self, data, cats):
        self.data, self.cats = data, cats
        self.items = data['guides']
        self.by_key = {g['key']: g for g in self.items}
        self.patterns = sorted(((p.replace(' ', ''), g) for g in self.items for p in g['match'] if p.strip()),
                               key=lambda x: -len(x[0]))

    def find(self, title):
        text = disclosure_classify.bare(title)
        for p, g in self.patterns:
            if p in text:
                return g
        return None

    def notes(self, title, is_correction=False):
        text = disclosure_classify.bare(title)
        out = [n['text'] for n in self.data.get('suffixNotes', []) if n['match'] in text]
        if is_correction or re.search(r'\[(기재정정|정정|첨부정정|첨부추가)\]', str(title or '')):
            out.append(self.data['correctionNote'])
        return out

    def explain(self, title, is_correction=False):
        """카드·목록에 붙일 설명: 쉬운 이름 · 무슨 내용 · 왜 확인 · 원문에서 볼 것 · 사전 주소."""
        cls = disclosure_classify.classify(title, self.cats)
        g = self.find(title)
        if g is None and cls['category'] not in self.cats or g is None and cls['category'] == 'other':
            g = self.by_key.get('other-general')
        notes = self.notes(title, is_correction)
        if g:
            return {'cls': cls, 'guide': g, 'plain': g['plain'], 'what': g['what'], 'why': g['why'], 'check': g['check'],
                    'notes': notes, 'href': f'/guide/{g["key"]}/'}
        spec = self.cats[cls['category']]
        h = spec.get('howToRead') or {}
        why = ('제목만으로는 어느 종류인지 정할 수 없어 한 가지 읽는 법을 고르지 않았어요. 원문에서 무엇을 결정·보고한 공시인지 먼저 확인해 보세요.'
               if cls['tie'] else h.get('why', ''))
        return {'cls': cls, 'guide': None, 'plain': None,
                'what': f'이 공시는 「{spec["label"]}」 종류로 분류했어요. 제목에 회사가 무엇을 결정·보고했는지 적혀 있어요.',
                'why': why, 'check': [h['next']] if h.get('next') and not cls['tie'] else [], 'notes': notes, 'href': None}


def guide_index_json(guide):
    """기업 리서치 화면이 공시마다 「쉬운 이름」을 붙이는 데 쓰는 작은 표."""
    return {'schema': 'gaeo-disclosure-guide-v1',
            'patterns': [[p, g['key']] for p, g in guide.patterns],
            'guides': {g['key']: {'name': g['name'], 'plain': g['plain']} for g in guide.items}}


def collect_filings(changes, dart):
    """사전·회사 쪽이 함께 쓰는 공시 목록(접수번호로 중복 제거 · 최신순)."""
    seen, rows = set(), []
    for it in dart.get('items') or []:
        if re.fullmatch(r'\d{6}', str(it.get('code') or '')) and it.get('rceptNo') not in seen:
            seen.add(it.get('rceptNo'))
            rows.append({'code': it['code'], 'name': it.get('name'), 'title': it.get('title'), 'date': ymd(it.get('receiptDate')),
                         'url': dart_url(it.get('rceptNo')), 'isCorrection': bool(it.get('isCorrection')), 'rceptNo': it.get('rceptNo')})
    for code, c in (changes.get('companies') or {}).items():
        for f in c.get('filings') or []:
            if f.get('rceptNo') in seen:
                continue
            seen.add(f.get('rceptNo'))
            rows.append({'code': code, 'name': c.get('name'), 'title': f.get('title'), 'date': f.get('receivedOn'),
                         'url': f.get('url'), 'isCorrection': bool(f.get('isCorrection')), 'rceptNo': f.get('rceptNo')})
    rows.sort(key=lambda r: (str(r['date'] or ''), str(r['rceptNo'] or '')), reverse=True)
    return rows


def guide_page(g, guide, examples, lesson_name, cats):
    path = f'/guide/{g["key"]}/'
    title = f'{g["name"]} 뜻과 확인할 점'
    desc = describe(f'{g["name"]}: {g["plain"]}. {plain(g["what"])}')
    label = (cats.get(g['cat']) or {}).get('label', '기타')
    body = head(title + ' · 공시 사전', desc, path, page='guide',
                jsonld=[article_ld(title, desc, path, guide.data.get('checkedOn'), '공시 사전'),
                        crumbs_ld([('홈', '/'), ('공시 사전', '/guide/'), (g['name'], path)])])
    body += crumbs_html([('홈', '/'), ('공시 사전', '/guide/')])
    body += f'<article class="article guide"><h1>{e(g["name"])}</h1>'
    body += f'<p class="guide-plain">쉬운 이름 · <b>{e(g["plain"])}</b></p>'
    body += f'<p class="meta">공시 사전 · 분류 {e(label)} · 내용 확인 {e(guide.data.get("checkedOn", ""))}</p>'
    body += '<h2>이 공시는 무엇인가요?</h2>' + paras(g['what'])
    body += '<h2>왜 확인할까요?</h2>' + paras(g['why'])
    body += '<h2>원문에서 이것부터 보세요</h2><ol class="checks">' + ''.join(f'<li>{inline(x)}</li>' for x in g['check']) + '</ol>'
    if g.get('caution'):
        body += '<h2>헷갈리기 쉬운 점</h2>' + paras(g['caution'])
    body += ('<h2>원문은 이렇게 열어요</h2><ol class="checks"><li>아래 「최근 이 공시를 낸 회사」나 기업 리서치에서 <b>DART 원문</b>을 눌러요.</li>'
             '<li>원문 맨 위의 <b>요약 표</b>부터 읽어요. 무엇을, 얼마에, 언제 하는지가 모여 있어요.</li>'
             '<li>금액이 나오면 <b>자기자본 대비 비율</b>을 함께 봐요. 회사 크기에 비해 얼마나 큰 일인지 알 수 있어요.</li></ol>')
    if g.get('lesson') in lesson_name:
        body += f'<p class="small">더 공부하기: <a href="{study_url("lesson", g["lesson"])}">{e(lesson_name[g["lesson"]])}</a></p>'
    body += '<h2>최근 이 공시를 낸 회사</h2>'
    if examples:
        body += '<ul class="list list-card">' + ''.join(
            f'<li><a href="/company/{e(x["code"])}/"><b>{e(x["name"] or x["code"])}</b></a> <span class="meta">{e(x["date"] or "")}</span><br>'
            f'<span class="small">{e(x["title"] or "")}</span>'
            + (f' · <a class="small" href="{e(x["url"])}" target="_blank" rel="noopener">DART 원문 ↗</a>' if x.get('url') else '') + '</li>'
            for x in examples) + '</ul>'
        body += '<p class="meta">GAEO가 모은 자료 기간 안에서 가장 최근 것부터 보여 드려요. 중요도 순서가 아니에요.</p>'
    else:
        body += '<p class="small">지금 자료 기간에는 이 제목의 공시가 없어요. 없다는 확정은 아니에요(자료를 모은 기간 밖일 수 있어요).</p>'
    same = [x for x in guide.items if x['cat'] == g['cat'] and x['key'] != g['key']][:8]
    if same:
        body += '<h2>같은 분류의 다른 공시</h2><p class="chip-row">' + ''.join(
            f'<a class="chip-link" href="/guide/{e(x["key"])}/">{e(x["name"])}</a>' for x in same) + '</p>'
    body += '<p class="note">공시를 이해하도록 돕는 공부용 설명이에요. 특정 회사의 매수·매도를 권하지 않아요.</p>'
    body += SHARE + '</article>\n'
    return path, body + TAIL


def guide_index(guide, cats, counts):
    path = '/guide/'
    desc = '공시 제목이 어려울 때 찾아보는 초보자용 공시 사전. 유상증자·전환사채·대량보유·자기주식처럼 자주 나오는 공시의 뜻과 원문에서 확인할 점을 쉬운 말로 정리했어요.'
    body = head('공시 사전', desc, path, page='guide', main='wrap', og_type='website',
                jsonld=[crumbs_ld([('홈', '/'), ('공시 사전', path)])])
    body += ('<h1>공시 사전</h1><p class="lede">공시 제목이 어려울 때 찾아보는 <b>초보자용 사전</b>이에요. '
             '공시마다 <b>쉬운 이름 · 무슨 내용인지 · 왜 확인하는지 · 원문에서 볼 곳</b>을 정리했어요.</p>'
             '<div class="search" role="search"><input id="guide-q" placeholder="예: 유상증자, 전환사채, 대량보유" '
             'aria-label="공시 사전 검색" data-filter="guide-list"></div>'
             '<p class="meta" id="guide-count" aria-live="polite"></p><div id="guide-list">')
    order = list(cats)
    for cat in sorted({g['cat'] for g in guide.items}, key=lambda c: order.index(c) if c in order else 99):
        items = [g for g in guide.items if g['cat'] == cat]
        body += f'<section class="guide-group" data-group><h2>{e((cats.get(cat) or {}).get("label", "기타"))}</h2><ul class="guide-list">'
        for g in items:
            n = counts.get(g['key'], 0)
            body += (f'<li data-text="{e(g["name"] + " " + g["plain"] + " " + " ".join(g["match"]))}"><a href="/guide/{e(g["key"])}/"><b>{e(g["name"])}</b></a>'
                     f'<span class="small">{e(g["plain"])}</span>' + (f'<span class="meta">최근 자료 {n}건</span>' if n else '') + '</li>')
        body += '</ul></section>'
    body += '</div><p class="note">공부용 설명이에요. 법령 기준(기한·금액)은 내용 확인일 기준이라 바뀌었을 수 있어요.</p>\n'
    return path, body + TAIL


# ── 공부 글 쪽(/snap/…) ─────────────────────────────────────────────────────────
STUDY_NOTE = ('<p class="note past"><b>작성 당시 기준의 공부 기록</b>입니다. 지금의 매수·매도 추천이 아니며, 숫자와 사실은 작성일 이후 바뀌었을 수 있습니다.{extra}</p>')


def related_items(it, items, n=3):
    same = [x for x in items if x['id'] != it['id'] and x.get('cat') == it.get('cat')]
    same.sort(key=lambda x: abs(x['id'] - it['id']))
    rest = [x for x in sorted(items, key=lambda x: (x.get('date') or '', x['id']), reverse=True) if x['id'] != it['id'] and x not in same]
    return (same + rest)[:n]


def article_page(kind, it, items, company_names):
    var, label, list_url, page, cats = SECTIONS[kind]
    path = study_url(kind, it['id'])
    cat = cats.get(it.get('cat'), '')
    desc = describe(it.get('summary') or it.get('name'))
    crumbs = [('홈', '/'), (label, list_url)]
    body = head(f'{it["name"]} · {label}', desc, path, page=page,
                jsonld=[article_ld(it['name'], desc, path, it.get('date'), label), crumbs_ld(crumbs + [(it['name'], path)])])
    body += crumbs_html(crumbs)
    body += f'<article class="article"><h1>{e(it["name"])}</h1>'
    body += '<p class="meta">' + e(' · '.join(x for x in [it.get('date'), cat, it.get('tag')] if x)) + '</p>'
    if kind == 'study':
        body += STUDY_NOTE.format(extra=' 옮기면서 출처 권리가 불분명한 수치 문장(컨센서스·목표주가·수급·주가배수·옛 수집 시세 등)은 뺐습니다.' if it.get('sanitized') else '')
    elif kind in ('lesson', 'estate'):
        body += f'<p class="note">작성일 {e(it.get("date") or "")} 기준이에요. 제도·세율·금리는 바뀌었을 수 있으니 공식 자료로 한 번 더 확인하세요.</p>'
    if it.get('summary'):
        body += '<div class="tldr"><p class="tldr-label">한눈에 보기</p>' + ''.join(
            f'<p>{inline(s)}</p>' for s in split_sentences(it['summary'])) + '</div>'
    code = str(it.get('code') or '')
    if kind == 'study' and code in company_names:
        body += f'<p class="small"><a href="/company/{e(code)}/">{e(it["name"])}의 최근 공시·재무 변화 보기 →</a></p>'
    if kind == 'calc':
        spec = json.dumps({'id': it['id'], 'calcType': it.get('calcType')})
        body += '<div id="calc-widget" data-calc="' + e(spec) + '"></div>'
    body += md_html(it.get('body'))
    sources = [s for s in it.get('sources') or [] if isinstance(s, dict) and str(s.get('url') or '').startswith('https://')]
    if sources:
        body += '<h2>참고한 자료</h2><ul class="sources">' + ''.join(
            f'<li><a href="{e(s["url"])}" target="_blank" rel="noopener nofollow">{e(s.get("name") or s["url"])}</a></li>' for s in sources) + '</ul>'
    body += SHARE + '</article>\n'
    rel = related_items(it, items)
    if rel:
        body += '<section class="section related" aria-labelledby="rel-h"><h2 id="rel-h">같이 읽으면 좋은 글</h2><div class="grid three">' + ''.join(
            f'<a class="card link-card" href="{study_url(kind, x["id"])}"><span class="chip neutral">{e(cats.get(x.get("cat"), label))}</span>'
            f'<span class="lc-title">{e(x["name"])}</span><span class="lc-sub">{e(describe(x.get("summary"), 70))}</span></a>' for x in rel) + '</div></section>\n'
    scripts = '<script src="/assets/calc-widgets.js"></script>\n' if kind == 'calc' else ''
    return path, body + tail(scripts)


def snap_index(content):
    path = '/snap/index.html'
    body = head('공부 노트 전체 목록', '종목 공부·투자 공부·부동산 공부·계산기 글을 한 쪽에 모았어요. 모두 작성 당시 기준이며 매수·매도 추천이 아닙니다.', path,
                page='', main='wrap read', og_type='website', jsonld=[crumbs_ld([('홈', '/'), ('공부 노트 전체 목록', path)])])
    body += '<h1>공부 노트 전체 목록</h1><p class="lede">모든 글은 작성 당시 기준이에요. 새 글이 먼저 나와요.</p>'
    for kind in ('study', 'lesson', 'estate', 'calc'):
        var, label, list_url, _, cats = SECTIONS[kind]
        items = sorted(content[var], key=lambda x: (x.get('date') or '', x['id']), reverse=True)
        body += f'<h2>{e(label)} <span class="meta">{len(items)}편</span></h2><ul class="list">' + ''.join(
            f'<li><a href="{study_url(kind, x["id"])}"><b>{e(x["name"])}</b></a> <span class="meta">{e(x.get("date") or "")}'
            f'{" · " + e(cats[x["cat"]]) if x.get("cat") in cats else ""}</span></li>' for x in items) + '</ul>'
    return path, body + TAIL


# ── 회사별 요약(/company/<코드>/) ─────────────────────────────────────────────────
def company_page(code, name, ctx):
    changes, financial, timelines, guide = ctx['changes'], ctx['financial'], ctx['timelines'], ctx['guide']
    c = (changes.get('companies') or {}).get(code)
    fc = (financial.get('companies') or {}).get(code)
    tc = (timelines.get('companies') or {}).get(code)
    filings = ctx['filings_by_code'].get(code, [])
    path = f'/company/{code}/'
    n = len(filings)
    latest = filings[0]['date'] if filings else None
    desc = (f'{name}({code})의 최근 공시 {n}건' + (f'(가장 최근 {latest})' if latest else '')
            + '과 사업보고서 재무 변화, 공시 흐름을 초보자도 읽기 쉽게 정리했어요. 출처 OpenDART · 매수·매도 추천 아님.')
    thin = not filings and not (fc and fc.get('rows')) and not (tc and tc.get('timelines'))
    crumbs = [('홈', '/'), ('기업 리서치', '/disclosure-research.html')]
    body = head(f'{name}({code}) 공시·재무 변화 쉽게 보기', desc, path, page='research', og_type='website', noindex=thin,
                jsonld=[crumbs_ld(crumbs + [(name, path)])])
    body += crumbs_html(crumbs)
    body += (f'<div class="company-head"><h1>{e(name)} <span class="chip neutral">{e(code)}</span></h1>'
             f'<p class="meta">자료 기준일 {e(ctx["asOf"])} · 하루 2회 갱신 · 출처 금융감독원 OpenDART</p>'
             f'<p class="cc-actions"><a class="btn btn-primary" href="/disclosure-research.html?code={e(code)}">탭으로 자세히 보기</a>'
             f'<a class="btn btn-quiet" href="{e(dart_search(name))}" target="_blank" rel="noopener">DART에서 검색<span aria-hidden="true"> ↗</span></a></p></div>')
    body += '<p class="note">회사가 낸 <b>공시 사실</b>만 모아 쉬운 말로 풀었어요. 주가 예측이나 매수·매도 추천이 아니에요.</p>'

    body += '<h2>최근 공시</h2>'
    if filings:
        body += '<ul class="filing-list">'
        for f in filings[:15]:
            x = guide.explain(f['title'], f['isCorrection'])
            chip = '<span class="chip neutral">정정</span>' if f['isCorrection'] else ''
            plain_link = (f'<a class="f-plain" href="{x["href"]}">{e(x["plain"])}</a>' if x['href'] else '')
            link = f'<a href="{e(f["url"])}" target="_blank" rel="noopener">{e(f["title"])}<span aria-hidden="true"> ↗</span></a>' if f.get('url') else e(f['title'])
            body += f'<li><span class="f-date">{e(f["date"] or "")}</span> {chip}{link}' + (f'<br><span class="small">쉬운 이름 · </span>{plain_link}' if plain_link else '') + '</li>'
        body += '</ul>'
        if n > 15:
            body += f'<p class="meta">이 밖에 {n - 15}건은 <a href="/disclosure-research.html?code={e(code)}">탭 화면</a>에서 볼 수 있어요.</p>'
    else:
        body += '<p class="small">GAEO가 모은 자료 기간에 이 회사 공시가 없어요. 공시가 없었다는 확정은 아니에요.</p>'

    if c and c.get('changes'):
        body += '<h2>공시 변화</h2><ul>' + ''.join(f'<li>{e(x.get("text") or "")}</li>' for x in c['changes'][:4]) + '</ul>'

    body += '<h2>재무 변화 <span class="meta">사업보고서 · 1년 단위</span></h2>'
    if fc and fc.get('rows'):
        periods = [p['year'] for p in fc.get('periods') or []][-3:]
        pairs = fc.get('comparablePairs') or []
        last = pairs[-1] if pairs else None
        rows = [r for r in fc['rows'] if r.get('account') in COMPANY_ACCOUNTS]
        body += f'<p class="small">{e(fc.get("fsDivLabel") or "")} 재무제표 기준이에요. 결측은 0이 아니에요.</p><div class="tbl"><table><thead><tr><th>항목</th>'
        body += ''.join(f'<th>{e(y)}</th>' for y in periods) + '<th>최근 변화</th></tr></thead><tbody>'
        lines = []
        for r in rows:
            ch = (r.get('changes') or {}).get(last['to']) if last else None
            vals = r.get('values') or {}
            cells = ''.join('<td>' + e(krw(vals[y])) + '</td>' if y in vals else '<td class="meta">—</td>' for y in periods)
            change = e(pct(ch)) if ch else '<span class="meta">견주지 않음</span>'
            body += '<tr><td>' + e(r.get('label') or '') + '</td>' + cells + '<td>' + change + '</td></tr>'
            if ch and r.get('account') in KEY_ACCOUNTS:
                before, after = vals.get(last['from']), vals.get(last['to'])
                if isinstance(before, (int, float)) and isinstance(after, (int, float)) and before > 0 > after:
                    lines.append(f'{r.get("label")}이(가) {last["from"]}년 흑자에서 {last["to"]}년 적자로 바뀌었어요.')
                elif isinstance(before, (int, float)) and isinstance(after, (int, float)) and before < 0 < after:
                    lines.append(f'{r.get("label")}이(가) {last["from"]}년 적자에서 {last["to"]}년 흑자로 바뀌었어요.')
                elif isinstance(ch.get('pct'), (int, float)) and abs(ch['pct']) >= 20:
                    lines.append(f'{r.get("label")}이(가) {last["from"]}년보다 {last["to"]}년에 {"늘었어요" if ch["pct"] > 0 else "줄었어요"} ({pct(ch)}).')
        body += '</tbody></table></div>'
        if lines:
            body += '<ul>' + ''.join(f'<li>{e(x)}</li>' for x in lines) + '</ul>'
        body += '<p class="meta">한 해의 변화에는 자산 매각·회계 변경 같은 일회성 요인이 섞일 수 있어요. 증감률만으로 좋고 나쁨을 단정하지 않아요.</p>'
    elif code in set(financial.get('notCollectedTickers') or []):
        body += '<p class="small">재무 자료를 아직 받지 못했어요(하루에 몇십 곳씩 차례로 채워요). 재무가 없다는 뜻이 아니에요.</p>'
    else:
        body += '<p class="small">이 자료에 재무 기록이 없어요.</p>'

    if tc and tc.get('timelines'):
        body += '<h2>사건 흐름</h2>'
        stage_vocab = timelines.get('stageVocabulary') or {}
        for t in sorted(tc['timelines'], key=lambda t: str(t.get('latestReceivedOn') or ''), reverse=True)[:3]:
            items = sorted(t.get('items') or [], key=lambda i: str(i.get('receivedOn') or ''))
            body += (f'<div class="tl-block"><h3>{e(t.get("label") or "")}</h3><p class="meta">지금 확인된 단계 · '
                     f'{e(stage_vocab.get(t.get("latestStage"), t.get("latestStage") or ""))} · 최근 {e(t.get("latestReceivedOn") or "")}</p><ol class="tl">'
                     + ''.join(f'<li><p class="tl-date">{e(i.get("receivedOn") or "")}</p><p class="tl-stage">{e(i.get("stageLabel") or "")}</p>'
                               f'<p class="tl-title">{e(i.get("title") or "")}</p></li>' for i in items[-4:]) + '</ol></div>')
        body += '<p class="meta">다음 단계 공시를 못 찾은 것은 「안 했다」는 뜻이 아니에요. 자료 기간 밖이거나 진행 중일 수 있어요.</p>'

    notes = ctx['study_by_code'].get(code, [])
    past = ctx['past_by_code'].get(code, [])
    if notes or past:
        body += '<h2>이 회사 공부 노트</h2><ul>' + ''.join(
            f'<li><a href="{study_url("study", x["id"])}">{e(x["name"])} 종목 공부</a> <span class="meta">{e(x.get("date") or "")} · 작성 당시 기준</span></li>' for x in notes) + ''.join(
            f'<li><a href="/research/deep-analysis/{e(code)}/{stamp(r["snapshotId"])}/">과거 분석 기록 · {e(r["title"])}</a> <span class="meta">{e(r["analyzedAt"][:10])}</span></li>' for r in past) + '</ul>'

    keys, seen = [], set()
    for f in filings:
        x = guide.explain(f['title'], False)
        if x['guide'] and x['guide']['key'] not in seen and x['guide']['key'] != 'other-general':
            seen.add(x['guide']['key'])
            keys.append(x['guide'])
    if keys:
        body += '<h2>이 공시들이 어렵다면</h2><p class="chip-row">' + ''.join(
            f'<a class="chip-link" href="/guide/{e(g["key"])}/">{e(g["name"])}</a>' for g in keys[:8]) + '</p>'
    body += (f'<p class="source-bar"><span>출처: 금융감독원 OpenDART · 공시 목록·사업보고서</span><span>자료 생성 {e(kst(ctx["generatedAt"]))}</span>'
             f'<a href="{e(dart_search(name))}" target="_blank" rel="noopener">DART에서 원문 확인 ↗</a></p>')
    body += SHARE
    return path, body + TAIL, thin, latest


# ── 홈 ─────────────────────────────────────────────────────────────────────────
def home_sections(contract, dart, vocab, study, lessons, guide=None):
    """홈 화면 조각. 숫자는 contract.json 의 실제 값만, 설명은 공시 사전(없으면 분류표의 일반적인 읽는 법)만 쓴다."""
    files = {f['kind']: f for f in contract.get('files', [])}
    names = contract.get('companyNames') or {}
    cats = vocab['categories']
    guide = guide or Guide(load_guides(), cats)
    status = (
        '<dl class="facts-strip" aria-label="자료 현황">'
        f'<div><dt>자료 기준일</dt><dd>{e(contract["asOf"])}</dd></div>'
        f'<div><dt>추적 회사</dt><dd>{len(names):,}곳</dd></div>'
        f'<div><dt>재무 자료가 있는 회사</dt><dd>{files["financial_changes"]["companies"]:,}곳</dd></div>'
        f'<div><dt>사건 흐름이 있는 회사</dt><dd>{files["event_timelines"]["companies"]:,}곳</dd></div>'
        '<div><dt>갱신</dt><dd>하루 2회 · OpenDART</dd></div></dl>'
        f'<p class="meta strip-note">자료 생성 {e(kst(contract["generatedAt"]))} (한국시간) · 출처 금융감독원 OpenDART</p>')

    items = [it for it in (dart.get('items') or []) if re.fullmatch(r'\d{6}', str(it.get('code') or ''))]
    same_day = {}
    for it in items:
        same_day[(it['code'], it.get('receiptDate'))] = same_day.get((it['code'], it.get('receiptDate')), 0) + 1
    # 회사별 가장 최근 접수일의 공시(같은 날이면 GAEO 가 나중에 모은 것) 1건 — 중요도 순위가 아니다.
    items.sort(key=lambda x: (str(x.get('receiptDate') or ''), str(x.get('detectedAt') or '')), reverse=True)
    cards, seen = [], set()
    for it in items:
        if it['code'] in seen:
            continue
        seen.add(it['code'])
        x = guide.explain(it.get('title'), it.get('isCorrection'))
        cls = x['cls']
        code, name, date = e(it['code']), e(it.get('name') or it['code']), e(ymd(it.get('receiptDate')))
        kind = '<span class="chip neutral">정정 공시</span>' if it.get('isCorrection') else '<span class="chip info">새 공시</span>'
        label = e((cats.get(cls['category']) or {}).get('label') or '기타')
        tags = ''.join(f'<span class="chip neutral">{e(cats[k]["label"])}</span>' for k in cls['tags'] if k in cats)
        n = same_day[(it['code'], it.get('receiptDate'))]
        many = f'<span class="chip neutral">같은 날 공시 {n}건</span>' if n > 1 else ''
        url = dart_url(it.get('rceptNo'))
        what = paras(x['what']) + ''.join(f'<p class="cc-note">{inline(t)}</p>' for t in x['notes'])
        check = (f'<details class="more"><summary>원문에서 무엇부터 보면 되나요?</summary><ul>'
                 + ''.join(f'<li>{inline(c)}</li>' for c in x['check']) + '</ul></details>') if x['check'] else ''
        cards.append(
            '<article class="card change-card">'
            f'<p class="cc-top"><a class="cc-company" href="/company/{code}/">{name}</a><span class="meta">{code}</span></p>'
            f'<p class="cc-meta">{kind}{many}<time datetime="{date}">{date}</time><span class="cc-cat">{label}</span>{tags}</p>'
            f'<h3 class="cc-title">{e(it.get("title") or "")}</h3>'
            + (f'<p class="cc-plain"><a href="{x["href"]}">쉬운 이름 · {e(x["plain"])}<span aria-hidden="true"> →</span></a></p>' if x['plain'] else '')
            + '<dl class="cc-qa">'
            f'<dt>무슨 내용인가요?</dt><dd>{what}</dd>'
            f'<dt>왜 확인할까요?</dt><dd>{paras(x["why"])}</dd></dl>'
            + check
            + '<p class="cc-actions">'
            + (f'<a class="btn btn-outline" href="/disclosure-research.html?code={code}&amp;tab=today">같은 날 공시 {n}건 모두 보기</a>' if n > 1
               else f'<a class="btn btn-outline" href="/company/{code}/">회사 공시 한눈에</a>')
            + (f'<a class="btn btn-quiet" href="{e(url)}" target="_blank" rel="noopener">DART 원문<span aria-hidden="true"> ↗</span></a>' if url else '')
            + '</p></article>')
        if len(cards) == 6:
            break
    today = ('<div class="grid three">' + ''.join(cards) + '</div>') if cards else (
        '<div class="state state-unknown"><p class="state-title">최근 공시 목록을 아직 받지 못했어요</p>'
        '<p>없는 자료를 빈 목록으로 채우지 않습니다. 기업 리서치에서 회사별 자료를 확인해 보세요.</p></div>')
    period = [ymd(x.get('receiptDate')) for x in (dart.get('items') or [])]
    today_note = (f'<p class="section-sub">최근 수집한 공시 중 회사별 가장 최근 자료를 보여드립니다. 중요도 순위가 아닙니다. '
                  f'공시 접수 {e(min(period))} ~ {e(max(period))} · 모은 시각 {e(dart.get("generatedAt") or "")}</p>') if period else ''

    def recent(items, kind, label):
        items = sorted(items, key=lambda x: (x.get('date') or '', x['id']), reverse=True)[:3]
        return ''.join(
            f'<a class="card link-card" href="{study_url(kind, x["id"])}"><span class="chip neutral">{label}</span>'
            f'<span class="lc-title">{e(x.get("name") or "")}</span>'
            f'<span class="lc-sub">{e(plain(first_sentence(x.get("summary"))[0]))}</span><span class="meta">{e(x.get("date") or "")}</span></a>'
            for x in items)
    studies = ('<div class="grid three">' + recent(study, 'study', '종목 공부')
               + recent(lessons, 'lesson', '투자 공부') + '</div>')

    by_name = {v: k for k, v in names.items()}
    examples = ' · '.join(f'<a class="chip-link" href="/company/{e(by_name[n])}/">{e(n)}</a>'
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


# ── 검색엔진 파일 ───────────────────────────────────────────────────────────────
def rfc822(day):
    """'2026-09-23' → RSS 날짜(한국시간 자정)."""
    try:
        t = datetime.strptime(str(day)[:10], '%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=9)))
    except ValueError:
        return None
    return t.astimezone(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')


def rss_xml(content, dart, company_names, guide, generated_at):
    items = []
    groups = {}
    for it in dart.get('items') or []:
        if re.fullmatch(r'\d{6}', str(it.get('code') or '')):
            groups.setdefault((it['code'], it.get('receiptDate')), []).append(it)
    for (code, day), rows in sorted(groups.items(), key=lambda kv: (str(kv[0][1]), kv[0][0]), reverse=True)[:25]:
        rows.sort(key=lambda r: str(r.get('rceptNo') or ''))
        name = company_names.get(code) or rows[0].get('name') or code
        t = rows[0].get('title') or ''
        plains = []
        for r in rows:
            x = guide.explain(r.get('title'), r.get('isCorrection'))
            if x['plain'] and x['plain'] not in plains:
                plains.append(x['plain'])
        items.append((ymd(day), f'{name} 새 공시: {t}' + (f' 외 {len(rows) - 1}건' if len(rows) > 1 else ''), f'/company/{code}/',
                      f'{BASE}/company/{code}/#r{rows[0].get("rceptNo")}', '새 공시',
                      f'{name}({code})이(가) {ymd(day)}에 공시 {len(rows)}건을 냈어요. ' + (' · '.join(plains[:3]) + '.' if plains else '')))
    for kind in ('study', 'lesson', 'estate', 'calc'):
        var, label = SECTIONS[kind][0], SECTIONS[kind][1]
        for x in content[var]:
            p = study_url(kind, x['id'])
            items.append((x.get('date') or '', x['name'], p, BASE + p, label, describe(x.get('summary'), 200)))
    items.sort(key=lambda r: r[0], reverse=True)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">', '<channel>',
           f'<title>{e(SITE_NAME)}</title>', f'<link>{BASE}/</link>',
           '<description>공시로 회사의 변화를 쉽게 읽고 기업·투자를 공부하는 개인 리서치 노트. 새 공부 글과 새 공시 요약. 매수·매도 추천 없음.</description>',
           '<language>ko</language>', f'<lastBuildDate>{rfc822(kst(generated_at)[:10]) or ""}</lastBuildDate>',
           f'<atom:link href="{BASE}/rss.xml" rel="self" type="application/rss+xml"/>']
    for day, title, path, guid, cat, desc in items[:60]:
        pub = rfc822(day)
        out.append('<item>' + f'<title>{e(title)}</title><link>{BASE}{path}</link><guid isPermaLink="false">{e(guid)}</guid>'
                   f'<category>{e(cat)}</category><description>{e(desc)}</description>' + (f'<pubDate>{pub}</pubDate>' if pub else '') + '</item>')
    out += ['</channel>', '</rss>', '']
    return '\n'.join(out)


def sitemap_xml(entries):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, lastmod in entries:
        lines.append(f'  <url><loc>{BASE}/{u}</loc>' + (f'<lastmod>{lastmod}</lastmod>' if lastmod else '') + '</url>')
    return '\n'.join(lines + ['</urlset>', ''])


def robots_txt():
    return (f'User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/rss.xml\n\n'
            '# 다음(Daum) 검색 등록 확인 줄 — 옛 사이트에서 그대로 옮겼다(지우면 다음 검색 소유 확인이 풀린다)\n'
            f'{DAUM_VERIFY}\n')


def llms_txt(guide, content):
    lines = ['# GAEO 기업 리서치 (gaeoteam.com)', '',
             '> 금융감독원 OpenDART 공시로 회사의 변화를 쉽게 읽고, 기업·투자를 공부하는 한국어 개인 리서치 노트입니다. '
             '매수·매도 추천, 목표주가, 수익 보장, 1:1 상담이 없습니다. 모든 공부 글은 작성 당시 기준입니다.', '',
             '## 주요 쪽',
             f'- [공시 사전]({BASE}/guide/): 공시 종류 {len(guide.items)}가지의 뜻·확인할 점을 초보자 말로 정리',
             f'- [기업 리서치]({BASE}/disclosure-research.html): 회사별 최근 공시·공시 변화·재무 변화·사건 흐름(OpenDART)',
             f'- [회사별 공시·재무 요약]({BASE}/company/005930/): /company/<종목코드 6자리>/ 모양의 정적 쪽',
             f'- [공부 노트 전체 목록]({BASE}/snap/index.html): 종목 공부 {len(content["STOCK_STUDY"])}편 · 투자 공부 {len(content["STOCK_LESSONS"])}편 · '
             f'부동산 공부 {len(content["ESTATE_LESSONS"])}편 · 계산기 {len(content["CALCULATORS"])}개',
             f'- [과거 정밀분석]({BASE}/past-analysis/): 2026년 7~8월 분석 기록(작성 당시 기준 · 현재 추천 아님)',
             f'- [새 글·새 공시 RSS]({BASE}/rss.xml)', '',
             '## 이용할 때',
             '- 공시 자료 출처: 금융감독원 전자공시시스템(DART)·OpenDART. 인용할 때 출처를 함께 적어 주세요.',
             '- 공시 원문 판단은 DART 원문을 기준으로 해 주세요. 이 사이트는 공시 원문 본문을 싣지 않고 링크만 겁니다.', '']
    return '\n'.join(lines)


def render_generated(out, content):
    """홈·기업 요약·공시 사전·회사 쪽·공부 글 쪽을 만든다(네트워크 0 · 저장소 안 자료만). 사이트맵 항목을 돌려준다."""
    def load(rel):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            return json.load(f)
    contract = load('disclosure_research/contract.json')
    with open(os.path.join(ROOT, 'config', 'disclosure_research_vocab.json'), encoding='utf-8') as f:
        vocab = json.load(f)
    cats = vocab['categories']
    guide = Guide(load_guides(), cats)
    dart = read_js_object('dart_today.js', 'DART_TODAY')
    changes = load('disclosure_research/disclosure_changes.json')
    financial = load('disclosure_research/financial_changes.json')
    timelines = load('disclosure_research/event_timelines.json')
    study, lessons = content['STOCK_STUDY'], content['STOCK_LESSONS']
    names = contract.get('companyNames') or {}
    entries = []

    parts = home_sections(contract, dart, vocab, study, lessons, guide)
    index = os.path.join(out, 'index.html')
    text = open(index, encoding='utf-8').read()
    for key, value in parts.items():
        marker = f'<!--HOME:{key}-->'
        if marker not in text:
            raise SystemExit(f'홈 화면 자리표시 없음: {marker}')
        text = text.replace(marker, value)
    open(index, 'w', encoding='utf-8', newline='\n').write(text)
    summary = research_summary(contract, changes, financial, timelines, lessons)
    with open(os.path.join(out, 'assets', 'research-summary.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(summary, f, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(out, 'assets', 'disclosure-guide.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(guide_index_json(guide), f, ensure_ascii=False, separators=(',', ':'))

    # 공부 글 쪽
    for kind in ('study', 'lesson', 'estate', 'calc'):
        items = content[SECTIONS[kind][0]]
        for it in items:
            path, page = article_page(kind, it, items, names)
            write(out, path, page)
            entries.append((path.lstrip('/'), it.get('date')))
    path, page = snap_index(content)
    write(out, path, page)

    # 공시 사전
    filings = collect_filings(changes, dart)
    lesson_name = {x['id']: x['name'] for x in lessons}
    examples, counts = {}, {}
    for f in filings:
        g = guide.find(f['title'])
        if g:
            counts[g['key']] = counts.get(g['key'], 0) + 1
            if len(examples.setdefault(g['key'], [])) < 8 and f['code'] in names:
                examples[g['key']].append(dict(f, name=names.get(f['code']) or f['name']))
    for g in guide.items:
        path, page = guide_page(g, guide, examples.get(g['key'], []), lesson_name, cats)
        write(out, path, page)
        ex = examples.get(g['key'])
        entries.append((path.lstrip('/'), ex[0]['date'] if ex else guide.data.get('checkedOn')))
    path, page = guide_index(guide, cats, counts)
    write(out, path, page)

    # 회사 쪽
    by_code = {}
    for f in filings:
        by_code.setdefault(f['code'], []).append(f)
    past = load('content/past_analysis.json')['records']
    ctx = {'changes': changes, 'financial': financial, 'timelines': timelines, 'guide': guide, 'filings_by_code': by_code,
           'asOf': contract.get('asOf'), 'generatedAt': contract.get('generatedAt'),
           'study_by_code': {}, 'past_by_code': {}}
    for x in study:
        ctx['study_by_code'].setdefault(str(x.get('code') or ''), []).append(x)
    for r in past:
        ctx['past_by_code'].setdefault(r['ticker'], []).append(r)
    indexed = 0
    for code, name in sorted(names.items()):
        path, page, thin, latest = company_page(code, name, ctx)
        write(out, path, page)
        if not thin:
            indexed += 1
            entries.append((path.lstrip('/'), latest or contract.get('asOf')))

    with open(os.path.join(out, 'rss.xml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(rss_xml(content, dart, names, guide, contract.get('generatedAt')))
    with open(os.path.join(out, 'llms.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(llms_txt(guide, content))
    return {'entries': entries, 'companies': len(summary['companies']), 'indexedCompanies': indexed, 'guides': len(guide.items),
            'asOf': contract.get('asOf')}


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
    content = load_content()
    with open(os.path.join(ROOT, 'content', 'past_analysis.json'), encoding='utf-8') as f:
        records = json.load(f)['records']
    gen = render_generated(out, content)
    entries = [(u, gen['asOf'] if u in ('', 'disclosure-research.html', 'guide/') else None) for u in STATIC_PAGES]
    for r in records:
        path, text = record_page(r)
        write(out, path, text)
        entries.append((path.lstrip('/'), (r.get('editedAt') or r['analyzedAt'])[:10]))
    write(out, '/past-analysis/', index_page(records, '/past-analysis/'))
    write(out, '/research/deep-analysis/', index_page(records, '/past-analysis/'))
    entries += [x for x in gen['entries'] if x[0] not in {u for u, _ in entries}]
    with open(os.path.join(out, 'sitemap.xml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(sitemap_xml(entries))
    with open(os.path.join(out, 'robots.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(robots_txt())
    with open(os.path.join(out, INDEXNOW_KEY + '.txt'), 'w', encoding='utf-8', newline='') as f:
        f.write(INDEXNOW_KEY)
    open(os.path.join(out, '.nojekyll'), 'w').close()
    enrich_heads(out)
    inject_chrome(out)
    base = os.environ.get('BASE_PATH', '').rstrip('/')
    rebased = rebase(out, base)
    files = sum(len(fs) for _, _, fs in os.walk(out))
    print(f'_site 조립 완료 · 파일 {files}개 · 사이트맵 {len(entries)}주소 · 과거 분석 {len(records)}쪽 · 공시 사전 {gen["guides"]}쪽 · '
          f'회사 {gen["companies"]}곳(색인 {gen["indexedCompanies"]})' + (f' · BASE_PATH {base} ({rebased}파일)' if base else ''))


if __name__ == '__main__':
    build(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '_site')))
