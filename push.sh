#!/usr/bin/env bash
REPO="https://github.com/techwithblemac/pixaby.git"
git config --global user.email "techwithblemac@gmail.com"
git config --global user.name "techwithblemac"
git config --global http.postBuffer 524288000
git config --global http.lowSpeedLimit 0
git config --global http.lowSpeedTime 999999

[ -d .git ] || git init
git branch -M main
git remote remove origin 2>/dev/null
git remote add origin "$REPO"
git add .
git commit -m "${1:-update}" || echo "Nothing new to commit"
if git push -u origin main --force; then
  echo "Done: $REPO"
else
  echo "PUSH FAILED - retry"
  exit 1
fi