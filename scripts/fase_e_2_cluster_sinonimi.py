"""
Fase E.2 — Identifica cluster di sinonimi nel catalogo grezzo.

Legge il catalogo grezzo da E.1, applica euristiche di similarità testuale
per raggruppare probabili sinonimi (mela, mele, MELA, etc.) e propone merge.

Genera un report JSON con cluster marcati come:
  ✓ Automatico (alta confidenza, es. solo case differences)
  ❓ Manuale (richiede validazione umana)

Uso:
    uv run python scripts/fase_e_2_cluster_sinonimi.py
    uv run python scripts/fase_e_2_cluster_sinonimi.py --threshold 0.8
"""
import argparse
import json
import sys
from difflib import SequenceMatcher
from collections import defaultdict


def similarity(a, b):
    """Similarità testuale fra due stringhe (0-1)."""
    return SequenceMatcher(None, a, b).ratio()


def cluster_by_similarity(names, threshold=0.85):
    """
    Raggruppa nomi per similarità.

    Algoritmo greedy: per ogni nome, se non è già in un cluster, cerca
    il cluster con il miglior match (similarità > threshold). Se trova,
    lo aggiunge; altrimenti crea un nuovo cluster.
    """
    clusters = []
    assigned = set()

    for name in sorted(names, key=len):  # Elabora i nomi corti prima
        if name in assigned:
            continue

        # Cerca il cluster più simile
        best_cluster = None
        best_sim = 0
        for cluster in clusters:
            for member in cluster:
                sim = similarity(name, member)
                if sim > best_sim and sim > threshold:
                    best_sim = sim
                    best_cluster = cluster
                    break

        if best_cluster is not None:
            best_cluster.append(name)
            assigned.add(name)
        else:
            clusters.append([name])
            assigned.add(name)

    return clusters


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/fase_e_1_catalogo_grezzo.json")
    parser.add_argument("--threshold", type=float, default=0.85)
    args = parser.parse_args(argv)

    with open(args.input) as f:
        data = json.load(f)

    catalogo = data["catalogo"]
    names = [item["canonical_name"] for item in catalogo]

    print(f"\nClustering {len(names)} nomi con threshold={args.threshold}\n")

    clusters = cluster_by_similarity(names, args.threshold)

    # Filtra i cluster: teniamo solo quelli con 2+ elementi
    multi_clusters = [c for c in clusters if len(c) > 1]
    single_clusters = [c for c in clusters if len(c) == 1]

    print(f"Cluster trovati: {len(clusters)}")
    print(f"  Con 2+ elementi: {len(multi_clusters)} (candidati per merge)")
    print(f"  Singoletti: {len(single_clusters)} (no merge)\n")

    # Crea il report con proposte di merge
    report = {
        "metadata": {
            "total_clusters": len(clusters),
            "multi_element_clusters": len(multi_clusters),
            "source": args.input,
            "phase": "E.2 — Cluster di sinonimi"
        },
        "clusters": []
    }

    for i, cluster in enumerate(multi_clusters):
        # Ordina per lunghezza decrescente (il nome più lungo è probabile il display name)
        sorted_cluster = sorted(cluster, key=len, reverse=True)
        canonical = sorted_cluster[0]  # Suggerisci il più lungo come canonico

        # Misura coerenza interna del cluster (similarità minima fra tutti i paia)
        min_sim = 1.0
        for j, name1 in enumerate(sorted_cluster):
            for name2 in sorted_cluster[j+1:]:
                sim = similarity(name1, name2)
                if sim < min_sim:
                    min_sim = sim

        # Automatico se:
        # - cluster di 2-3 elementi
        # - similarità minima > 0.9 (solo case/whitespace differences)
        is_automatic = (
            len(cluster) <= 3 and
            min_sim > 0.90
        )

        report["clusters"].append({
            "id": i + 1,
            "elements": sorted_cluster,
            "suggested_canonical": canonical,
            "min_similarity": min_sim,
            "automatic": is_automatic,
            "decision": "MERGE" if is_automatic else "REVIEW"
        })

    # Ordina per numero di elementi (cluster più grandi primo)
    report["clusters"].sort(key=lambda x: -len(x["elements"]))

    # Salva il report
    output_path = "data/fase_e_2_cluster_sinonimi.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Report salvato: {output_path}\n")

    # Mostra i cluster automatici
    auto_clusters = [c for c in report["clusters"] if c["automatic"]]
    print(f"Cluster AUTOMATICI ({len(auto_clusters)} da mergiare):\n")
    for cluster in auto_clusters[:10]:
        print(f"  Cluster {cluster['id']}: {cluster['elements']}")
        print(f"    → canonico suggerito: '{cluster['suggested_canonical']}'")
        print()

    if len(auto_clusters) > 10:
        print(f"  ... ({len(auto_clusters) - 10} altri cluster automatici)\n")

    # Mostra i cluster da rivedere
    review_clusters = [c for c in report["clusters"] if not c["automatic"]]
    print(f"Cluster che RICHIEDONO REVISIONE ({len(review_clusters)}):\n")
    for cluster in review_clusters[:10]:
        print(f"  Cluster {cluster['id']}: {cluster['elements'][:5]}")
        print(f"    Min similarity: {cluster['min_similarity']:.2f}")
        print(f"    → canonico suggerito: '{cluster['suggested_canonical']}'")
        print()

    if len(review_clusters) > 10:
        print(f"  ... ({len(review_clusters) - 10} altri cluster da rivedere)\n")

    print(f"Prossimo passo: revisionare i cluster da review in {output_path}")
    print("Marca ogni cluster con 'decision': 'MERGE_A_<canonical>' oppure 'SKIP'")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
