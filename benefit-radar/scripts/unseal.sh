#!/usr/bin/env bash
# seal.sh 로 암호화한 파일을 복호화한다. 결과 파일은 커밋하지 말고 사용 후 삭제한다.
# 사용법: unseal.sh <암호문 입력> <평문 출력> [암호가 든 환경변수 이름, 기본 REPORT_PASSPHRASE]
set -euo pipefail
set +x
in="$1"; out="$2"; key_env="${3:-REPORT_PASSPHRASE}"
if [ -z "${!key_env:-}" ]; then echo "unseal: \$$key_env is not set" >&2; exit 2; fi
umask 077
openssl enc -d -aes-256-cbc -md sha256 -pbkdf2 -iter 200000 -salt -a -pass "env:$key_env" -in "$in" -out "$out"
