#!/usr/bin/env python3
"""종목 공부 글 세척기 (이전 1회용 · LLM 0 · 네트워크 0).

옛 저장소 stock_study.js 를 읽어, 권리가 불분명한 수치 문장(컨센서스·목표주가·투자의견·수급·주가배수)만 빼고
content/stock_study.js 로 쓴다. 문장 단위로만 뺀다 — 글을 새로 쓰지 않는다. 결과 분류:
  SAFE_AS_IS            뺀 문장 0
  SANITIZE_AND_RESTORE  뺀 문장이 있고 본문의 60% 이상이 남음
  PRIVATE_ONLY          남은 본문이 60% 미만 → 공개하지 않는다(옛 저장소에만 남는다)
사용: python3 tools/migration/sanitize_study.py <옛 stock_study.js> <출력 js> <보고 json>
"""
import json, re, sys

RISK = re.compile(r"컨센서스|목표\s*주?가|상승\s*여력|투자\s*의견|순매수|순매도|보유\s*비중|지분율|보유율|"
                  r"PER\b|PBR\b|PER\s|PBR\s|주가수익비율|주가순자산비율|[가-힣A-Z]+증권\s*[가-힣]*\s*연구원|연구원은|리포트에서|"
                  r"data\.js|데이터닷|(종가|주가|장중|최고가|최저가|고점|저점)[^.]{0,40}\d{1,3}(,\d{3})+\s*원")
# 옛 사이트 시세 파일(네이버 유래)·네이버 금융 페이지를 가리키는 출처 링크는 옮기지 않는다.
BAD_SOURCE = re.compile(r"data\.js|gaeo-analyst-team|finance\.naver|stock\.naver|m\.stock\.naver", re.I)
SENT = re.compile(r"(?<=[.!?요다])\s+(?=\S)")


def load(path, name):
    import subprocess
    js = (f"const fs=require('fs');process.stdout.write(JSON.stringify("
          f"new Function(fs.readFileSync({json.dumps(path)},'utf8')+';return {name}')()))")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def clean_text(text):
    removed, out_lines = [], []
    for line in str(text or "").split("\n"):
        stripped = line.strip()
        if not stripped:
            out_lines.append(line); continue
        bullet = re.match(r"^(\s*[-·*]\s+|\s*\d+\.\s+|\s*\|)", line)
        if bullet or stripped.startswith("#"):
            if RISK.search(stripped) and not stripped.startswith("#"):
                removed.append(stripped); continue
            out_lines.append(line); continue
        parts = SENT.split(line)
        keep = [p for p in parts if not RISK.search(p)]
        removed += [p.strip() for p in parts if RISK.search(p)]
        if keep:
            out_lines.append(" ".join(keep))
    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 소제목 밑이 비었으면 소제목도 뺀다
    text = re.sub(r"(^|\n)##[^\n]*\n\s*(?=(\n##|\Z))", r"\1", text)
    return text.strip(), removed


def main(src, out, report):
    items = load(src, "STOCK_STUDY")
    kept, rows = [], []
    for it in items:
        body, rb = clean_text(it.get("body"))
        summary, rs = clean_text(it.get("summary"))
        before = len(str(it.get("body") or "")) + len(str(it.get("summary") or ""))
        after = len(body) + len(summary)
        n = len(rb) + len(rs)
        ratio = after / before if before else 0
        cls = "SAFE_AS_IS" if n == 0 else ("SANITIZE_AND_RESTORE" if ratio >= 0.6 and summary else "PRIVATE_ONLY")
        rows.append({"id": it.get("id"), "code": it.get("code"), "name": it.get("name"), "date": it.get("date"),
                     "classification": cls, "removedSentences": n, "keptRatio": round(ratio, 3),
                     "reason": ("권리 불명확 수치 문장 없음" if n == 0 else
                                f"컨센서스·목표주가·투자의견·수급·주가배수 문장 {n}개를 뺐다(본문 {round(ratio * 100)}% 유지)")})
        if cls != "PRIVATE_ONLY":
            sources = [x for x in (it.get("sources") or [])
                       if not BAD_SOURCE.search(str(x.get("name", "")) + " " + str(x.get("url", "")))]
            kept.append(dict(it, body=body, summary=summary, sources=sources, sanitized=(n > 0)))
    with open(out, "w", encoding="utf-8") as f:
        f.write("// GAEO 종목 공부(STOCK_STUDY) — 옛 저장소 글을 옮기며 권리 불명확 수치 문장을 뺐다(tools/migration/sanitize_study.py).\n")
        f.write("// 작성 당시 기준의 공부 기록이며 현재의 매수·매도 추천이 아니다.\n")
        f.write("const STOCK_STUDY = " + json.dumps(kept, ensure_ascii=False, indent=1) + ";\n")
    json.dump(rows, open(report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    counts = {c: sum(r["classification"] == c for r in rows) for c in ("SAFE_AS_IS", "SANITIZE_AND_RESTORE", "PRIVATE_ONLY")}
    print(json.dumps({"total": len(rows), **counts}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:4])
