#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GAEO Research Archive Store — 장기 Research 데이터 저장 인프라.

저장 backend와 Research 계산 코드를 분리하는 추상화 계층이다.
나중에 저장소가 바뀌어도 Research Engine 코드를 갈아엎지 않기 위해서다.

계층
    HOT   research_archive/live/YYYY/MM/DD.jsonl        오늘·최근. 압축 안 함
    WARM  research_archive/live/YYYY/MM/DD.jsonl.gz     닫힌 날. gzip
    COLD  research_archive/archive/YYYY/MM/...          월간 묶음 + manifest

원칙
- APPEND-ONLY. 닫힌 날짜(CLOSED) 기록은 어떤 이유로도 수정하지 않는다.
- 압축은 저장형태만 바꾼다. 연구 데이터 내용은 바꾸지 않는다.
- 압축·묶음이 검증에 성공하기 전에는 원본을 절대 지우지 않는다.
- Raw Prediction이 Source of Truth다. Scorecard는 언제든 다시 만들 수 있다.
- 보관기간을 임의로(7일·30일) 정하지 않는다. 실측 후 결정한다.

⚠️ 이 디렉터리는 사이트가 읽지 않는다. index.html의 GaeoFeatures 목록에 없고
   robots.txt에서도 막는다. 사용자가 웹에서 내려받는 자료가 아니다.
