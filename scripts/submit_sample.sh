#!/usr/bin/env bash
# Submit one sample PDF to the running intake API and print the response.
#   scripts/submit_sample.sh [title] [idempotency-key]
cd "$(dirname "$0")/.."
TITLE=${1:-"Invoice 9001"}
KEY=${2:-"sample-$(date +%s)-$RANDOM"}
TOKEN=$(.venv/bin/python -c "from rmflow import auth; print(auth.mint('acme-portal', 'submitter'))")
DOC=$(printf '%%PDF-1.4\n%% %s\n' "$TITLE" | base64)
curl -s -X POST http://127.0.0.1:8890/v1/records -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $KEY" -H 'content-type: application/json' \
  -d "{\"title\":\"$TITLE\",\"doc_type\":\"invoice\",\"filename\":\"invoice.pdf\",\"document_b64\":\"$DOC\",\"fields\":{\"amount\":\"880.00\",\"vendor\":\"Northwind\"}}"
echo
