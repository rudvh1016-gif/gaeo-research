#!/usr/bin/env python3
"""IndexNow 알림 — 배포된 sitemap 과 새 sitemap 을 견줘 **바뀐 주소만** 검색엔진(빙·네이버 등 IndexNow 참여 엔진)에 알린다.

배포 워크플로(.github/workflows/pages.yml) 전용. 수집기가 아니다(OpenDART·네이버·KIND 를 부르지 않는다).
  plan   --new _site/sitemap.xml --live https://gaeoteam.com/sitemap.xml --out indexnow_urls.txt   (배포 전)
  submit --urls indexnow_urls.txt                                                                  (배포 뒤)
네트워크: plan 은 자기 사이트 sitemap 1회, submit 은 api.indexnow.org 1회. 개인정보·비밀값 없음 — 키는 사이트에
공개하는 파일(/<키>.txt)로 소유를 확인하는 공개 값이다. 알림이 실패해도 배포 실패로 치지 않는다.
"""
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

KEY = 'd96e570cc9c1cbbad053bee2b14a7e5d'
HOST = 'gaeoteam.com'
ENDPOINT = 'https://api.indexnow.org/indexnow'
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


def parse(blob):
    root = ET.fromstring(blob)
    return {u.findtext('s:loc', namespaces=NS): (u.findtext('s:lastmod', namespaces=NS) or '')
            for u in root.findall('s:url', NS)}


def plan(new_path, live_url, out_path):
    with open(new_path, 'rb') as f:
        new = parse(f.read())
    try:
        req = urllib.request.Request(live_url, headers={'User-Agent': 'gaeo-indexnow/1'})
        with urllib.request.urlopen(req, timeout=30) as r:
            live = parse(r.read())
    except Exception as ex:  # 처음 배포·일시 오류 — 전체를 한 번 알린다(최대 10,000개)
        print(f'배포된 sitemap 을 읽지 못함({ex}) — 전체 주소를 알린다')
        live = {}
    changed = [u for u, m in new.items() if u and u.startswith(f'https://{HOST}/') and (u not in live or live[u] != m)]
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(''.join(u + '\n' for u in changed))
    print(f'IndexNow 대상 {len(changed)}개 / sitemap {len(new)}개')
    return 0


def submit(urls_path):
    with open(urls_path, encoding='utf-8') as f:
        urls = [u.strip() for u in f if u.strip()][:10000]
    if not urls:
        print('바뀐 주소 없음 — 보내지 않는다')
        return 0
    body = json.dumps({'host': HOST, 'key': KEY, 'keyLocation': f'https://{HOST}/{KEY}.txt', 'urlList': urls}).encode('utf-8')
    req = urllib.request.Request(ENDPOINT, data=body, headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f'IndexNow HTTP {r.status} · {len(urls)}개 알림')
    except urllib.error.HTTPError as ex:
        print(f'IndexNow HTTP {ex.code} · {len(urls)}개 — 알림만 실패(배포는 그대로)')
    except Exception as ex:
        print(f'IndexNow 연결 실패({ex}) — 알림만 실패(배포는 그대로)')
    return 0


def main(argv):
    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default
    if argv[:1] == ['plan']:
        return plan(arg('--new', '_site/sitemap.xml'), arg('--live', f'https://{HOST}/sitemap.xml'), arg('--out', 'indexnow_urls.txt'))
    if argv[:1] == ['submit']:
        return submit(arg('--urls', 'indexnow_urls.txt'))
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
