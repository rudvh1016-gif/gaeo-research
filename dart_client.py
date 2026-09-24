#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenDART API 클라이언트 — 키 보안 + Graceful Failure + 사용량 계측.

⚠️ 이 모듈은 research_v1.0 / research_v1.1의 판단에 절대 관여하지 않는다.
   지금은 '오늘부터 공시를 모아두는' 수집 전용이다.
   DART가 실제 분석 Feature로 쓰이는 최초 버전은 research_v2.0이다.

키 보안 (요구 14번)
- API Key는 환경변수(OPEN_DART_API_KEY)에서만 읽는다.
  소스코드·HTML·클라이언트 JS·공개 JSON·로그·저장소 어디에도 넣지 않는다.
- GitHub Actions에서는 Secrets로 주입한다.
- 예외 메시지·URL 로그에 키가 섞여 나가지 않도록 redact()로 항상 지운다.
  (DART는 키를 쿼리스트링으로 받기 때문에 URL이 그대로 로그에 찍히면 유출이다.)

Graceful Failure (요구 15번)
- 실패는 EVENT_DATA_ERROR로 기록하고 예외를 밖으로 던지지 않는다.
- Price / TARO / DIANA / FLOW / ROTATION 워크플로를 절대 중단시키지 않는다.

Rate / Efficiency (요구 16번)
- 호출 건수를 스스로 세서 리포트한다. 500종목을 반복 조회하는 구조가
  생겼는지 확인하기 위한 계측이다.
