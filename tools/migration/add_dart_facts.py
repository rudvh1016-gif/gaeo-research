#!/usr/bin/env python3
"""과거 정밀분석 세척본에 DART 재무 사실을 되살린다 (1회용 · 네트워크 0 · LLM 0 · 2026-09-24).

왜: 이전 세척 때 숫자·%·ROE 를 출처와 무관하게 모두 뺐다. 그것은 법률 기준이 아니라 내부 필터였다.
공개 이용 근거가 확인된 사실(OpenDART 사업보고서 구조화 재무수치 · config 의 opendart derivedPublication
조건부 허용)과 그 값으로 한 자체 계산은 출처·범위를 붙여 살린다. 근거 없는 과거 시세·수급·제3자 수치는
여전히 싣지 않는다.

원칙
  · 값은 저장소 안 dart_financials/<종목>.json 에서만 읽는다(새 수집 0). 없는 값은 만들지 않는다.
  · 이것은 **이번 편집(2026-09-24)에 덧붙인 사실**이다 — 당시 분석의 근거였다고 쓰지 않는다.
  · 연결/별도가 다른 두 해는 비교하지 않는다. 전년 값이 0 이하면 증감률을 만들지 않는다.
  · validate_past_analysis.py 가 같은 파일로 다시 계산해 대조한다(값을 손으로 고치면 실패).
사용: python3 tools/migration/add_dart_facts.py content/past_analysis.json
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EDITED_AT = '2026-09-24'
FS = {'CFS': '연결', 'OFS': '별도'}
SOURCE = 'OpenDART 단일회사 전체 재무제표 · 사업보고서(연간) · dart_financials/{t}.json'


def load_fin(ticker, root=ROOT):
    path = os.path.join(root, 'dart_financials', f'{ticker}.json')
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        doc = json.load(f)
    return doc.get('years') if isinstance(doc.get('years'), dict) else None


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def facts_for(ticker, analyzed_year, root=ROOT):
    """분석 연도의 직전 회계연도(=그해 3월 전후 공시된 사업보고서)와 그 전해를 쓴다. 값이 없으면 빈 목록."""
    years = load_fin(ticker, root)
    if not years:
        return []
    y1, y0 = str(analyzed_year - 1), str(analyzed_year - 2)
    cur, prev = years.get(y1) or {}, years.get(y0) or {}
    if cur.get('status') != 'OK':
        return []
    fs = cur.get('fsDiv')
    v = cur.get('values') or {}
    out = []
    rev, op, ni, eq = (num(v.get(k)) for k in ('revenue', 'operatingIncome', 'netIncome', 'totalEquity'))
    same_basis = prev.get('status') == 'OK' and prev.get('fsDiv') == fs
    pv = prev.get('values') or {}
    prev_rev = num(pv.get('revenue')) if same_basis else None
    if rev is not None and prev_rev is not None and prev_rev > 0:
        out.append({'kind': 'REVENUE_YOY', 'year': y1, 'vs': y0, 'fsDiv': fs,
                    'value': round((rev - prev_rev) / prev_rev * 100, 1),
                    'text': f'{y1}년 매출액은 {y0}년보다 {round((rev - prev_rev) / prev_rev * 100, 1)}% {"늘었다" if rev >= prev_rev else "줄었다"}({FS.get(fs, fs)} 기준).'})
    if rev is not None and op is not None and rev > 0:
        out.append({'kind': 'OPERATING_MARGIN', 'year': y1, 'fsDiv': fs, 'value': round(op / rev * 100, 1),
                    'text': f'{y1}년 영업이익률(영업이익 ÷ 매출액)은 {round(op / rev * 100, 1)}%였다({FS.get(fs, fs)} · 자체 계산).'})
    if ni is not None and eq is not None and eq > 0:
        out.append({'kind': 'ROE_YEAR_END_EQUITY', 'year': y1, 'fsDiv': fs, 'value': round(ni / eq * 100, 1),
                    'text': f'{y1}년 ROE(당기순이익 ÷ 기말 자본총계)는 {round(ni / eq * 100, 1)}%였다({FS.get(fs, fs)} · 자체 계산 · 평균자본이 아닌 기말 기준).'})
    for f in out:
        f['source'] = SOURCE.format(t=ticker)
    return out


def main(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    added = 0
    for r in data['records']:
        r['editedAt'] = EDITED_AT
        r['sectionOrigin'] = {
            'whatWeSaw': 'ORIGINAL_RESTATED', 'whyViewed': 'ORIGINAL_RESTATED',
            'wrongIf': 'EDIT_SUPPLEMENT', 'studyNext': 'EDIT_SUPPLEMENT', 'dartCheck': 'EDIT_SUPPLEMENT'}
        facts = facts_for(r['ticker'], int(r['analyzedAt'][:4]))
        if facts:
            r['dartFacts'] = facts
            added += 1
        else:
            r.pop('dartFacts', None)
    data['editedAt'] = EDITED_AT
    data['sectionOriginVocabulary'] = {
        'ORIGINAL_RESTATED': '당시 기록을 수치 없이 다시 정리한 것',
        'EDIT_SUPPLEMENT': f'{EDITED_AT} 편집에서 정리·보충한 것 — 당시의 판단으로 읽지 않는다',
        'dartFacts': f'{EDITED_AT} 편집에서 OpenDART 사업보고서 값으로 덧붙인 사실과 자체 계산 — 당시 분석의 근거가 아니다'}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(json.dumps({'records': len(data['records']), 'withDartFacts': added}, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1])
