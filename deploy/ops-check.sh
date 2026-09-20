#!/usr/bin/env sh
set -eu

node --test tests/ops/*.test.mjs
printf '%s\n' "PASS: offline operations checks"