- 공식 호출 한도는 문서를 봐야 하는 값이라 상수로 박지 않는다.
"""
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

API_BASE = "https://opendart.fss.or.kr/api"
KEY_ENV = "OPEN_DART_API_KEY"

# 상태값
OK = "OK"
EVENT_DATA_ERROR = "EVENT_DATA_ERROR"
DART_KEY_MISSING = "DART_KEY_MISSING"
DART_UNREACHABLE = "DART_UNREACHABLE"

# DART가 돌려주는 status 코드 중 우리가 구분해서 다루는 것들
STATUS_OK = "000"
STATUS_NO_DATA = "013"          # 조회된 데이터 없음 — 오류가 아니다


def get_api_key():
    """환경변수에서만 읽는다. 없으면 None(파이프라인은 계속 돈다)."""
    key = os.environ.get(KEY_ENV) or ""
    return key.strip() or None


def redact(text, key=None):
    """로그·예외 메시지에서 API Key를 지운다.

    키를 모를 때도 crtfc_key= 뒤 값은 무조건 가린다.
    """
    s = str(text)
    key = key or get_api_key()
    if key:
        s = s.replace(key, "***REDACTED***")
        s = s.replace(urllib.parse.quote(key), "***REDACTED***")
    # crtfc_key=... 형태는 키를 몰라도 가린다
    out, i = [], 0
    needle = "crtfc_key="
    while True:
        j = s.find(needle, i)
        if j < 0:
            out.append(s[i:]); break
        out.append(s[i:j + len(needle)])
        k = j + len(needle)
        while k < len(s) and s[k] not in "&\"' \n\t":
            k += 1
        out.append("***REDACTED***")
        i = k
    return "".join(out)


class DartClient:
    """OpenDART 호출기. 사용량을 스스로 센다."""

    def __init__(self, api_key=None, timeout=20, min_interval=0.2):
        self._key = api_key or get_api_key()
        self.timeout = timeout
        # 예의상 최소 간격. 공식 한도는 문서 기준으로 확인할 값이라 여기 박지 않는다.
        self.min_interval = min_interval
        self._last_call = 0.0
        self.stats = {
            "requests_per_run": 0,
            "detail_requests": 0,
            "api_errors": 0,
            "no_data_responses": 0,
            "bytes_received": 0,
        }

    @property
    def has_key(self):
        return bool(self._key)

    def _throttle(self):
        gap = time.time() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.time()

    def call(self, endpoint, params=None, detail=False, raw=False):
        """DART API 한 번 호출. 실패해도 예외를 던지지 않는다.

        반환: {"status": OK|EVENT_DATA_ERROR|DART_KEY_MISSING|DART_UNREACHABLE,
                "data": <파싱된 응답 또는 bytes>, "error": "<키가 지워진 메시지>"}
        """
        if not self._key:
            return {"status": DART_KEY_MISSING, "data": None,
                    "error": f"{KEY_ENV} 환경변수가 없습니다. GitHub Secrets로 주입하세요."}
        query = dict(params or {})
        query["crtfc_key"] = self._key
        url = f"{API_BASE}/{endpoint}?" + urllib.parse.urlencode(query)
        self._throttle()
        self.stats["requests_per_run"] += 1
        if detail:
            self.stats["detail_requests"] += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gaeo-research/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
            self.stats["bytes_received"] += len(body)
        except urllib.error.HTTPError as ex:
            self.stats["api_errors"] += 1
            return {"status": EVENT_DATA_ERROR, "data": None,
                    "error": redact(f"HTTP {ex.code} {ex.reason}", self._key)}
        except Exception as ex:
            # 네트워크 차단·타임아웃·DNS 실패 등. 메시지에 URL이 섞일 수 있어 반드시 가린다.
            self.stats["api_errors"] += 1
            return {"status": DART_UNREACHABLE, "data": None,
                    "error": redact(f"{type(ex).__name__}: {ex}", self._key)}

        if raw:
            return {"status": OK, "data": body, "error": None}
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as ex:
            self.stats["api_errors"] += 1
            return {"status": EVENT_DATA_ERROR, "data": None,
                    "error": redact(f"응답 파싱 실패: {ex}", self._key)}

        status = str(parsed.get("status", ""))
        if status == STATUS_NO_DATA:
            self.stats["no_data_responses"] += 1
            return {"status": OK, "data": parsed, "error": None, "noData": True}
        if status and status != STATUS_OK:
            self.stats["api_errors"] += 1
            return {"status": EVENT_DATA_ERROR, "data": parsed,
                    "error": redact(f"DART status {status}: {parsed.get('message')}", self._key)}
        return {"status": OK, "data": parsed, "error": None}

    # ── 실제로 쓰는 엔드포인트 ──────────────────────────────────────────
    def list_filings(self, bgn_de=None, end_de=None, page_no=1, page_count=100,
                     corp_cls=None, last_reprt_at="N"):
        """최근 신규공시 목록.

        ⚠️ 500종목을 각각 부르지 않는다(요구 4번). 전체 신규공시를 한 번에 받아서
           우리 유니버스와 매칭하는 구조다. corp_code를 넘기지 않는 것이 핵심이다.
        """
        params = {"page_no": page_no, "page_count": page_count,
                  "last_reprt_at": last_reprt_at}
        if bgn_de:
            params["bgn_de"] = bgn_de
        if end_de:
            params["end_de"] = end_de
        if corp_cls:
            params["corp_cls"] = corp_cls
        return self.call("list.json", params)

    def list_issuer_filings(self, corp_code, bgn_de, end_de, page_no=1, page_count=100,
                            last_reprt_at="N", sort="date", sort_mth="asc"):
        """회사 한 곳의 기간 전체 공시 목록.

        ⚠️ list_filings(전체 신규공시)와 목적이 다르다. 전체 목록에 그 종목이 안 보였다는 것은
           '그 종목에 공시가 없었다'의 증거가 되지 못한다. 부재를 증명하려면 회사별로 조회하고
           페이지를 끝까지 받아 건수를 대조해야 한다. 그래서 corp_code 를 반드시 넘긴다.
           호출량이 늘어나므로 부르는 쪽이 예산을 관리한다.
        정렬을 고정하는 이유: 수집 도중 목록이 밀리면 페이지가 겹치거나 빠진다.
        """
        return self.call("list.json", {
            "corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de,
            "page_no": page_no, "page_count": page_count,
            "last_reprt_at": last_reprt_at, "sort": sort, "sort_mth": sort_mth})

    def corp_code_zip(self):
        """전체 기업 corp_code 매핑 원본(zip). Mapping Table 생성용."""
        return self.call("corpCode.xml", {}, raw=True)

    def financial_statement(self, corp_code, bsns_year, reprt_code, fs_div="CFS"):
        """단일회사 전체 재무제표. DIANA v2.0 준비용 수집."""
        return self.call("fnlttSinglAcntAll.json", {
            "corp_code": corp_code, "bsns_year": str(bsns_year),
            "reprt_code": reprt_code, "fs_div": fs_div}, detail=True)

    def efficiency_report(self, extra=None):
        """요구 16번 계측 리포트."""
        out = dict(self.stats)
        out.update(extra or {})
        return out
