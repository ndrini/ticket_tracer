#!/usr/bin/env bash
# Aggiunge le credenziali AWS a .env (che git ignora) e prova subito S3.
#
#     bash scripts/configura_s3.sh AKIA... 'il-secret' eu-north-1
#
# Il secret va fra apici singoli: spesso contiene caratteri che la shell
# interpreterebbe (/, +, $).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -lt 2 ]; then
  sed -n '2,9p' "$0" | sed 's/^# \?//'
  exit 1
fi

CHIAVE="$1"; SEGRETO="$2"; REGIONE="${3:-eu-north-1}"

if grep -q "^AWS_ACCESS_KEY_ID=" .env 2>/dev/null; then
  echo "In .env ci sono gia' delle credenziali AWS. Tolgo le vecchie."
  sed -i '/^AWS_ACCESS_KEY_ID=/d;/^AWS_SECRET_ACCESS_KEY=/d;/^AWS_REGION=/d' .env
fi

cat >> .env <<EOF

# Credenziali S3 aggiunte il $(date +%Y-%m-%d). File ignorato da git.
AWS_ACCESS_KEY_ID=$CHIAVE
AWS_SECRET_ACCESS_KEY=$SEGRETO
AWS_REGION=$REGIONE
EOF

echo "Scritte in .env. Provo S3..."
echo
uv run python scripts/prova_s3.py --bucket "ticket-tracer-$(date +%s | tail -c 6)" --regione "$REGIONE"
