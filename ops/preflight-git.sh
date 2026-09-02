#!/usr/bin/env bash
#
# What would actually reach GitHub, checked before the first push rather than
# after. A private key that lands in the history is compromised even if a later
# commit deletes it, so this runs against the staged index, not the working tree.
#
#   bash ops/preflight-git.sh
#
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d .git ]; then
  echo "no git repository here yet — run: git init -b main"
  exit 1
fi

git add -A

staged=$(git ls-files --cached)
total=$(printf '%s\n' "$staged" | grep -c . || true)
echo "files that would be committed: ${total}"
echo

fail=0
check() {
  local label="$1" pattern="$2"
  local hits
  hits=$(printf '%s\n' "$staged" | grep -E "$pattern" || true)
  if [ -n "$hits" ]; then
    printf '  FAIL  %s\n' "$label"
    printf '%s\n' "$hits" | sed 's/^/          /'
    fail=1
  else
    printf '  ok    %s\n' "$label"
  fi
}

check "no .env files"              '(^|/)\.env$'
check "no device or TLS keys"      '(^|/)keys/|\.(key|pem|crt|srl|p12|jks)$'
check "no runtime logs"            '^logs/'
check "no dependency trees"        'node_modules/|\.venv/'
check "no build or tool caches"    '\.angular/|egg-info/|__pycache__/|\.(ruff|pytest|mypy)_cache/'

printf '  '
if git grep --cached -lE 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' -- . ':!*.md' 2>/dev/null; then
  echo 'FAIL  PEM private key material found in staged content'
  fail=1
else
  echo 'ok    no PEM private keys in staged content'
fi

echo
if [ "$fail" -ne 0 ]; then
  echo 'DO NOT PUSH. Fix .gitignore, then: git rm -r --cached <path>'
  exit 1
fi
echo 'Clean. Safe to commit and push.'
