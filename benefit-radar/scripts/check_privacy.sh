#!/usr/bin/env bash
# 커밋 직전 개인정보 유출 검사. 문제가 있으면 exit 1 → 커밋하지 말 것.
#
#   PRIVACY_DENYLIST="이름1,이름2,이메일1,..." ./check_privacy.sh
#
# PRIVACY_DENYLIST 는 비공개 Routine 설정에만 두고 저장소에 적지 않는다.
# 검사 대상: 스테이징된 변경 내용(+ 줄)과 파일 경로. 매칭된 값 자체는 출력하지 않는다.
set -euo pipefail
set +x
cd "$(git rev-parse --show-toplevel)"

fail=0
report() { echo "privacy-check: $1" >&2; fail=1; }

paths="$(git diff --cached --name-only --diff-filter=ACMR)"

# 1) outbox/state 에는 암호문(.enc)과 .gitkeep 만 허용
while IFS= read -r p; do
  [ -z "$p" ] && continue
  case "$p" in
    benefit-radar/outbox/*|benefit-radar/state/*)
      case "$p" in *.enc|*/.gitkeep) ;; *) report "plaintext file in outbox/state: $p" ;; esac ;;
  esac
done <<< "$paths"

# 2) 암호문 파일은 openssl base64 헤더(U2FsdGVkX1)로 시작해야 함
while IFS= read -r p; do
  case "$p" in
    *.enc) head -c 10 "$p" | grep -q '^U2FsdGVkX1' || report "not an openssl-sealed file: $p" ;;
  esac
done <<< "$paths"

# 암호문 줄은 내용 검사에서 제외 (base64 가 우연히 패턴과 맞을 수 있음)
plain_added="$(git diff --cached --unified=0 --diff-filter=ACMR -- . ':(exclude)*.enc' | grep -E '^\+' | grep -vE '^\+\+\+ ' || true)"

# 3) 이메일 주소(예시용 도메인 제외)
if printf '%s\n' "$plain_added" \
  | grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' \
  | grep -viE '@(example\.(com|org|net)|anthropic\.com|users\.noreply\.github\.com)$' \
  | grep -q .; then
  report "email address found in staged changes"
fi

# 4) 주민등록번호 / 휴대폰 번호 패턴
printf '%s\n' "$plain_added" | grep -qE '[0-9]{6}-[1-4][0-9]{6}' && report "resident registration number pattern found"
printf '%s\n' "$plain_added" | grep -qE '01[016789]-?[0-9]{3,4}-?[0-9]{4}' && report "phone number pattern found"

# 5) 비공개 금지어(이름, 실제 이메일, 주소 등)
if [ -n "${PRIVACY_DENYLIST:-}" ]; then
  IFS=',' read -ra terms <<< "$PRIVACY_DENYLIST"
  n=0
  for t in "${terms[@]}"; do
    t="$(echo "$t" | xargs)"; [ -z "$t" ] && continue
    n=$((n+1))
    if printf '%s\n%s\n' "$plain_added" "$paths" | grep -qiF -- "$t"; then
      report "denylisted term #$n found in staged changes or paths"
    fi
  done
  # 커밋 메시지 초안도 검사하려면 COMMIT_MSG_FILE 지정
  if [ -n "${COMMIT_MSG_FILE:-}" ] && [ -f "$COMMIT_MSG_FILE" ]; then
    for t in "${terms[@]}"; do
      t="$(echo "$t" | xargs)"; [ -z "$t" ] && continue
      grep -qiF -- "$t" "$COMMIT_MSG_FILE" && report "denylisted term found in commit message"
    done
  fi
else
  echo "privacy-check: warning: PRIVACY_DENYLIST not set (name/address checks skipped)" >&2
fi

if [ "$fail" -ne 0 ]; then
  echo "privacy-check: FAILED — do not commit" >&2
  exit 1
fi
echo "privacy-check: OK"
