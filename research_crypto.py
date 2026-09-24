#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Research Raw Archive 암호화 — AES-256-GCM (authenticated encryption).

왜 필요한가
    이 저장소는 public이고 GitHub Pages가 저장소 루트를 그대로 서빙한다.
    실측(2026-08-15): https://gaeoteam.com/research_archive/dart/corp_map.json 이
    HTTP 200으로 내려받아졌다. robots.txt의 Disallow는 색인 요청일 뿐 접근 차단이 아니고,
    설령 Pages에서 가린다 해도 public repo의 raw URL로 여전히 받을 수 있다.
    따라서 **검증되지 않은 연구용 판단 원본을 평문으로 커밋하면 안 된다.**

원칙
    1. Key는 GitHub Actions Secret `RESEARCH_ARCHIVE_KEY`에서만 읽는다.
    2. ⚠️ OPEN_DART_API_KEY를 암호화 Key로 재사용하지 않는다. 용도가 다른 비밀은 섞지 않는다.
    3. Key 값을 코드·로그·커밋·리포트 어디에도 출력하지 않는다.
    4. **FAIL CLOSED** — Key가 없으면 평문으로 대신 저장하지 않는다. 저장 자체를 거부한다.
    5. AAD(추가 인증 데이터)에 날짜·종류를 넣어, 암호문을 다른 날짜로 바꿔치기하면 복호가 실패한다.

Key 형식
    base64(32바이트) 또는 64자 hex. 둘 다 허용한다.
"""
import base64
import binascii
import gzip
import json
import os

KEY_ENV = "RESEARCH_ARCHIVE_KEY"

MAGIC = b"GAEORA1\n"          # GAEO Research Archive v1
NONCE_BYTES = 12
KEY_BYTES = 32               # AES-256

# 상태값
OK = "OK"
KEY_MISSING = "RESEARCH_ARCHIVE_KEY_MISSING"
KEY_INVALID = "RESEARCH_ARCHIVE_KEY_INVALID"
CRYPTO_UNAVAILABLE = "CRYPTO_LIBRARY_UNAVAILABLE"
DECRYPT_FAILED = "DECRYPT_FAILED"


class ResearchArchiveKeyMissing(RuntimeError):
    """Key가 없을 때 평문 fallback을 막기 위해 던진다(FAIL CLOSED)."""


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except Exception:
        return None


def crypto_available():
    return _aesgcm() is not None


def _decode_key(raw):
    """base64(32B) 또는 hex(64자)를 32바이트 키로."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if len(raw) == KEY_BYTES * 2:
        try:
            return binascii.unhexlify(raw)
        except (binascii.Error, ValueError):
            pass
    try:
        key = base64.b64decode(raw, validate=True)
        if len(key) == KEY_BYTES:
            return key
    except (binascii.Error, ValueError):
        pass
    return None


def get_key():
    """환경변수에서만 읽는다. 없으면 None. ⚠️ 값을 절대 출력하지 않는다."""
    return _decode_key(os.environ.get(KEY_ENV))


def key_status():
    """진단용. 키 '값'이 아니라 상태만 돌려준다."""
    raw = (os.environ.get(KEY_ENV) or "").strip()
    if not raw:
        return KEY_MISSING
    if _decode_key(raw) is None:
        return KEY_INVALID
    if not crypto_available():
        return CRYPTO_UNAVAILABLE
    return OK


def generate_key_b64():
    """새 키를 만들어 base64로 돌려준다. 사용자가 Secret에 넣을 때만 쓴다.
    ⚠️ 이 값을 로그·파일에 남기지 말 것."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii")


def _aad(label):
    """암호문을 다른 파일 자리로 옮겨치기하는 것을 막는 바인딩."""
    return f"gaeo-research-archive|{label}".encode("utf-8")


def encrypt_bytes(plaintext, label):
    """평문 → 암호문. Key가 없으면 예외를 던진다(평문 저장 금지).

    출력 형식: MAGIC || nonce(12B) || ciphertext+tag
    """
    key = get_key()
    if key is None:
        raise ResearchArchiveKeyMissing(
            f"{KEY_ENV}가 없거나 형식이 잘못됐습니다. "
            f"평문으로 저장하지 않고 중단합니다(FAIL CLOSED).")
    AESGCM = _aesgcm()
    if AESGCM is None:
        raise ResearchArchiveKeyMissing(
            "cryptography 라이브러리를 쓸 수 없습니다. 평문 저장 대신 중단합니다.")
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext, _aad(label))
    return MAGIC + nonce + ct


def decrypt_bytes(blob, label):
    """암호문 → 평문. 인증에 실패하면 예외가 난다(변조 탐지)."""
    key = get_key()
    if key is None:
        raise ResearchArchiveKeyMissing(f"{KEY_ENV}가 없어 복호할 수 없습니다.")
    AESGCM = _aesgcm()
    if AESGCM is None:
        raise ResearchArchiveKeyMissing("cryptography 라이브러리를 쓸 수 없습니다.")
    if not blob.startswith(MAGIC):
        raise ValueError("GAEO Research Archive 암호문 형식이 아닙니다.")
    body = blob[len(MAGIC):]
    nonce, ct = body[:NONCE_BYTES], body[NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, ct, _aad(label))


def is_encrypted_file(path):
    try:
        with open(path, "rb") as f:
            return f.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def write_encrypted(path, text, label, gzip_first=False):
    """텍스트를 암호화해 저장한다. Key가 없으면 아무것도 쓰지 않는다.

    gzip_first=True면 압축 후 암호화한다. 암호문은 델타 압축이 안 되기 때문에
    같은 파일을 자주 커밋하면 매번 전체 크기가 저장소에 통째로 쌓인다.
    읽는 쪽(research_store._read_text)이 gzip 매직바이트로 자동 판별하므로
    파일 이름은 그대로 두고, 예전에 저장된 비압축 파일도 계속 읽힌다.
    """
    payload = text.encode("utf-8")
    if gzip_first:
        payload = gzip.compress(payload, compresslevel=9)
    blob = encrypt_bytes(payload, label)   # 여기서 먼저 실패해야 한다
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return len(blob)


def read_encrypted(path, label):
    with open(path, "rb") as f:
        return decrypt_bytes(f.read(), label).decode("utf-8")


def redact(text):
    """혹시라도 Key가 섞인 문자열을 로그로 내보내지 않도록 지운다."""
    s = str(text)
    raw = (os.environ.get(KEY_ENV) or "").strip()
    if raw:
        s = s.replace(raw, "***REDACTED***")
    return s
