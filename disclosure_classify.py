#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공시 제목 분류 — 공시 연구 생산자(build_disclosure_research.py)와 사이트 조립기(tools/build_site.py)가 함께 쓴다.

분류 단어는 config/disclosure_research_vocab.json 의 categories[*].terms 다. 한 제목이 여러 분류 단어에 걸릴 때
설정 파일의 순서(우연)로 고르지 않고 아래 규칙으로 고른다(2026-09-26 · 네트워크 0 · LLM 0).

  ① 더 구체적인 표현이 이긴다 — 다른 일치 구간 안에 통째로 들어가는 더 짧은 일치는 따로 세지 않는다.
     예: '증권발행실적' 안의 '실적' · '동일인등출자' 안의 '출자' · '액면분할' 안의 '분할'.
  ② 무슨 일이 있었는지(사건 분류)가 어떤 서식·절차인지(설정의 role="form")보다 먼저다.
     예: '증권신고서(합병)' → 주 분류 합병·분할, 증권신고·발행은 보조.
  ③ 같은 종류끼리는 괄호 밖이 괄호 안보다, 제목 뒤쪽이 앞쪽보다 먼저다(한국어 제목은 뒤쪽 말이 공시의 행위).
     예: '주권매매거래정지 (풍문 또는 보도 관련)' → 거래정지 · '최대주주변경을수반하는주식담보제공계약체결' → 채무보증·담보.
  ④ 제목이 스스로 "A또는B" 라고 하면(예: 유상증자또는주식관련사채등의발행결과) 제목만으로는 어느 쪽인지 모른다 —
     먼저 나온 A 를 주 분류로 두고 tie=True(애매함)로 알린다.

주 분류가 아닌 분류는 버리지 않고 보조 분류(tags)로 남긴다 — 실제로 두 성격인 공시를 하나로 거짓 정리하지 않는다.
규칙으로 순서가 갈리지 않을 때도 설정 순서로 주 분류를 정하되 tie=True 로 알린다(화면은 한 가지 읽는 법을 붙이지 않는다).
"""
import re


def bare(title):
    """정정 표식([기재정정] 등)과 공백을 뺀 제목."""
    return re.sub(r"\s+", "", re.sub(r"\[[^\]]*\]", "", str(title or "")))


def _depths(text):
    depth, out = 0, []
    for ch in text:
        if ch == "(":
            out.append(depth)
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
            out.append(depth)
        else:
            out.append(depth)
    return out


def classify(title, categories):
    """제목 → {"category": 주 분류, "tags": [보조 분류…], "tie": bool}. 분류 단어가 없으면 category="other"."""
    text = bare(title)
    depth = _depths(text)
    order = {k: i for i, k in enumerate(categories)}
    found = []
    for key, spec in categories.items():
        for term in spec.get("terms") or []:
            word = term.replace(" ", "")
            at = text.find(word) if word else -1
            while at >= 0:
                found.append((key, at, at + len(word)))
                at = text.find(word, at + 1)
    kept = [m for m in found
            if not any(o[1] <= m[1] and m[2] <= o[2] and o[2] - o[1] > m[2] - m[1] for o in found)]
    if not kept:
        return {"category": "other", "tags": [], "tie": False}

    def rank(m):
        form = (categories.get(m[0]) or {}).get("role") == "form"
        return (form, depth[m[1]], -m[2], -(m[2] - m[1]))

    best = {}
    for m in kept:
        if m[0] not in best or rank(m) < rank(best[m[0]]):
            best[m[0]] = m
    ranked = sorted(best.values(), key=lambda m: rank(m) + (order[m[0]],))
    tie = len(ranked) > 1 and rank(ranked[0]) == rank(ranked[1])
    if len(ranked) > 1 and rank(ranked[0])[:2] == rank(ranked[1])[:2]:
        a, b = sorted(ranked[:2], key=lambda m: m[1])
        if "또는" in text[a[2]:b[1]]:
            # ④ 제목이 "A또는B" 라고 말하면 어느 쪽인지 제목만으로 모른다 — 먼저 나온 A 를 주 분류로 두고 애매함으로 알린다.
            ranked = [a, b] + ranked[2:]
            tie = True
    return {"category": ranked[0][0], "tags": [m[0] for m in ranked[1:]], "tie": tie}


def category_of(title, categories):
    """주 분류만(예전 함수 이름과 뜻을 유지)."""
    return classify(title, categories)["category"]
