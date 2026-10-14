#!/usr/bin/env bash
# 정책 블로그 원고 발행 파이프라인 (Routine 세션에서 실행).
#
#   REPORT_PASSPHRASE=... RECIPIENTS="받는사람,..." [CC="참조,..."] [PRIVACY_DENYLIST=...] [TEST_MODE=1] \
#     ./publish_posts.sh <평문 posts.json 경로(저장소 밖 임시 폴더)> [YYYY-MM-DD]
#
# 1) 암호화된 이력 복호화 → 2) 중복 제거·kind 보정 → 3) 검증 + 메일 payload 렌더링
# 4) payload·이력을 암호화해 benefit-radar/outbox, benefit-radar/state 에 저장 (기존 발송 워크플로가 그대로 메일을 보냄)
#    썸네일 PNG 는 <저장소>/public/<날짜>/<id>/01_thumb.png 에 만든다. 메일 본문이 이 공개 주소를 가리키므로
#    호출자는 **public/ 을 먼저 commit·push 한 뒤** outbox/state 를 push 해야 한다(INSTRUCTIONS 7장).
# TEST_MODE=1 이면 제목에 [시험]을 붙이고 이력(state)을 갱신하지 않는다(형식 확인용).
# 새 원고가 없으면 "오늘은 새 정책이 없어요" 알림 메일을 만든다(posts.json 의 scan.checked·scan.note 를 메일에 넣는다).
set -euo pipefail
set +x
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
radar="$root/benefit-radar/scripts"
posts_in="$1"
today="${2:-$(TZ=Asia/Seoul date +%F)}"
: "${REPORT_PASSPHRASE:?REPORT_PASSPHRASE not set}"
: "${RECIPIENTS:?RECIPIENTS not set}"

case "$(cd "$(dirname "$posts_in")" && pwd)" in
  "$(git -C "$root" rev-parse --show-toplevel)"*) echo "publish_posts: posts.json must live outside the repository" >&2; exit 2 ;;
esac

tmp="$(mktemp -d)"; chmod 700 "$tmp"
trap 'rm -rf "$tmp"' EXIT
cp "$posts_in" "$tmp/posts.json"

state_enc="$root/benefit-radar/state/blog-state.json.enc"
if [ -f "$state_enc" ]; then
  "$radar/unseal.sh" "$state_enc" "$tmp/state.json"
else
  python3 "$here/blog_state.py" init --state "$tmp/state.json"
fi

# 검증을 먼저(중복 제거 전 원본도 규칙을 지켜야 함), 그다음 중복 제거
python3 "$here/blog_state.py" merge --state "$tmp/state.json" --posts "$tmp/posts.json" --today "$today" | tee "$tmp/merge.txt"
# remaining=0 이면 "오늘은 새 정책이 없어요" 알림 메일을 보낸다(썸네일 없음, 이력 변화 없음)
to_args=()
IFS=',' read -ra rcpts <<< "$RECIPIENTS"
for r in "${rcpts[@]}"; do r="$(echo "$r" | xargs)"; [ -n "$r" ] && to_args+=(--to "$r"); done
IFS=',' read -ra ccs <<< "${CC:-}"
for r in "${ccs[@]}"; do r="$(echo "$r" | xargs)"; [ -n "$r" ] && to_args+=(--cc "$r"); done

# 썸네일(공개 주소용). Pillow·한글 글꼴이 없으면 건너뛰고 썸네일 없이 진행한다.
python3 "$here/make_thumb.py" --posts "$tmp/posts.json" --out-dir "$root/public" --today "$today" || true
if [ -z "${PUBLIC_BASE_URL:-}" ]; then
  remote="$(git -C "$root" remote get-url origin | sed -E 's#(\.git)?$##; s#^.*github\.com[:/]##')"
  branch="$(git -C "$root" rev-parse --abbrev-ref HEAD)"
  PUBLIC_BASE_URL="https://raw.githubusercontent.com/$remote/refs/heads/$branch/public"
fi
test_args=(); [ "${TEST_MODE:-}" = "1" ] && test_args+=(--test)
python3 "$here/render_posts.py" --posts "$tmp/posts.json" "${to_args[@]}" --today "$today" --out "$tmp/payload.json" \
  --public-base "$PUBLIC_BASE_URL" --thumb-dir "$root/public" ${test_args[@]+"${test_args[@]}"}
python3 "$radar/deliver.py" "$tmp/payload.json" --dry-run >/dev/null

out="$root/benefit-radar/outbox/blog-$today.json.enc"
if [ -e "$out" ]; then out="$root/benefit-radar/outbox/blog-$today-$(date +%H%M%S).json.enc"; fi
"$radar/seal.sh" "$tmp/payload.json" "$out"
if [ "${TEST_MODE:-}" != "1" ]; then "$radar/seal.sh" "$tmp/state.json" "$state_enc"; fi

"$radar/unseal.sh" "$out" "$tmp/check.json"
cmp -s "$tmp/payload.json" "$tmp/check.json" || { echo "publish_posts: seal round-trip mismatch" >&2; exit 1; }
echo "publish_posts: sealed $(basename "$out") and blog-state.json.enc"
