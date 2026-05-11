#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# run.sh — Pipeline ingest + NLP avec notifications Telegram
# ═══════════════════════════════════════════════════════════════
set -e
set -o pipefail   # tee ne doit pas masquer les erreurs Python

cd /home/simo/Documents/news-intelligence
source .venv/bin/activate

# ─── CONFIG ────────────────────────────────────────────────────
DB="news.duckdb"
WORK="news.duckdb.work"
LOG_DIR="logs"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOG_DIR"

# ─── TELEGRAM ──────────────────────────────────────────────────
TG_TOKEN="8628519780:AAFeNc-mYm52pTiNrB1Z7_NYBmbuHOAAivI"
TG_CHAT="8548531132"

notify() {
    local msg="$1"
    curl -s --max-time 10 \
        --data-urlencode "chat_id=${TG_CHAT}" \
        --data-urlencode "text=${msg}" \
        --data-urlencode "parse_mode=Markdown" \
        "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" > /dev/null || true
}

# Catch errors and notify before exiting
trap 'notify "❌ *Pipeline failed* at $(date +%H:%M)
Check logs on the ThinkCentre."; exit 1' ERR

# ─── START ─────────────────────────────────────────────────────
notify "🚀 *Pipeline started* at $(date +%H:%M)"

echo "═══════════════════════════════════════════════════════"
echo "  RUN $TS"
echo "═══════════════════════════════════════════════════════"

# ─── 1. Copie ──────────────────────────────────────────────────
cp "$DB" "$WORK"

# ─── 2. INGEST ─────────────────────────────────────────────────
notify "📥 *Ingestion* in progress…"
DB_PATH="$PWD/$WORK" python ingest.py 2>&1 | tee "$LOG_DIR/ingest_$TS.log"

# Stats ingestion : "Insérés en DB   : X"
INGEST_COUNT=$(grep -oP "Insérés en DB\s*:\s*\K[0-9]+" "$LOG_DIR/ingest_$TS.log" | tail -1 || echo "?")
notify "✅ *Ingestion done* — ${INGEST_COUNT} new articles"

# ─── 3. NLP ────────────────────────────────────────────────────
notify "🧠 *NLP* in progress…"
DB_PATH="$PWD/$WORK" python nlp.py 2>&1 | tee "$LOG_DIR/nlp_$TS.log"

# Stats nlp : "X mots insérés en"
NLP_WORDS=$(grep -oP "[0-9,]+(?= mots insérés)" "$LOG_DIR/nlp_$TS.log" | tail -1 || echo "?")
NLP_ARTICLES=$(grep -oP "Articles traités\s*:\s*\K[0-9]+" "$LOG_DIR/nlp_$TS.log" | tail -1 || echo "?")
notify "✅ *NLP done* — ${NLP_ARTICLES} articles, ${NLP_WORDS} words"

# ─── 4. Swap ───────────────────────────────────────────────────
mv "$WORK" "$DB"

# ─── DONE ──────────────────────────────────────────────────────
notify "🎉 *Pipeline complete* at $(date +%H:%M)
Next run in 6h."

echo "✅ Run $TS terminé"