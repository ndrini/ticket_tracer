#!/bin/bash
#
# Prepara il dataset Kaggle per il benchmark LLaVA
#
# Uso:
#   bash scripts/prepare_kaggle_dataset.sh
#
# Output: /tmp/ticket-tracer-kaggle-dataset/ pronto per upload
#

set -e

DATASET_DIR="/tmp/ticket-tracer-kaggle-dataset"
IMAGES_SAMPLE=50  # Quante immagini includere

echo "🔧 Preparazione dataset Kaggle per LLaVA benchmark"
echo ""

# Crea struttura
echo "📁 Creazione cartelle..."
mkdir -p "$DATASET_DIR/ritagli"
rm -rf "$DATASET_DIR"/* 2>/dev/null || true

# Copia sample immagini (prime 50)
echo "📋 Copia immagini (sample $IMAGES_SAMPLE)..."
cp $(ls data/ritagli/*.jpg | head -$IMAGES_SAMPLE) "$DATASET_DIR/ritagli/" 2>/dev/null || {
    echo "⚠️  No images found in data/ritagli/"
    exit 1
}

IMAGE_COUNT=$(ls "$DATASET_DIR/ritagli/" | wc -l)
echo "   ✅ Copiate $IMAGE_COUNT immagini"

# Crea metadata file
echo "📝 Creazione metadati..."
cat > "$DATASET_DIR/dataset-metadata.json" <<'JSON'
{
  "title": "Ticket Tracer Receipt Images",
  "id": "aless-drini-ndrini-eu/ticket-tracer-receipt-images",
  "licenses": [
    {
      "name": "CC0: Public Domain"
    }
  ],
  "keywords": ["receipts", "extraction", "llava", "computer-vision"],
  "collaborators": [],
  "data": []
}
JSON

echo "   ✅ Metadati OK"

# Calcola dimensione
SIZE=$(du -sh "$DATASET_DIR" | cut -f1)
echo ""
echo "📊 Dataset pronto:"
echo "   Cartella: $DATASET_DIR"
echo "   Immagini: $IMAGE_COUNT"
echo "   Dimensione: $SIZE"

echo ""
echo "📤 Per caricare su Kaggle:"
echo ""
echo "   1. Accedi a https://www.kaggle.com/settings/account"
echo "   2. Scarica il file kaggle.json (API token)"
echo "   3. Posiziona in ~/.kaggle/kaggle.json"
echo ""
echo "   4. Upload dataset:"
echo "      cd $DATASET_DIR"
echo "      kaggle datasets create -p . --dataset-name ticket-tracer-receipt-images --public false"
echo ""
echo "   5. Attendi conferma (1-2 minuti)"
echo ""
echo "✅ Fatto!"
