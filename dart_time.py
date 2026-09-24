#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시각 처리 — Asia/Seoul 명시 + timezone-aware 비교.

두 가지 실수를 코드로 막는다.

1. Runner의 기본 timezone에 암묵적으로 기대는 것.
   GitHub Actions는 UTC로 돈다. datetime.date.today()를 쓰면 한국시간 오전 8시가
   전날로 잡힌다. DART 운영일 기준은 명시적으로 Asia/Seoul을 쓴다.

2. ISO 문자열을 그대로 비교해 시간순서를 판정하는 것.
   "2026-08-15T23:30:00+09:00"(= UTC 14:30)은
   "2026-08-15T15:00:00+00:00"(= UTC 15:00)보다 실제로는 이르지만,
   문자열로는 "23..." > "15..."이라 순서가 뒤집힌다.
   반드시 aware datetime으로 parse해서 UTC Instant로 비교한다.
"""
import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = datetime.timezone.utc


def now_kst():
    return datetime.datetime.now(KST)


def now_utc():
    return datetime.datetime.now(UTC)


def today_kst():
    """DART 운영일 기준 오늘(YYYY-MM-DD). Runner timezone과 무관하다."""
    return now_kst().date().isoformat()


def today_kst_compact():
    """DART API가 쓰는 YYYYMMDD."""
    return now_kst().strftime("%Y%m%d")


def iso_now():
    """기록용 timezone-aware ISO 문자열(UTC)."""
    return now_utc().isoformat()


def parse_instant(value):
    """ISO timestamp → timezone-aware UTC datetime. 실패하면 None.

    ⚠️ timezone이 없는(naive) 문자열은 받아들이지 않는다.
       어느 지역 시각인지 모르는 값을 임의로 UTC나 KST로 간주하면
       그 순간 조용한 오류가 된다.
    """
    if isinstance(value, datetime.datetime):
        return value.astimezone(UTC) if value.tzinfo else None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None          # naive는 사용하지 않는다
    return dt.astimezone(UTC)


def instant_le(a, b):
    """a <= b 를 실제 시각(UTC Instant)으로 비교. 하나라도 못 읽으면 False."""
    ia, ib = parse_instant(a), parse_instant(b)
    if ia is None or ib is None:
        return False
    return ia <= ib
