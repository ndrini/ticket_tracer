"""
Fase G — Migra i dati del catalogo (E.1–E.5) dai file JSON al database.

Legge i file JSON generati nelle fasi E.1–E.5 e li importa nelle tabelle
catalog_versions, catalog_snapshots, catalog_decisions.

Uso:
    uv run python scripts/fase_g_migra_catalogo_al_db.py
    uv run python scripts/fase_g_migra_catalogo_al_db.py --db data/spese.db --dry-run
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/spese.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()

    timestamp_now = datetime.now().isoformat()

    print("\n📥 Migrazione catalogo E.1–E.5 nel database\n")

    # --- E.1: Catalogo grezzo ---
    e1_path = Path("data/fase_e_1_catalogo_grezzo.json")
    if e1_path.exists():
        print(f"E.1: Leggo {e1_path.name}...")
        with open(e1_path) as f:
            e1_data = json.load(f)

        if not args.dry_run:
            cursor.execute(
                """INSERT INTO catalog_versions (phase, status, created_at, description, stats)
                   VALUES (?, 'final', ?, ?, ?)""",
                (
                    "E.1_grezzo",
                    timestamp_now,
                    "Catalogo grezzo: deduplicated by case-insensitive",
                    json.dumps(e1_data.get("metadata", {}))
                )
            )
            version_e1 = cursor.lastrowid

            # Inserisci i nomi nel catalogo
            for i, item in enumerate(e1_data.get("catalogo", [])):
                cursor.execute(
                    """INSERT INTO catalog_snapshots
                       (version_id, logical_item_id, canonical_name, aka_list, frequency, metadata)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        version_e1,
                        f"e1_{i}",
                        item["canonical_name"],
                        json.dumps([item["original_name"]]),
                        item.get("frequency", 1),
                        json.dumps({"source": "fase_e_1"})
                    )
                )

        print(f"  ✅ Inseriti {len(e1_data.get('catalogo', []))} nomi grezzo")
    else:
        print(f"  ⚠️  {e1_path.name} non trovato, saltato")

    # --- E.2: Cluster di sinonimi ---
    e2_path = Path("data/fase_e_2_cluster_sinonimi.json")
    if e2_path.exists():
        print(f"E.2: Leggo {e2_path.name}...")
        with open(e2_path) as f:
            e2_data = json.load(f)

        if not args.dry_run:
            cursor.execute(
                """INSERT INTO catalog_versions (phase, status, created_at, description, stats)
                   VALUES (?, 'final', ?, ?, ?)""",
                (
                    "E.2_clustered",
                    timestamp_now,
                    "Cluster di sinonimi proposti",
                    json.dumps(e2_data.get("metadata", {}))
                )
            )
            version_e2 = cursor.lastrowid

            # Inserisci i cluster
            for cluster in e2_data.get("clusters", []):
                cursor.execute(
                    """INSERT INTO catalog_snapshots
                       (version_id, logical_item_id, canonical_name, aka_list, cluster_id,
                        confidence, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        version_e2,
                        f"e2_cluster_{cluster['id']}",
                        cluster.get("suggested_canonical", ""),
                        json.dumps(cluster.get("elements", [])),
                        cluster.get("id"),
                        cluster.get("min_similarity", 0),
                        json.dumps({
                            "automatic": cluster.get("automatic", False),
                            "decision": cluster.get("decision", "REVIEW")
                        })
                    )
                )

        print(f"  ✅ Inseriti {len(e2_data.get('clusters', []))} cluster")
    else:
        print(f"  ⚠️  {e2_path.name} non trovato, saltato")

    # --- E.3: Normalizzazione (validazioni sinonimi) ---
    e3_path = Path("data/fase_e_validazioni_sinonimi.json")
    if e3_path.exists():
        print(f"E.3: Leggo {e3_path.name}...")
        with open(e3_path) as f:
            e3_data = json.load(f)

        if not args.dry_run:
            cursor.execute(
                """INSERT INTO catalog_versions (phase, status, created_at, description, stats)
                   VALUES (?, 'final', ?, ?, ?)""",
                (
                    "E.3_canonical",
                    timestamp_now,
                    "Catalogo canonico: normalizzazione sinonimi applicate",
                    json.dumps({"total_decisions": len(e3_data)})
                )
            )
            version_e3 = cursor.lastrowid

            # Inserisci le decisioni di normalizzazione
            for key, decision in e3_data.items():
                cursor.execute(
                    """INSERT INTO catalog_decisions
                       (version_id, decision_type, target_type, target_id, decision_value,
                        metadata, approved_by, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        version_e3,
                        "CLUSTER_MERGE" if decision.get("decision", "").startswith("MERGE") else "SKIP",
                        "cluster",
                        decision.get("cluster", 0),
                        decision.get("decision", "REVIEW"),
                        json.dumps({"elements": decision.get("elements", [])}),
                        decision.get("approved_by", "auto"),
                        timestamp_now
                    )
                )

        print(f"  ✅ Inserite {len(e3_data)} decisioni di normalizzazione")
    else:
        print(f"  ⚠️  {e3_path.name} non trovato, saltato")

    # --- E.4–E.5: Split proposal e decisioni ---
    e4_path = Path("data/fase_e_4_proponi_spezzatura.json")
    if e4_path.exists():
        print(f"E.4: Leggo {e4_path.name}...")
        with open(e4_path) as f:
            e4_data = json.load(f)

        if not args.dry_run:
            cursor.execute(
                """INSERT INTO catalog_versions (phase, status, created_at, description, stats)
                   VALUES (?, 'final', ?, ?, ?)""",
                (
                    "E.4_split_proposed",
                    timestamp_now,
                    "Proposte di spezzatura fused",
                    json.dumps(e4_data.get("metadata", {}))
                )
            )
            version_e4 = cursor.lastrowid

        print(f"  ✅ Registrata versione E.4")
    else:
        print(f"  ⚠️  {e4_path.name} non trovato, saltato")

    # --- Decisioni E.5: Split applicate ---
    e5_path = Path("data/fase_e_validazioni_fused.json")
    if e5_path.exists():
        print(f"E.5: Leggo {e5_path.name}...")
        with open(e5_path) as f:
            e5_data = json.load(f)

        if not args.dry_run:
            cursor.execute(
                """INSERT INTO catalog_versions (phase, status, created_at, description, stats)
                   VALUES (?, 'final', ?, ?, ?)""",
                (
                    "E.5_split_applied",
                    timestamp_now,
                    "Spezzature fused applicate",
                    json.dumps({"total_fused": len(e5_data)})
                )
            )
            version_e5 = cursor.lastrowid

            # Inserisci le decisioni di split
            for key, decision in e5_data.items():
                cursor.execute(
                    """INSERT INTO catalog_decisions
                       (version_id, decision_type, target_type, target_id, decision_value,
                        metadata, approved_by, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        version_e5,
                        "FUSED_SPLIT",
                        "receipt_line",
                        decision.get("receipt_line_id", 0),
                        decision.get("decision", "CANNOT_SPLIT"),
                        json.dumps({"matches": decision.get("matches", [])}),
                        decision.get("approved_by", "auto"),
                        timestamp_now
                    )
                )

        print(f"  ✅ Inserite {len(e5_data)} decisioni di split")
    else:
        print(f"  ⚠️  {e5_path.name} non trovato, saltato")

    if not args.dry_run:
        conn.commit()
        print(f"\n✅ Migrazione completata nel database\n")

        # Verifica
        cursor.execute("SELECT COUNT(*) as n FROM catalog_versions")
        versions = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) as n FROM catalog_snapshots")
        snapshots = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) as n FROM catalog_decisions")
        decisions = cursor.fetchone()[0]

        print(f"Database statistics:")
        print(f"  Versioni catalogo: {versions}")
        print(f"  Snapshot prodotti: {snapshots}")
        print(f"  Decisioni audit trail: {decisions}\n")
    else:
        print(f"\n(dry-run: nessun dato inserito)\n")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
