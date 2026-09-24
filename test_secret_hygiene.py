#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Secret 위생 검사 — Public Repo에 실제 Secret 값이 평문으로 들어가는 실수를 막는다.

원칙 (2026-08-16 보안 정리)
  · "환경변수 이름"과 "실제 Secret 값"을 구분한다.
    os.environ["TOSS_INVEST_CLIENT_SECRET"]  → 정상 (이름만 사용)
    TOSS_INVEST_CLIENT_SECRET = "실제값"      → 차단
  · 문서의 placeholder(your-api-key, xxxxxxxx, 예시 등)는 오탐하지 않는다.
  · 위반을 찾아도 값 자체는 절대 출력하지 않는다 — 파일·행 번호만 알려준다.

검사 대상
  1. 커밋되는 코드/설정(py·js·yml·json·html) 안의 실제 토큰 패턴
     (ghp_/gho_, xoxb-/xoxp-, AKIA, sk-…, PRIVATE KEY 블록)
  2. SECRET/KEY/TOKEN 이름에 16자 이상 실제값을 직접 대입하는 하드코딩
  3. research_archive/ JSON 안의 민감 키(계좌·토큰·secret 등) — 값 유무와 무관하게
     그런 필드 자체가 공개 아카이브에 있으면 실패 (Secret은 파일 저장 자체를 안 한다)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SCAN_EXT = {".py", ".js", ".yml", ".yaml", ".json", ".html"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".test-screenshots", ".claude"}
# 대용량 생성 데이터 파일은 토큰이 들어갈 경로가 없고(파이프라인이 시세·분석만 기록)
# 스캔 시간이 오래 걸려 제외한다. research_archive는 반드시 포함한다.
SKIP_FILES = {"rotation_snapshot.js", "auto_analysis.js", "analysis_archive.js",
              "history.js", "price_history.js", "index_history.js", "radar_series.js"}

# 1) 실제 토큰이 아니면 나올 수 없는 형태들
TOKEN_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),           # GitHub token
    re.compile(r"xox[bpoas]-[0-9A-Za-z-]{20,}"),          # Slack token
    re.compile(r"AKIA[0-9A-Z]{16}"),                       # AWS access key
    re.compile(r"sk-[A-Za-z0-9]{40,}"),                    # OpenAI형 secret
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
# 2) 이름 = "실제값" 하드코딩 (16자 이상 무작위형). 환경변수 참조·placeholder는 허용.
HARDCODE = re.compile(
    r"(CLIENT_SECRET|API_KEY|ACCESS_TOKEN|REFRESH_TOKEN|ARCHIVE_KEY)"
    r"['\"]?\s*[:=]\s*['\"]([A-Za-z0-9+/=_-]{16,})['\"]")
ALLOW_LINE = re.compile(
    r"environ|getenv|secrets\.|process\.env|\$\{\{|\bexport\b.*(xxxx|your-|예시|placeholder|example)"
    r"|xxxx|your-|예시|placeholder|example|MASKED")

# 3) 공개 아카이브에 있어선 안 되는 필드 이름(값 유무 무관)
FORBIDDEN_ARCHIVE_KEYS = re.compile(
    r"client_secret|access_token|refresh_token|authorization|account_number"
    r"|계좌번호|password|credential|cookie|session_id", re.I)


def iter_files():
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name in SKIP_FILES:
                continue
            if os.path.splitext(name)[1] in SCAN_EXT:
                yield os.path.join(root, name)


def main():
    problems = []
    for path in iter_files():
        rel = os.path.relpath(path, HERE)
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for pat in TOKEN_PATTERNS:
                if pat.search(line):
                    problems.append(f"{rel}:{i} 실제 토큰 형태 감지")
            m = HARDCODE.search(line)
            if m and not ALLOW_LINE.search(line):
                problems.append(f"{rel}:{i} {m.group(1)} 하드코딩 의심")
        if rel.replace(os.sep, "/").startswith("research_archive/") and rel.endswith(".json"):
            try:
                keys = " ".join(re.findall(r'"([^"]+)"\s*:', text))
                if FORBIDDEN_ARCHIVE_KEYS.search(keys):
                    problems.append(f"{rel} 공개 아카이브에 민감 필드 이름 존재")
            except Exception:
                pass

    if problems:
        print("test_secret_hygiene: 실패 — 값은 출력하지 않습니다. 위치만 표시:")
        for p in problems:
            print("  ✗", p)
        return 1
    print("test_secret_hygiene: 통과 (실제 토큰 패턴 0 · 하드코딩 0 · 공개 아카이브 민감 필드 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
