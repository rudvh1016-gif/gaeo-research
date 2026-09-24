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
<main id="main" class="wrap">
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
    base = os.environ.get('BASE_PATH', '').rstrip('/')
    rebased = rebase(out, base)
    files = sum(len(fs) for _, _, fs in os.walk(out))
    print(f'_site 조립 완료 · 파일 {files}개 · 과거 분석 {len(records)}쪽' + (f' · BASE_PATH {base} ({rebased}파일)' if base else ''))


if __name__ == '__main__':
    build(os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '_site')))