"""
import gzip
import hashlib
import io
import json
import os
import datetime

import research_crypto

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_ROOT = os.path.join(HERE, "research_archive")

SCHEMA_VERSION = "research_archive_v1"
ARCHIVE_VERSION = "1.0"

# ⚠️ 레코드 종류마다 필수 필드가 다르다. Research Prediction 검사기를 그대로
#    DART Raw Event에 쓰면 modelVersion이 없다고 정상 Event가 손상으로 잡힌다.
#    DART 기록에 억지로 modelVersion을 넣어 검사를 통과시키지 않는다.
RECORD_RESEARCH = "research_prediction"
RECORD_DART = "dart_event"

RECORD_SPECS = {
    "production_decision": {
        "versionBlocks": (), "versionField": None,
        "timestampField": "decisionAt", "keyFields": ("recordId",),
        "requiredFields": ("recordId", "code", "source", "decisionAt", "scoringVersion"),
    },
    RECORD_RESEARCH: {
        "versionBlocks": ("research", "researchV11"),
        "versionField": "modelVersion",
        "timestampField": "createdAt",
        "keyFields": ("code", "date"),
        "requiredFields": (),
    },
    RECORD_DART: {
        # DART Raw는 모델 개념이 없다. 원본이 어디서 언제 왔는지가 핵심이다.
        "versionBlocks": (),
        "versionField": None,
        "timestampField": "detected_at",
        "keyFields": ("rcept_no",),
        "requiredFields": ("rcept_no", "corp_code", "ticker",
                           "detected_at", "fetched_at", "source", "sourceMode"),
    },
}

# 무결성 상태값
OK = "OK"
ARCHIVE_INTEGRITY_ERROR = "ARCHIVE_INTEGRITY_ERROR"
STORAGE_MIGRATION_RECOMMENDED = "STORAGE_MIGRATION_RECOMMENDED"


# ── 공통 유틸 ────────────────────────────────────────────────────────────────
def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_text(path, label=None):
    """.jsonl / .jsonl.gz / .*.enc 어느 형태든 평문 텍스트로 읽는다."""
    if path.endswith(".enc"):
        blob = research_crypto.decrypt_bytes(open(path, "rb").read(), label or "")
        # 이름이 .gz.enc면 무조건 gzip이고, ACTIVE(.jsonl.enc)도 2026-08-21부터
        # 압축해서 저장한다(암호문은 git 델타 압축이 안 돼 매 커밋마다 4MB가 통째로
        # 쌓였다). 그 전에 저장된 비압축 파일도 계속 읽혀야 하므로 매직바이트로 함께 판별한다.
        if path.endswith(".gz.enc") or blob[:2] == b"\x1f\x8b":
            blob = gzip.decompress(blob)
        return blob.decode("utf-8")
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def _iter_jsonl(path, label=None):
    """한 줄씩 dict로 돌려준다. 암호문이면 복호 후 파싱한다."""
    for lineno, line in enumerate(_read_text(path, label).splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        yield lineno, json.loads(line)


def _stat_records(path, record_type=RECORD_RESEARCH, label=None):
    """레코드 수 + 버전 집합 + 시각 범위 + 중복 키 + 필수필드 누락을 센다.

    record_type에 따라 '무엇이 필수인가'가 달라진다.
    Research Prediction에는 modelVersion이, DART Raw에는 rcept_no·detected_at이
    필수다. 서로의 잣대를 들이대지 않는다.
    """
    spec = RECORD_SPECS.get(record_type) or RECORD_SPECS[RECORD_RESEARCH]
    count = 0
    versions, features, labels = set(), set(), set()
    first_ts = last_ts = None
    keys = set()
    dups = []
    missing_version, missing_ts = 0, 0
    missing_required = {}
    for _lineno, rec in _iter_jsonl(path, label):
        count += 1
        key = tuple(str(rec.get(k)) for k in spec["keyFields"])
        if key in keys:
            dups.append(key)
        keys.add(key)

        for field in spec["requiredFields"]:
            if not rec.get(field):
                missing_required[field] = missing_required.get(field, 0) + 1

        if spec["versionBlocks"]:
            found_version = False
            found_ts = False
            for block in spec["versionBlocks"]:
                b = rec.get(block)
                if not isinstance(b, dict):
                    continue
                if b.get("modelVersion"):
                    versions.add(b["modelVersion"]); found_version = True
                if b.get("featureVersion"):
                    features.add(b["featureVersion"])
                if b.get("labelVersion"):
                    labels.add(b["labelVersion"])
                ts = b.get(spec["timestampField"])
                if ts:
                    found_ts = True
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts
            if not found_version:
                missing_version += 1
            if not found_ts:
                missing_ts += 1
        else:
            # DART Raw: 최상위에 시각이 있다. 모델 버전은 아예 개념이 없다.
            ts = rec.get(spec["timestampField"])
            if ts:
                if first_ts is None or str(ts) < str(first_ts):
                    first_ts = ts
                if last_ts is None or str(ts) > str(last_ts):
                    last_ts = ts
            else:
                missing_ts += 1
    return {
        "recordType": record_type,
        "recordCount": count,
        "modelVersions": sorted(versions),
        "featureVersions": sorted(features),
        "labelVersions": sorted(labels),
        "firstPredictionTimestamp": first_ts,
        "lastPredictionTimestamp": last_ts,
        "duplicateKeys": sorted(set(dups)),
        "missingModelVersion": missing_version,
        "missingPredictionTimestamp": missing_ts,
        "missingRequiredFields": missing_required,
    }


def _day_from_path(path):
    """live/YYYY/MM/DD.jsonl[.gz][.enc] → YYYY-MM-DD."""
    parts = os.path.normpath(path).split(os.sep)
    name = parts[-1].split(".")[0]
    if len(parts) >= 3 and len(name) == 2:
        return f"{parts[-3]}-{parts[-2]}-{name}"
    return name


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)


# ── ResearchArchiveStore ─────────────────────────────────────────────────────
class ResearchArchiveStore:
    """Research Prediction의 저장·압축·묶음·검증을 담당한다.

    Research 계산 코드는 이 클래스의 메서드만 부른다. 파일 경로 규칙이나
    압축 방식이 바뀌어도 호출부는 그대로 둘 수 있다.
    """

    def __init__(self, root=ARCHIVE_ROOT, record_type=RECORD_RESEARCH, encrypt=True):
        # ⚠️ 기본값이 encrypt=True다. public repo에 평문 Research Raw를 남기지 않기 위해서다.
        #    Key가 없으면 평문으로 대체 저장하지 않고 쓰기 자체를 거부한다(FAIL CLOSED).
        self.root = root
        self.encrypt = encrypt
        self.record_type = record_type
        self.spec = RECORD_SPECS.get(record_type) or RECORD_SPECS[RECORD_RESEARCH]
        self.live = os.path.join(root, "live")
        self.archive = os.path.join(root, "archive")

    def _key(self, rec):
        """이 스키마에서 레코드를 구분하는 키."""
        return tuple(str(rec.get(k)) for k in self.spec["keyFields"])

    def _stats(self, path, day=None):
        label = self._label(day) if day else self._label(_day_from_path(path))
        return _stat_records(path, self.record_type, label)

    # ── 경로 ────────────────────────────────────────────────────────────
    def segment_path(self, day, compressed=False, encrypted=None):
        """encrypted=None이면 이 Store의 기본 정책(self.encrypt)을 따른다."""
        y, m, d = str(day)[:4], str(day)[5:7], str(day)[8:10]
        enc = self.encrypt if encrypted is None else encrypted
        name = f"{d}.jsonl" + (".gz" if compressed else "") + (".enc" if enc else "")
        return os.path.join(self.live, y, m, name)

    def existing_segment(self, day):
        """실제로 있는 파일 경로. 암호문·평문·압축 여부를 모두 살핀다."""
        for enc in (True, False):
            for comp in (False, True):
                path = self.segment_path(day, comp, enc)
                if os.path.exists(path):
                    return path
        return None

    def _label(self, day):
        """AAD 바인딩. 암호문을 다른 날짜 자리로 옮기면 복호가 실패한다."""
        return f"{self.record_type}|{day}"

    def manifest_path(self, day):
        y, m, d = str(day)[:4], str(day)[5:7], str(day)[8:10]
        return os.path.join(self.live, y, m, f"{d}.manifest.json")

    def list_days(self):
        """저장된 날짜를 오름차순으로."""
        days = []
        if not os.path.isdir(self.live):
            return days
        for y in sorted(os.listdir(self.live)):
            ydir = os.path.join(self.live, y)
            if not os.path.isdir(ydir):
                continue
            for m in sorted(os.listdir(ydir)):
                mdir = os.path.join(ydir, m)
                if not os.path.isdir(mdir):
                    continue
                for name in sorted(os.listdir(mdir)):
                    if ".jsonl" in name and not name.endswith(".tmp"):
                        d = name.split(".")[0]
                        if len(d) == 2 and d.isdigit():
                            days.append(f"{y}-{m}-{d}")
        return sorted(set(days))

    # ── 상태 ────────────────────────────────────────────────────────────
    def segment_state(self, day, today=None):
        """ACTIVE(오늘, 계속 쓰는 중) / CLOSED(닫힘) / COMPRESSED / MISSING."""
        today = today or datetime.date.today().isoformat()
        for enc in (True, False):
            if os.path.exists(self.segment_path(day, True, enc)):
                return "COMPRESSED"
        for enc in (True, False):
            if os.path.exists(self.segment_path(day, False, enc)):
                return "ACTIVE" if str(day) >= str(today) else "CLOSED"
        return "MISSING"

    # ── 쓰기 ────────────────────────────────────────────────────────────
    def read_day(self, day):
        """그 날 기록을 리스트로. 없으면 빈 리스트."""
        path = self.existing_segment(day)
        if not path:
            return []
        return [rec for _n, rec in _iter_jsonl(path, self._label(day))]

    def append_predictions(self, day, records, today=None):
        """오늘(ACTIVE) Segment에만 쓴다.

        닫힌 날짜에는 절대 쓰지 않는다. 같은 (code, date) 키가 이미 있으면
        그 날이 ACTIVE일 때만 최신 스냅샷으로 교체한다(장중 재실행).
        반환: (added, replaced)
        """
        today = today or datetime.date.today().isoformat()
        state = self.segment_state(day, today)
        if state in ("CLOSED", "COMPRESSED"):
            raise PermissionError(
                f"{day} Segment는 {state} 상태다. 닫힌 날짜에는 기록을 쓸 수 없다.")

        existing = self.read_day(day)
        index = {self._key(r): i for i, r in enumerate(existing)}
        added = replaced = 0
        for rec in records:
            key = self._key(rec)
            if key in index:
                existing[index[key]] = rec
                replaced += 1
            else:
                index[key] = len(existing)
                existing.append(rec)
                added += 1

        body = "".join(
            json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"
            for rec in sorted(existing, key=self._key))
        path = self.segment_path(day, False)
        if self.encrypt:
            # ⚠️ FAIL CLOSED — Key가 없으면 여기서 예외가 나고 아무 파일도 안 생긴다.
            #    평문으로 대신 저장하는 fallback은 존재하지 않는다.
            # 💾 gzip 후 암호화한다. 이 파일은 하루 동안 사이클마다 통째로 다시 쓰이는데,
            #    암호문은 git 델타 압축이 안 돼서 매 커밋마다 전체 크기가 저장소에 쌓인다.
            #    2026-08-21 실측: 하루치 원본 4.16MB × 23커밋 = 저장소에 90MB.
            #    압축하면 같은 내용이 64KB 수준이라 그 비용이 60분의 1로 준다.
            #    파일 이름은 그대로 두고(ACTIVE/CLOSED 상태 판별이 이름을 쓴다),
            #    읽는 쪽이 gzip 매직바이트로 자동 판별한다.
            research_crypto.write_encrypted(path, body, self._label(day), gzip_first=True)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        return added, replaced

    # ── 닫기 · 압축 ─────────────────────────────────────────────────────
    def close_daily_segment(self, day, today=None):
        """하루가 끝난 Segment의 manifest를 만들어 CLOSED로 표시한다.

        오늘 파일(ACTIVE)은 닫지 않는다. 아직 쓰고 있기 때문이다.
        """
        today = today or datetime.date.today().isoformat()
        state = self.segment_state(day, today)
        if state == "MISSING":
            return None
        if state == "ACTIVE":
            return None      # 아직 쓰는 중 — 닫지 않는다
        path = self.existing_segment(day)
        stats = self._stats(path, day)
        manifest = {
            "archiveVersion": ARCHIVE_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "period": {"type": "day", "id": day},
            "recordType": self.record_type,
            "compression": "gzip" if ".gz" in os.path.basename(path) else "none",
            "sourceFiles": [os.path.relpath(path, self.root)],
            "sha256": {os.path.basename(path): _sha256_file(path)},
            "status": "CLOSED",
        }
        manifest.update({k: stats[k] for k in (
            "recordCount", "modelVersions", "featureVersions", "labelVersions",
            "firstPredictionTimestamp", "lastPredictionTimestamp")})
        _write_json(self.manifest_path(day), manifest)
        return manifest

    def compress_segment(self, day, today=None, remove_source=True):
        """닫힌 Segment를 gzip으로 만든다.

        절차(요구된 순서 그대로):
          1) 원본 종료 확인  2) record count  3) SHA256  4) gzip 생성
          5) decompress test 6) 압축 전/후 count 비교 7) manifest 검증
          8) 검증 성공 후에만 원본 정리

        암호화 모드에서는 gzip → 암호화 순서로 만든다(.jsonl.gz.enc).
        압축이 먼저여야 압축률이 나온다. 암호문은 압축되지 않는다.

        검증이 하나라도 실패하면 만든 파일을 지우고 원본은 그대로 둔다.
        """
        today = today or datetime.date.today().isoformat()
        state = self.segment_state(day, today)
        if state == "COMPRESSED":
            return {"status": "ALREADY_COMPRESSED", "day": day}
        if state != "CLOSED":
            return {"status": f"SKIPPED_{state}", "day": day}

        src = self.existing_segment(day)
        label = self._label(day)
        before = self._stats(src, day)
        plain = _read_text(src, label).encode("utf-8")
        src_hash = hashlib.sha256(plain).hexdigest()
        raw_bytes = len(plain)

        dst = self.segment_path(day, True)
        tmp = dst + ".tmp"
        try:
            gz_bytes_data = gzip.compress(plain, compresslevel=9)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if self.encrypt:
                # gzip 바이너리를 그대로 암호화한다(텍스트 변환 없이).
                blob = research_crypto.encrypt_bytes(gz_bytes_data, label)
                with open(tmp, "wb") as f:
                    f.write(blob); f.flush(); os.fsync(f.fileno())
            else:
                with open(tmp, "wb") as f:
                    f.write(gz_bytes_data); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, dst)

            # 5·6) 실제로 풀어서 다시 세어 본다
            after = self._stats(dst, day)
            if after["recordCount"] != before["recordCount"]:
                raise ValueError(
                    f"압축 전후 레코드 수 불일치 {before['recordCount']} != {after['recordCount']}")
            # 7) 내용 자체가 동일한지(바이트 단위)
            if hashlib.sha256(_read_text(dst, label).encode("utf-8")).hexdigest() != src_hash:
                raise ValueError("압축 해제 결과가 원본과 다르다")
        except Exception as ex:
            for pth in (tmp, dst):
                if os.path.exists(pth):
                    os.remove(pth)
            return {"status": ARCHIVE_INTEGRITY_ERROR, "day": day, "error": str(ex)[:200]}

        gz_bytes = os.path.getsize(dst)
        manifest = {
            "archiveVersion": ARCHIVE_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "period": {"type": "day", "id": day},
            "recordType": self.record_type,
            "compression": "gzip",
            "encryption": "AES-256-GCM" if self.encrypt else "none",
            "sourceFiles": [os.path.relpath(dst, self.root)],
            "sha256": {os.path.basename(dst): _sha256_file(dst)},
            "plaintextSha256": src_hash,
            "rawBytes": raw_bytes,
            "compressedBytes": gz_bytes,
            "compressionRatio": round(gz_bytes / raw_bytes, 4) if raw_bytes else None,
            "status": "CLOSED_COMPRESSED",
        }
        manifest.update({k: before[k] for k in (
            "recordCount", "modelVersions", "featureVersions", "labelVersions",
            "firstPredictionTimestamp", "lastPredictionTimestamp")})
        _write_json(self.manifest_path(day), manifest)

        # 8) 여기까지 전부 통과했을 때만 원본을 정리한다
        if remove_source and os.path.abspath(src) != os.path.abspath(dst):
            os.remove(src)
        return {"status": OK, "day": day, "rawBytes": raw_bytes,
                "compressedBytes": gz_bytes,
                "compressionRatio": manifest["compressionRatio"],
                "recordCount": before["recordCount"]}

    # ── 검증 · 복원 ─────────────────────────────────────────────────────
    def verify_archive(self, day):
        """manifest와 실제 파일이 맞는지 검사한다. Restore Test의 핵심."""
        mpath = self.manifest_path(day)
        if not os.path.exists(mpath):
            return {"status": ARCHIVE_INTEGRITY_ERROR, "day": day,
                    "errors": ["manifest 없음"]}
        manifest = json.load(open(mpath, encoding="utf-8"))
        path = self.existing_segment(day)
        errors = []
        if not path:
            return {"status": ARCHIVE_INTEGRITY_ERROR, "day": day,
                    "errors": ["Segment 파일 없음"]}
        # gzip decompress + JSONL parse. 손상 형태가 다양하므로(zlib.error,
        # EOFError, UnicodeDecodeError, BadGzipFile …) 여기서는 넓게 잡는다.
        # 무결성 검사기가 예외로 죽어버리면 검사 자체가 무의미하다.
        try:
            stats = self._stats(path, day)
        except Exception as ex:
            return {"status": ARCHIVE_INTEGRITY_ERROR, "day": day,
                    "errors": [f"복원 실패: {str(ex)[:120]}"]}

        if stats["recordCount"] != manifest.get("recordCount"):
            errors.append(f"레코드 수 불일치 {stats['recordCount']} != {manifest.get('recordCount')}")
        expected = (manifest.get("sha256") or {}).get(os.path.basename(path))
        if expected and expected != _sha256_file(path):
            errors.append("SHA256 불일치")
        if stats["duplicateKeys"]:
            errors.append(f"중복 키 {len(stats['duplicateKeys'])}건")
        if self.spec["versionBlocks"] and stats["missingModelVersion"]:
            errors.append(f"modelVersion 누락 {stats['missingModelVersion']}건")
        if stats["missingPredictionTimestamp"]:
            errors.append(f"{self.spec['timestampField']} 누락 "
                          f"{stats['missingPredictionTimestamp']}건")
        for field, n in (stats.get("missingRequiredFields") or {}).items():
            errors.append(f"필수 필드 {field} 누락 {n}건")
        return {"status": OK if not errors else ARCHIVE_INTEGRITY_ERROR,
                "day": day, "errors": errors, "recordCount": stats["recordCount"],
                "modelVersions": stats["modelVersions"]}

    def restore_test(self, day):
        """압축 Archive → 복원 → parse → count/version/timestamp 확인."""
        res = self.verify_archive(day)
        path = self.existing_segment(day)
        res["restoredFrom"] = os.path.relpath(path, self.root) if path else None
        res["compressed"] = bool(path and ".gz" in os.path.basename(path))
        return res

    # ── Weekly / Monthly Rollup ─────────────────────────────────────────
    def rollup_week(self, week_id, days):
        """주간 Manifest. 개별 Prediction 값을 다시 계산하지 않는다."""
        included, hashes, counts = [], {}, 0
        versions, first_ts, last_ts = set(), None, None
        for day in days:
            path = self.existing_segment(day)
            if not path:
                continue
            stats = self._stats(path, day)
            included.append(day)
            hashes[os.path.relpath(path, self.root)] = _sha256_file(path)
            counts += stats["recordCount"]
            versions |= set(stats["modelVersions"])
            if stats["firstPredictionTimestamp"] and (
                    first_ts is None or stats["firstPredictionTimestamp"] < first_ts):
                first_ts = stats["firstPredictionTimestamp"]
            if stats["lastPredictionTimestamp"] and (
                    last_ts is None or stats["lastPredictionTimestamp"] > last_ts):
                last_ts = stats["lastPredictionTimestamp"]
        if not included:
            return None
        manifest = {
            "archiveVersion": ARCHIVE_VERSION, "schemaVersion": SCHEMA_VERSION,
            "period": {"type": "week", "id": week_id},
            "weekId": week_id, "includedDays": included,
            "recordCount": counts, "modelVersions": sorted(versions),
            "firstPredictionTimestamp": first_ts, "lastPredictionTimestamp": last_ts,
            "fileHashes": hashes, "compression": "mixed",
            "archiveCreatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        year = week_id.split("-")[0]
        _write_json(os.path.join(self.archive, year, week_id, "manifest.json"), manifest)
        return manifest

    def rollup_month(self, month_id, remove_source=False):
        """월간 장기보관 묶음. 원본 hash·record count 검증 후에만 만든다.

        remove_source=True여도 묶음 검증이 통과하기 전에는 아무것도 지우지 않는다.
        """
        days = [d for d in self.list_days() if d[:7] == month_id]
        if not days:
            return None
        # 원본 검증 먼저
        problems = []
        total = 0
        versions, features, labels = set(), set(), set()
        first_ts = last_ts = None
        sources, hashes = [], {}
        for day in days:
            v = self.verify_archive(day)
            if v["status"] != OK:
                problems.append({"day": day, "errors": v.get("errors")})
                continue
            path = self.existing_segment(day)
            stats = self._stats(path, day)
            total += stats["recordCount"]
            versions |= set(stats["modelVersions"])
            features |= set(stats["featureVersions"])
            labels |= set(stats["labelVersions"])
            if stats["firstPredictionTimestamp"] and (
                    first_ts is None or stats["firstPredictionTimestamp"] < first_ts):
                first_ts = stats["firstPredictionTimestamp"]
            if stats["lastPredictionTimestamp"] and (
                    last_ts is None or stats["lastPredictionTimestamp"] > last_ts):
                last_ts = stats["lastPredictionTimestamp"]
            rel = os.path.relpath(path, self.root)
            sources.append(rel)
            hashes[rel] = _sha256_file(path)
        if problems:
            return {"status": ARCHIVE_INTEGRITY_ERROR, "month": month_id,
                    "problems": problems}

        year = month_id[:4]
        outdir = os.path.join(self.archive, year, month_id[5:7])
        os.makedirs(outdir, exist_ok=True)
        month_label = f"{self.record_type}|month|{month_id}"
        gz_path = os.path.join(outdir, f"research-{month_id}.jsonl.gz"
                               + (".enc" if self.encrypt else ""))
        tmp = gz_path + ".tmp"
        try:
            lines = []
            for day in days:
                for _n, rec in _iter_jsonl(self.existing_segment(day), self._label(day)):
                    lines.append(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
            payload = gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), compresslevel=9)
            # ⚠️ 월간 묶음도 평문으로 두지 않는다. public repo에 들어가는 파일이다.
            blob = research_crypto.encrypt_bytes(payload, month_label) if self.encrypt else payload
            with open(tmp, "wb") as f:
                f.write(blob); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, gz_path)
            merged = _stat_records(gz_path, self.record_type, month_label)
            if merged["recordCount"] != total:
                raise ValueError(f"묶음 레코드 수 불일치 {merged['recordCount']} != {total}")
        except Exception as ex:
            for pth in (tmp, gz_path):
                if os.path.exists(pth):
                    os.remove(pth)
            return {"status": ARCHIVE_INTEGRITY_ERROR, "month": month_id,
                    "error": str(ex)[:200]}

        manifest = {
            "archiveVersion": ARCHIVE_VERSION, "schemaVersion": SCHEMA_VERSION,
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "archiveCreatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "period": {"type": "month", "id": month_id},
            "includedDays": days, "recordCount": total,
            "modelVersions": sorted(versions), "featureVersions": sorted(features),
            "labelVersions": sorted(labels),
            "firstPredictionTimestamp": first_ts, "lastPredictionTimestamp": last_ts,
            "compression": "gzip",
            "encryption": "AES-256-GCM" if self.encrypt else "none",
            "sourceFiles": sources, "fileHashes": hashes,
            "sha256": {os.path.basename(gz_path): _sha256_file(gz_path)},
            "status": "MONTHLY_ARCHIVED",
        }
        _write_json(os.path.join(outdir, "manifest.json"), manifest)

        # 묶음이 정상이라는 것이 확인된 뒤에만 원본 정리를 허용한다.
        removed = []
        if remove_source:
            for day in days:
                path = self.existing_segment(day)
                if path:
                    os.remove(path); removed.append(day)
        manifest["removedSourceDays"] = removed
        return {"status": OK, "month": month_id, "recordCount": total,
                "compressedBytes": os.path.getsize(gz_path),
                "removedSourceDays": removed, "manifest": manifest}

    # ── 저장량 모니터 ───────────────────────────────────────────────────
    def storage_report(self, today=None):
        """하루 증가량과 30/90/365일 예상치. 임의의 한계를 하드코딩하지 않는다."""
        today = today or datetime.date.today().isoformat()
        days = self.list_days()
        raw_today = comp_today = new_today = 0
        total_bytes = 0
        per_day = []
        for day in days:
            path = self.existing_segment(day)
            if not path:
                continue
            size = os.path.getsize(path)
            total_bytes += size
            compressed = ".gz" in os.path.basename(path)   # .gz / .gz.enc 둘 다
            stats = self._stats(path, day)
            per_day.append({"day": day, "bytes": size, "records": stats["recordCount"],
                            "compressed": compressed})
            if day == today:
                new_today = stats["recordCount"]
                if compressed:
                    comp_today = size
                else:
                    raw_today = size
        for root, _dirs, files in os.walk(self.archive):
            for name in files:
                total_bytes += os.path.getsize(os.path.join(root, name))

        # 압축비는 실제로 압축된 날들에서만 잰다(없으면 None).
        ratios = [m["compressionRatio"] for m in self._manifests()
                  if m.get("compressionRatio")]
        ratio = round(sum(ratios) / len(ratios), 4) if ratios else None

        # 예상치는 '최종 보관 형태(압축 후)' 기준으로 잡는다.
        # ⚠️ 이미 압축된 날의 크기에 압축비를 또 곱하면 안 된다(이중 계산).
        #    아직 압축 안 된 날만 압축비를 적용해 최종 크기를 추정한다.
        final_sizes = []
        for d in per_day:
            if d["compressed"]:
                final_sizes.append(d["bytes"])
            elif ratio:
                final_sizes.append(d["bytes"] * ratio)
            else:
                final_sizes.append(d["bytes"])
        avg = (sum(d["bytes"] for d in per_day) / len(per_day)) if per_day else 0
        projected_daily = (sum(final_sizes) / len(final_sizes)) if final_sizes else 0
        report = {
            "asof": today,
            "observedDays": len(per_day),
            "newRecordsToday": new_today,
            "rawBytesToday": raw_today,
            "compressedBytesToday": comp_today,
            "compressionRatio": ratio,
            "totalArchiveBytes": total_bytes,
            "dailyGrowthAverageBytes": round(avg),          # 지금 디스크에 있는 형태 기준
            "projectedDailyBytes": round(projected_daily),  # 압축까지 끝난 최종 형태 기준
            "estimated30dBytes": round(projected_daily * 30),
            "estimated90dBytes": round(projected_daily * 90),
            "estimated365dBytes": round(projected_daily * 365),
            "status": OK,
            "note": "보관기간·용량 한계는 실측값을 보고 정한다. 임의 상수를 두지 않는다.",
        }
        return report

    def _manifests(self):
        out = []
        for root, _dirs, files in os.walk(self.live):
            for name in files:
                if name.endswith(".manifest.json"):
                    try:
                        out.append(json.load(open(os.path.join(root, name), encoding="utf-8")))
                    except (OSError, json.JSONDecodeError):
                        continue
        return out

    # ── 유지보수 한 번에 ────────────────────────────────────────────────
    def maintain(self, today=None, compress=True):
        """닫힌 날 닫기 → 압축 → 검증. 오늘 파일은 절대 건드리지 않는다."""
        today = today or datetime.date.today().isoformat()
        actions = []
        for day in self.list_days():
            state = self.segment_state(day, today)
            if state == "ACTIVE":
                continue                        # 아직 쓰는 중
            if state == "CLOSED":
                self.close_daily_segment(day, today)
                if compress:
                    actions.append(self.compress_segment(day, today))
                else:
                    actions.append({"status": "CLOSED_NOT_COMPRESSED", "day": day})
            elif state == "COMPRESSED" and not os.path.exists(self.manifest_path(day)):
                self.close_daily_segment(day, today)
                actions.append({"status": "MANIFEST_REBUILT", "day": day})
        return actions
