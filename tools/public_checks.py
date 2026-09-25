#!/usr/bin/env python3
"""공개 저장소 검사기 (네트워크 0 · LLM 0). 실패하면 exit 1 — 배포·커밋을 막는다.

  --producer-hosts  수집기 코드가 부르는 호스트가 OpenDART 뿐인지
  --tree            저장소 파일: 은퇴 자료 파일 이름 · 비밀값 모양 · 계좌/주문/Toss 흔적 · 네이버/KIND 수집 흔적
  --history         HEAD 에서 닿는 git 이력 전체에 은퇴 자료 파일 이름이 한 번도 없는지(새 저장소는 옛 이력을 가져오지 않는다)
  --site DIR        조립된 사이트(_site)가 허용목록 밖 파일을 싣지 않는지 · 글자 크기 상한 · 추적/광고/서비스워커 0
  --past            과거 정밀분석 세척본 문장 검사(tools/migration/validate_past_analysis.py)
  --all             --producer-hosts --tree --history --past (+ _site 가 있으면 --site _site)
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = os.path.relpath(os.path.abspath(__file__), ROOT).replace(os.sep, "/")

# 옛 저장소에서 네이버·KIND·모의투자 원장·개인 자료였던 파일 이름. 새 저장소에는 어떤 경로로도 들어오면 안 된다.
RETIRED = re.compile(r'(^|/)(data\.js|auto_analysis\.js|indicators[^/]*\.(js|json)|history\.js|price_history\.js|index_history\.js|'
                     r'market_history\.js|radar[^/]*\.(js|json)|rotation[^/]*\.(js|json)|market_context\.js|analysis\.js|analysis_data\.json|'
                     r'analysis_archive\.js|research_shadow\.json|price_provenance\.json|krx_list\.json|sector_map\.json|'
                     r'kind_market_action_evidence\.json|paper_public\.js|full_market_latest\.json\.gz|news_analysis\.js|'
                     r'official_price_history\.js|team_weights\.js|model_intelligence\.js|model_scoreboard\.js|dow_stats\.js|'
                     r'deep_analysis_(latest|manifest|publish)[^/]*)$|(^|/)(flow_history|paper_trading|market_universe|official_prices|'
                     r'research_archive/decisions|snap)/')
SECRET = re.compile(r'crtfc_key=[0-9a-fA-F]{40}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|'
                    r'-----BEGIN [A-Z ]*PRIVATE KEY-----|sk-[A-Za-z0-9]{32,}|gsk_[A-Za-z0-9]{32,}')
ACCOUNT = re.compile(r'X-Tossinvest-Account|accountSeq|accountNo|tossinvest\.com|/api/v1/orders|/api/v1/holdings|'
                     r'buying-power|PRIVATE_DATA_MODE|GAEO_GATEWAY_AUTH_TOKEN')
COLLECT = re.compile(r'finance\.naver\.com|stock\.naver\.com|api\.stock\.naver|polling\.finance|m\.stock\.naver|'
                     r'kind\.krx\.co\.kr/(disclosure|corpgeneral|investwarn|common)|data\.krx\.co\.kr/comm')
PRODUCER_OK_HOSTS = {'opendart.fss.or.kr', 'dart.fss.or.kr', 'gaeoteam.com'}  # gaeoteam.com: 주석 속 자기 사이트 주소
TEXT_EXT = ('.py', '.js', '.json', '.html', '.css', '.md', '.yml', '.yaml', '.txt', '.xml')
# 사이트에 실어도 되는 것(허용목록). 이 밖의 파일이 _site 에 있으면 실패.
SITE_ALLOW = re.compile(r'^(index\.html|404\.html|about\.html|disclaimer\.html|privacy\.html|contact\.html|disclosure-research\.html|'
                        r'study\.html|learn\.html|calculators\.html|sitemap\.xml|robots\.txt|\.nojekyll|CNAME|dart_today\.js|'
                        r'assets/(site\.css|site\.js|articles\.js|calc-widgets\.js|disclosure-research\.js)|'
                        r'assets/fonts/wanted-sans/(OFL\.txt|WantedSansVariable\.css|woff2/WantedSansVariable\.split\.\d+\.woff2)|'
                        r'img/[a-z0-9-]+\.(png|ico)|'
                        r'content/(stock_study|stock_lessons|estate_lessons|calculators)\.js|content/past_analysis\.json|'
                        r'disclosure_research/(contract|disclosure_changes|financial_changes|event_timelines)\.json|'
                        r'past-analysis/index\.html|research/deep-analysis/index\.html|research/deep-analysis/\d{6}/\d{4}-\d{2}-\d{2}-\d{4}/index\.html)$')
SITE_FORBIDDEN = re.compile(r'googletagmanager|google-analytics|gtag\(|adsbygoogle|googlesyndication|adfit|kvdb\.io|'
                            r'serviceWorker|navigator\.sendBeacon|localStorage\.setItem')


def tracked():
    try:
        out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split('\n')
        files = [p for p in out if p]
        if files:
            return files
    except Exception:
        pass
    found = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ('.git', '_site', '__pycache__', 'node_modules')]
        found += [os.path.relpath(os.path.join(base, f), ROOT) for f in files]
    return found


def read(rel):
    try:
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            return f.read()
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return None


def check_producer_hosts():
    bad = []
    for rel in tracked():
        if not rel.endswith('.py') or '/' in rel or rel.startswith('test_'):
            continue
        for host in re.findall(r'https?://([A-Za-z0-9.-]+)', read(rel) or ''):
            if host not in PRODUCER_OK_HOSTS:
                bad.append(f'{rel}: {host}')
    return bad


def check_tree():
    bad = []
    for rel in tracked():
        if RETIRED.search(rel):
            bad.append(f'은퇴 자료 파일: {rel}')
        if rel == SELF or not rel.endswith(TEXT_EXT) or rel.startswith('site/assets/fonts/'):
            continue
        text = read(rel)
        if text is None:
            continue
        for rx, label in ((SECRET, '비밀값 모양'), (ACCOUNT, '계좌·주문·Toss 흔적'), (COLLECT, '네이버·KIND 수집 주소')):
            m = rx.search(text)
            # 문서와 시험(금지 목록을 적어 두는 곳)은 이름을 말할 수 있다. 비밀값 모양은 어디서도 안 된다.
            if m and not (rel.startswith(('docs/', 'test_')) and label != '비밀값 모양'):
                bad.append(f'{label}: {rel}: {m.group(0)[:40]}')
    return bad


def check_history():
    try:
        out = subprocess.run(['git', 'log', 'HEAD', '--name-only', '--pretty=format:'], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
    except Exception as ex:
        return [f'git 이력을 읽지 못함: {ex}']
    try:
        shallow = subprocess.run(['git', 'rev-parse', '--is-shallow-repository'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:
        shallow = 'unknown'
    if shallow == 'true':
        return ['얕은 clone 이라 이력 전체를 볼 수 없다 — fetch-depth: 0 으로 받는다']
    return sorted({f'이력에 은퇴 자료 파일: {p}' for p in out.split('\n') if p and RETIRED.search(p)})


def check_site(site):
    bad = []
    if not os.path.isdir(site):
        return [f'사이트 폴더 없음: {site}']
    for base, _, files in os.walk(site):
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), site).replace(os.sep, '/')
            if not SITE_ALLOW.match(rel):
                bad.append(f'허용목록 밖 파일이 사이트에 있음: {rel}')
                continue
            if rel.endswith(('.html', '.js', '.css', '.json', '.xml', '.txt')) and 'fonts/' not in rel:
                with open(os.path.join(base, f), encoding='utf-8') as fh:
                    text = fh.read()
                for rx, label in ((SITE_FORBIDDEN, '추적·광고·서비스워커'), (SECRET, '비밀값 모양'), (ACCOUNT, '계좌·주문·Toss 흔적'),
                                  (COLLECT, '네이버·KIND 수집 주소')):
                    m = rx.search(text)
                    if m:
                        bad.append(f'{label}: {rel}: {m.group(0)[:40]}')
                if rel.endswith(('.css', '.html')):
                    for size in re.findall(r'font-size\s*:\s*(\d+(?:\.\d+)?)px', text):
                        if float(size) > 30:
                            bad.append(f'글자 크기 상한(30px) 초과: {rel}: {size}px')
    return bad


def check_past():
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'migration', 'validate_past_analysis.py'),
                        os.path.join(ROOT, 'content', 'past_analysis.json')], capture_output=True, text=True)
    return [] if r.returncode == 0 else ['과거 정밀분석 세척본 검사 실패:\n' + r.stdout[-2000:]]


def main(argv):
    checks = []
    if '--producer-hosts' in argv or '--all' in argv:
        checks.append(('producer-hosts', check_producer_hosts()))
    if '--tree' in argv or '--all' in argv:
        checks.append(('tree', check_tree()))
    if '--history' in argv or '--all' in argv:
        checks.append(('history', check_history()))
    if '--past' in argv or '--all' in argv:
        checks.append(('past', check_past()))
    if '--site' in argv:
        checks.append(('site', check_site(os.path.abspath(argv[argv.index('--site') + 1]))))
    elif '--all' in argv and os.path.isdir(os.path.join(ROOT, '_site')):
        checks.append(('site', check_site(os.path.join(ROOT, '_site'))))
    if not checks:
        print(__doc__)
        return 2
    failed = False
    for name, problems in checks:
        print(f'[{name}] {"PASS" if not problems else "FAIL"} ({len(problems)})')
        for p in problems[:50]:
            print('  - ' + p)
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
