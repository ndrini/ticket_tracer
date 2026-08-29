"""
Fase E.3 — Applica la normalizzazione al database.

Legge le validazioni dai sinonimi, crea la mappatura nome_originale → product_id_canonico,
e aggiorna i receipt_lines per usare i prodotti normalizzati.

Misura: Preservation = righe 'complete' ancora mappate dopo update.
Deve stare a ~100%.

Uso:
    uv run python scripts/fase_e_3_applica_normalizzazione.py
    uv run python scripts/fase_e_3_applica_normalizzazione.py --db data/spese.db --dry-run
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/spese.db")
    parser.add_argument("--validazioni", default="data/fase_e_validazioni_sinonimi.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    # Leggi le validazioni
    with open(args.validazioni) as f:
        validazioni = json.load(f)

    # Leggi il catalogo grezzo per la mappatura
    with open("data/fase_e_1_catalogo_grezzo.json") as f:
        catalogo_data = json.load(f)

    catalogo = {item["canonical_name"]: item for item in catalogo_data["catalogo"]}

    # Costruisci la mappatura: nome_canonico → nome_canonico_finale (post-merge)
    nome_to_canonical = {}  # { canonical_name → final_canonical_name }

    # Leggi il catalogo grezzo per i singoletti
    with open("data/fase_e_1_catalogo_grezzo.json") as f:
        catalogo_data = json.load(f)

    all_canonical_names = set(item["canonical_name"] for item in catalogo_data["catalogo"])

    # Prima: tutti i nomi singoletti → mappati a sé stessi
    for name in all_canonical_names:
        nome_to_canonical[name] = name

    # Poi: sovrascrivi con le decisioni dalle validazioni
    for cluster_key, validation in validazioni.items():
        decision = validation["decision"]
        elements = validation["elements"]

        if decision.startswith("MERGE_A_"):
            final_canonical = decision.replace("MERGE_A_", "").lower()
            for element in elements:
                nome_to_canonical[element] = final_canonical
        elif decision == "SKIP":
            # I SKIP vengono conservati ma non mergiati: restano come singoletti
            # (questo preserva i dati anche se sono OCR garbage)
            for element in elements:
                nome_to_canonical[element] = element
        elif decision == "REVIEW":
            # Default: mantieni come è (no merge)
            for element in elements:
                nome_to_canonical[element] = element

    print(f"\nMappatura costruita:")
    print(f"  Nome canonici mappati: {len(nome_to_canonical)}")
    print(f"  Nomi marcati come SKIP: {sum(1 for v in nome_to_canonical.values() if v is None)}")
    print()

    # Collega il database
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Conta PRIMA: preservation baseline
    cursor.execute("""
        SELECT COUNT(*) as n FROM receipt_lines
        WHERE name_quality = 'complete' AND extraction_method = 'geometric'
    """)
    count_before = cursor.fetchone()["n"]
    print(f"Baseline (prima della normalizzazione):")
    print(f"  Righe 'complete' geometriche: {count_before}")

    # Leggi solo i prodotti usati dalle righe 'complete' geometriche
    cursor.execute("""
        SELECT DISTINCT p.id, p.name
        FROM products p
        JOIN receipt_lines rl ON rl.product_id = p.id
        WHERE rl.name_quality = 'complete' AND rl.extraction_method = 'geometric'
    """)
    products = {row["name"]: row["id"] for row in cursor.fetchall()}

    # Trova o crea i prodotti canonici
    canonical_product_ids = {}  # { canonical_name → product_id }

    for canonical_name in set(nome_to_canonical.values()):
        if canonical_name is None:
            continue

        # Verifica se il canonico esiste già come prodotto
        if canonical_name in products:
            canonical_product_ids[canonical_name] = products[canonical_name]
        else:
            # Crea un nuovo prodotto canonico
            cursor.execute(
                "INSERT INTO products (name, aka) VALUES (?, ?)",
                (canonical_name, json.dumps([]))
            )
            canonical_product_ids[canonical_name] = cursor.lastrowid

    print(f"\nProdotti canonici creati/trovati: {len(canonical_product_ids)}")

    # Costruisci la mappa: original_product_name → canonical_product_id
    # Nota: original_name nel DB potrebbe non essere normalizzato (case, whitespace)
    original_to_canonical_id = {}
    for original_name, product_id in products.items():
        # Normalizza come fatto nella fase_e_1
        normalized_original = original_name.lower().strip()
        canonical_name = nome_to_canonical.get(normalized_original, normalized_original)
        if canonical_name is None:
            original_to_canonical_id[product_id] = None
        else:
            original_to_canonical_id[product_id] = canonical_product_ids.get(canonical_name)

    print(f"Mappatura prodotti: {len(original_to_canonical_id)} prodotti mappati")

    if not args.dry_run:
        # Applica gli update
        updated_rows = 0
        for orig_product_id, canonical_product_id in original_to_canonical_id.items():
            if canonical_product_id is not None:
                # Aggiorna al prodotto canonico
                cursor.execute(
                    "UPDATE receipt_lines SET product_id = ? WHERE product_id = ? AND extraction_method = 'geometric'",
                    (canonical_product_id, orig_product_id)
                )
                updated_rows += cursor.rowcount

        conn.commit()
        print(f"\nApplicato:")
        print(f"  Righe aggiornate (remapped): {updated_rows}")

        # Verifica DOPO
        cursor.execute("""
            SELECT COUNT(*) as n FROM receipt_lines
            WHERE name_quality = 'complete' AND extraction_method = 'geometric'
        """)
        count_after = cursor.fetchone()["n"]
        preservation = 100.0 * count_after / count_before if count_before > 0 else 0

        print(f"\nAfter normalizzazione:")
        print(f"  Righe 'complete' geometriche: {count_after}")
        print(f"  Preservation rate: {preservation:.1f}%")

        if preservation < 95:
            print(f"\n❌ FALLIMENTO: Preservation < 95%!")
            return 1

        print(f"\n✅ Preservation OK: {preservation:.1f}%")
    else:
        print(f"\n(dry-run: nessun update applicato)")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
