#!/usr/bin/env bash
# 전환일 1회: 옛 저장소(gaeo-analyst-team) main 의 OpenDART 상태·산출물을 새 저장소로 옮긴다.
# 옮기는 것은 OpenDART 유래 파일뿐이다(목록 고정). 네이버·KIND·모의투자 파일은 목록에 없다.
# 사용: bash tools/migration/sync_dart_state.sh <옛 저장소 clone 경로>
set -euo pipefail
OLD="${1:?옛 저장소 clone 경로}"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
FILES=(
  research_archive/dart/seen_rcept.json
  research_archive/dart/corp_map.json
  research_archive/dart/api_budget.json
  research_archive/dart/collection_status.json
  gaeo_coverage/corporate_action_evidence.json
  dart_today.js
  disclosure_research/contract.json
  disclosure_research/disclosure_changes.json
  disclosure_research/financial_changes.json
  disclosure_research/event_timelines.json
)
for f in "${FILES[@]}"; do
  cp "$OLD/$f" "$HERE/$f"
  echo "synced $f"
done
rm -f "$HERE"/dart_financials/*.json
cp "$OLD"/dart_financials/*.json "$HERE/dart_financials/"
echo "synced dart_financials/ ($(ls "$HERE"/dart_financials | wc -l) files)"
python3 "$HERE/tools/public_checks.py" --tree
