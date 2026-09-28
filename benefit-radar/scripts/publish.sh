#!/usr/bin/env bash
# 주간 리포트 발행 파이프라인 (Routine 세션에서 실행).
#
#   REPORT_PASSPHRASE=... RECIPIENTS="받는사람,..." [CC="참조,..."] \
#     ./publish.sh <평문 report.json 경로(저장소 밖 임시 폴더)> [YYYY-MM-DD]
#
# 1) 암호화된 알림 이력(state) 복호화 → 2) 이력 병합(is_new, 누적 목록)
# 3) 이메일 payload 렌더링 → 4) payload·state 암호화해 outbox/ state/ 에 저장
# 평문 파일은 전부 저장소 밖 임시 폴더에서만 다루고 끝나면 지운다. 커밋·푸시는 하지 않는다.
set -euo pipefail
set +x
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
report_in="$1"
today="${2:-$(TZ=Asia/Seoul date +%F)}"
: "${REPORT_PASSPHRASE:?REPORT_PASSPHRASE not set}"
: "${RECIPIENTS:?RECIPIENTS not set}"

case "$(cd "$(dirname "$report_in")" && pwd)" in
  "$(git -C "$root" rev-parse --show-toplevel)"*) echo "publish: report.json must live outside the repository" >&2; exit 2 ;;
esac

tmp="$(mktemp -d)"; chmod 700 "$tmp"
trap 'rm -rf "$tmp"' EXIT
cp "$report_in" "$tmp/report.json"

state_enc="$root/state/state.json.enc"
if [ -f "$state_enc" ]; then
  "$here/unseal.sh" "$state_enc" "$tmp/state.json"
else
  python3 "$here/state.py" init --state "$tmp/state.json"
fi

python3 "$here/state.py" merge --state "$tmp/state.json" --report "$tmp/report.json" --today "$today"

to_args=()
IFS=',' read -ra rcpts <<< "$RECIPIENTS"
for r in "${rcpts[@]}"; do r="$(echo "$r" | xargs)"; [ -n "$r" ] && to_args+=(--to "$r"); done
IFS=',' read -ra ccs <<< "${CC:-}"
for r in "${ccs[@]}"; do r="$(echo "$r" | xargs)"; [ -n "$r" ] && to_args+=(--cc "$r"); done

python3 "$here/render_email.py" --report "$tmp/report.json" "${to_args[@]}" --today "$today" --out "$tmp/payload.json"
python3 "$here/deliver.py" "$tmp/payload.json" --dry-run >/dev/null

out="$root/outbox/$today.json.enc"
if [ -e "$out" ]; then out="$root/outbox/$today-$(date +%H%M%S).json.enc"; fi
"$here/seal.sh" "$tmp/payload.json" "$out"
"$here/seal.sh" "$tmp/state.json" "$state_enc"

# 왕복 검증: 복호화 결과가 원본과 같아야 함
"$here/unseal.sh" "$out" "$tmp/check.json"
cmp -s "$tmp/payload.json" "$tmp/check.json" || { echo "publish: seal round-trip mismatch" >&2; exit 1; }

cp "$tmp/report.json" "$report_in"   # 이력이 반영된 report 를 호출자 임시 폴더에 되돌려 줌(커밋 금지)
echo "publish: sealed $(basename "$out") and state.json.enc"
