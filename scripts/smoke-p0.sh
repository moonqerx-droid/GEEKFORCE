#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$repo_root"

docker compose up -d --build

health_url="http://localhost:8000/health"
attempt=1
until curl --fail --silent --show-error "$health_url" >/dev/null 2>&1; do
  if [ "$attempt" -ge 40 ]; then
    echo "API did not become healthy after 40 attempts" >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 2
done

create_response=$(mktemp "${TMPDIR:-/tmp}/helpflow-create.XXXXXX")
message_response=$(mktemp "${TMPDIR:-/tmp}/helpflow-message.XXXXXX")
trap 'rm -f "$create_response" "$message_response"' EXIT

curl --fail --silent --show-error \
  --request POST \
  --header "Content-Type: application/json" \
  --output "$create_response" \
  http://localhost:8000/api/conversations

conversation_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' < "$create_response")

curl --fail --silent --show-error \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{"content":"Привет, не работает VPN"}' \
  --output "$message_response" \
  "http://localhost:8000/api/conversations/$conversation_id/messages"

python3 -c 'import json,sys; data=json.load(sys.stdin); assert any(m.get("role") == "assistant" and str(m.get("content", "")).strip() for m in data["messages"]), "assistant response is empty"' < "$message_response"

echo "P0 smoke passed for conversation $conversation_id"
echo "Frontend: http://localhost:5173/ (run: cd apps/web && npm run dev)"
echo "Operator: http://localhost:5173/operator"
echo "Backend debug: http://localhost:8000/debug"
echo "Backend operator: http://localhost:8000/debug/operator"
