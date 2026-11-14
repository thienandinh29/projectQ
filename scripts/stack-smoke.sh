#!/usr/bin/env bash
# Checks a running `docker compose up` stack end to end (specs/one-command-start).
# Needs API_KEY in the environment (the same value as in .env). No model keys needed.
#   API_KEY=... scripts/stack-smoke.sh
set -euo pipefail
API=${API:-http://localhost:8000}
WEB=${WEB:-http://localhost:3000}
: "${API_KEY:?set API_KEY to the value in .env}"
failures=0
check() { # name, condition result (0 = pass)
  if [ "$2" = 0 ]; then echo "ok   $1"; else echo "FAIL $1"; failures=$((failures + 1)); fi
}
json() { python3 -c "import sys, json; d = json.load(sys.stdin); print($1)"; }
api() { curl -sS -H "x-api-key: $API_KEY" -H 'content-type: application/json' "$@"; }

health=$(curl -sS "$API/health")
[ "$(echo "$health" | json 'd["status"], d["db"]')" = "ok ok" ]; check "API healthy and connected to the database" $?

code=$(curl -sS -o /dev/null -w '%{http_code}' "$API/openapi.json")
[ "$code" = 401 ]; check "API refuses requests without the key ($code)" $?

code=$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/")
[ "$code" = 200 ]; check "web serves the home page ($code)" $?

learner=$(curl -sS -X POST -H "Origin: $WEB" -H 'content-type: application/json' \
  -d '{"display_name":"Smoke test"}' "$WEB/api/backend/learners" | json 'd["learner_id"]')
[ -n "$learner" ]; check "web reaches the API through its proxy (learner created)" $?

q="learner_id=$learner&course=python-basics&objective=conditions-even"
fn=$(api "$API/code/exercise?$q" | json 'd["function"]')
[ "$fn" = is_even ]; check "code exercise served" $?

attempt() {
  api -d "{\"learner_id\":\"$learner\",\"course\":\"python-basics\",\"objective\":\"conditions-even\",\"code\":\"$1\",\"hints_used\":0}" \
    "$API/code/attempts" | json 'd["status"], d["correct"], d["hidden_passed"]'
}
[ "$(attempt 'def is_even(n):\n    return n % 2 == 0\n')" = "ok True 2" ]
check "right code passes in the sandbox (runner reached)" $?
[ "$(attempt 'def is_even(n):\n    return n % 2 == 1\n')" = "ok False 0" ]
check "wrong code fails in the sandbox" $?
[ "$(attempt 'def is_even(n):\n    while True:\n        pass\n' | cut -d' ' -f1-2)" = "timeout False" ]
check "an infinite loop is stopped" $?

session=$(api "$API/vocab/session?learner_id=$learner&new_limit=2")
item=$(echo "$session" | json 'd["entries"][0]["item"]["id"]')
[ "$(echo "$session" | json 'len(d["entries"]), d["entries"][0]["is_new"], "accepted" in str(d)')" = "2 True False" ]
check "vocabulary session serves new words without the answer key" $?
answered=$(api -d "{\"learner_id\":\"$learner\",\"item_id\":\"$item\",\"answer\":\"definitely-wrong\"}" \
  "$API/vocab/answers" | json 'd["correct"], d["trace"]["kind"]')
[ "$answered" = "False review" ]; check "a vocabulary answer is graded and scheduled (FSRS review trace)" $?

road=$(api "$API/roadmap?learner_id=$learner" | json 'len(d["milestones"]), d["next_milestone"] is not None')
[ "$road" = "10 True" ]; check "grammar roadmap served (10 milestones, a next one to take)" $?
code=$(curl -sS -o /dev/null -w '%{http_code}' -H "x-api-key: $API_KEY" -H 'content-type: application/json' \
  -d "{\"learner_id\":\"$learner\"}" "$API/level-tests")
[ "$code" = 409 ]; check "draft items are not served to a learner without permission ($code)" $?

pages=""
for page in / /kiem-tra /lo-trinh /tu-vung /gioi-thieu /on-tap/cot-moc/passive /kham-pha; do pages="$pages $(curl -sS -o /dev/null -w '%{http_code}' "$WEB$page")"; done
[ "$pages" = " 200 200 200 200 200 200 200" ]; check "English pack pages and the topic explorer load ($pages)" $?
proxied=$(curl -sS "$WEB/api/backend/roadmap?learner_id=$learner&course=english-ielts" | json 'len(d["milestones"])')
[ "$proxied" = 10 ]; check "the web proxy serves the roadmap" $?
code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H "Origin: $WEB" -H 'content-type: application/json' \
  -d "{\"learner_id\":\"$learner\"}" "$WEB/api/backend/level-tests")
[ "$code" = 409 ]; check "the web proxy passes the level test through, drafts still guarded ($code)" $?
code=$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/api/backend/level-tests/not-an-id/answers")
[ "$code" = 404 ]; check "the web proxy refuses paths outside its allowlist ($code)" $?

topic=$(api -d '{"goal_vi":"Kiểm tra hệ thống","mode":"quick","tier":"free"}' "$API/topics" | json 'd["topic_id"]')
status=queued
for _ in $(seq 1 30); do
  status=$(api "$API/topics/$topic" | json 'd["status"]')
  case "$status" in failed | ready) break ;; esac
  sleep 1
done
case "$status" in failed | ready) true ;; *) false ;; esac
check "worker claims and finishes a queued topic job ($status)" $?

if [ "$failures" -gt 0 ]; then echo "$failures check(s) failed"; exit 1; fi
echo "all checks passed"
