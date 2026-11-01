#!/usr/bin/env bash
# Usage: inject_token.sh <in.html> <out.html>
# Replaces __SH_SCORES_TOKEN__ with $STUDY_HUB_SCORES_TOKEN. Never prints the token.
# The output holds a live token: it must ONLY go into the study-hub-src mirror and then
# through study-hub/tools/publish.sh (StatiCrypt). Never commit or share it in plaintext.
set -euo pipefail
[ $# -eq 2 ] || { echo "usage: $0 <in.html> <out.html>" >&2; exit 2; }
umask 077
python3 - "$1" "$2" <<'PY'
import os, sys
tok = os.environ.get('STUDY_HUB_SCORES_TOKEN', '').strip()
if not tok:
    sys.exit('STUDY_HUB_SCORES_TOKEN is empty or unset; refusing to build')
if any(c in tok for c in '\'"\\<>\n\r ') :
    sys.exit('STUDY_HUB_SCORES_TOKEN has unexpected characters; refusing to build')
src, dst = sys.argv[1], sys.argv[2]
h = open(src, encoding='utf-8').read()
n = h.count('__SH_SCORES_TOKEN__')
if n != 1:
    sys.exit(f'expected exactly 1 token placeholder in {src}, found {n}')
tmp = dst + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(h.replace('__SH_SCORES_TOKEN__', tok))
os.replace(tmp, dst)
print(f'injected token into {dst} (1 placeholder replaced)')
PY
