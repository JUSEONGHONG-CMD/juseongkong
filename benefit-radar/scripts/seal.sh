#!/usr/bin/env bash
# 평문 파일을 AES-256으로 암호화한다(공개 저장소에는 결과물만 올린다).
# 사용법: seal.sh <평문 입력> <암호문 출력> [암호가 든 환경변수 이름, 기본 REPORT_PASSPHRASE]
# 가구(사용자)별로 다른 키를 쓰려면 세 번째 인자로 다른 환경변수 이름을 넘긴다.
set -euo pipefail
set +x
in="$1"; out="$2"; key_env="${3:-REPORT_PASSPHRASE}"
if [ -z "${!key_env:-}" ]; then echo "seal: \$$key_env is not set" >&2; exit 2; fi
openssl enc -aes-256-cbc -md sha256 -pbkdf2 -iter 200000 -salt -a -pass "env:$key_env" -in "$in" -out "$out"
