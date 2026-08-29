"""
Fase E.4 — Proponi la spezzatura dei nomi fused.

Legge le 150 righe con name_quality='fused', cerca i prodotti nel catalogo
canonico che corrispondono ai token nel nome fused, e propone la spezzatura.

Uso:
    uv run python scripts/fase_e_4_proponi_spezzatura.py
    uv run python scripts/fase_e_4_proponi_spezzatura.py --threshold 0.7
"""
import argparse
import json
import sqlite3
import sys
import re
from difflib import SequenceMatcher


def similarity(a, b):
    """Similarità testuale fra due stringhe (0-1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def tokenize(name):
    """Divide il nome in token."""
    # Divide per spazi, punteggiatura, ma mantiene i numeri
    tokens = re.findall(r"\b\w+\b", name.lower())
    return [t for t in tokens if len(t) > 2]  # Escludi token < 3 char


def best_match_in_catalog(token, catalog, threshold=0.7):
    """
    Cerca il miglior match di un token nel catalogo.
    Restituisce (product_id, nome, confidenza) o (None, None, 0).
    """
    best = (None, None, 0)

    for prod_name, prod_id in catalog.items():
        sim = similarity(token, prod_name)
        if sim >= threshold and sim > best[2]:
            best = (prod_id, prod_name, sim)

    return best


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/spese.db")
    parser.add_argument("--threshold", type=float, default=0.75)
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Leggi il catalogo canonico (prodotti creati in E.3)
    cursor.execute("""
        SELECT id, name FROM products
        WHERE id IN (
            SELECT DISTINCT product_id FROM receipt_lines
            WHERE extraction_method = 'geometric' AND name_quality = 'complete'
        )
    """)
    catalog = {row["name"].lower().strip(): row["id"] for row in cursor.fetchall()}

    print(f"Catalogo canonico caricato: {len(catalog)} prodotti\n")

    # Leggi i nomi fused
    cursor.execute("""
        SELECT rl.id, rl.receipt_id, p.name, rl.total_price
        FROM receipt_lines rl
        JOIN products p ON rl.product_id = p.id
        WHERE rl.name_quality = 'fused' AND rl.extraction_method = 'geometric'
        ORDER BY rl.id
    """)

    fused_rows = cursor.fetchall()
    print(f"Righe fused trovate: {len(fused_rows)}\n")

    proposte = []
    successful = 0
    unmatched_count = 0

    for fused_row in fused_rows:
        fused_name = fused_row["name"]
        tokens = tokenize(fused_name)

        if len(tokens) < 2:
            # Non ci sono abbastanza token per spezzare
            continue

        # Cerca il match per ogni token
        matches = []
        for token in tokens:
            prod_id, prod_name, conf = best_match_in_catalog(token, catalog, args.threshold)
            if prod_id is not None:
                matches.append({
                    "token": token,
                    "product_id": prod_id,
                    "product_name": prod_name,
                    "confidence": conf
                })
            else:
                matches.append({
                    "token": token,
                    "product_id": None,
                    "product_name": None,
                    "confidence": 0.0
                })

        # Filtra i match con confidenza >= threshold
        strong_matches = [m for m in matches if m["confidence"] >= args.threshold]

        # Se abbiamo 2+ forti match, suggeriamo la spezzatura
        if len(strong_matches) >= 2:
            proposte.append({
                "receipt_line_id": fused_row["id"],
                "receipt_id": fused_row["receipt_id"],
                "fused_name": fused_name,
                "total_price": fused_row["total_price"],
                "tokens": tokens,
                "matches": matches,
                "strong_matches": strong_matches,
                "decision": "SPLIT_SUGGESTED"
            })
            successful += 1
        else:
            proposte.append({
                "receipt_line_id": fused_row["id"],
                "receipt_id": fused_row["receipt_id"],
                "fused_name": fused_name,
                "total_price": fused_row["total_price"],
                "tokens": tokens,
                "matches": matches,
                "strong_matches": strong_matches,
                "decision": "CANNOT_SPLIT"
            })
            unmatched_count += 1

    # Salva il report
    output_path = "data/fase_e_4_proponi_spezzatura.json"
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_fused": len(fused_rows),
                "splittable_suggested": successful,
                "cannot_split": unmatched_count,
                "threshold": args.threshold,
                "phase": "E.4 — Proponi spezzatura"
            },
            "proposte": proposte
        }, f, indent=2)

    print(f"Report salvato: {output_path}\n")

    print(f"Risultati:")
    print(f"  Righe fused totali: {len(fused_rows)}")
    print(f"  Spezzabili suggerite: {successful}  ({100*successful//len(fused_rows)}%)")
    print(f"  Non spezzabili: {unmatched_count}  ({100*unmatched_count//len(fused_rows)}%)\n")

    # Mostra alcuni esempi
    print("Esempi di spezzature suggerite:\n")
    for prop in proposte[:5]:
        if prop["decision"] == "SPLIT_SUGGESTED":
            print(f"  Fused: '{prop['fused_name']}'  (prezzo: €{prop['total_price']:.2f})")
            for m in prop["strong_matches"]:
                print(f"    → {m['token']:15s} →  '{m['product_name']}'  ({m['confidence']:.0%})")
            print()

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
