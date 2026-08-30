"""Confronta la lettura del VLM con quella geometrica, sul campione giudicato.

    uv run python scripts/confronta_vlm_geometrico.py
    uv run python scripts/confronta_vlm_geometrico.py --risultati data/kaggle_output/vlm_risultati.json

La metrica e' dichiarata in docs/122_metrica_confronto_vlm.md, PRIMA di aver
visto questi numeri:

    quadra(metodo) = |somma_righe(metodo) - totale_stampato| <= 0,02 EUR

Il totale stampato fa da giudice terzo: non e' stato letto da nessuno dei due
estrattori per la stessa via dei prodotti. E' una misura debole - si puo'
quadrare per compensazione di errori - ma e' automatica e non richiede di
trascrivere a mano ogni riga.

NON DECIDE DA SOLO. Stampa anche le metriche di guardia, perche' una metrica che
sale non basta ad assolvere: un VLM che quadra piu' spesso ma inventa prodotti
non e' un miglioramento.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Two cents: enough to absorb rounding, not enough to hide a wrong line.
TOLLERANZA = 0.02

# Scontrini in cui la revisione umana dice che il TOTALE STAMPATO e' stato letto
# male: e' il contante versato, un subtotale, o un numero preso altrove.
# MISURATO il 2026-08-30: 7 su 28, il 25% del campione. Le note:
#   #113 "totale stampato 20,00 EUR, sbagliato, e' quanto ho pagato in contanti"
#   #22  "letto male lo stampato (efectivo=contanti, invece che totale)"
#   #54  "ancora errore sul totale stampato (ma somma righe e' giusto!!)"
#   #128 "totale stampato scritto 'total (EUR)' letto male"
#
# Su questi il giudice terzo e' sbagliato, e la metrica PENALIZZA l'estrattore
# che ha letto bene i prodotti. Il conteggio si riporta due volte: su tutti e
# sul sottoinsieme attendibile. La metrica dichiarata resta quella su tutti -
# cambiarla dopo aver visto i dati e' precisamente cio' che il metodo vieta.
TOTALE_INATTENDIBILE = {22, 23, 54, 56, 75, 113, 128}


def somma(prodotti) -> float | None:
    if not prodotti:
        return None
    totale = 0.0
    for p in prodotti:
        prezzo = p.get("price", p.get("prezzo"))
        if prezzo is None:
            continue
        try:
            totale += float(prezzo)
        except (TypeError, ValueError):
            continue
    return round(totale, 2)


def quadra(valore, dichiarato) -> bool:
    return (valore is not None and dichiarato is not None
            and abs(valore - dichiarato) <= TOLLERANZA)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=ROOT / "data" / "spese.db")
    p.add_argument("--risultati", type=Path,
                   default=ROOT / "data" / "kaggle_output" / "vlm_risultati.json")
    args = p.parse_args(argv)

    if not args.risultati.is_file():
        raise SystemExit(
            f"non trovo {args.risultati}.\n"
            "Scaricalo con: uv run python scripts/kaggle_lancia_kernel.py "
            "--lavoro vlm --scarica")

    # Indicizzati per sha256, non per receipt_id: il kernel su Kaggle vede solo
    # i nomi dei file (che sono lo sha256), perche' la piattaforma non serve
    # l'indice.json caricato insieme alle immagini. Lo sha256 e' comunque la
    # chiave di tutta la pipeline.
    with open(args.risultati, encoding="utf-8") as f:
        vlm = {r["sha256"]: r for r in json.load(f)}

    conn = sqlite3.connect(args.db)
    # La somma si ricalcola dalle righe SALVATE, non si legge da
    # receipts.total_computed. MISURATO il 2026-08-30: i due divergono in 12
    # casi su 25, perche' total_computed e' la somma di tutti i prodotti trovati
    # in fase C mentre nel database entrano solo quelli con un NOME - e il
    # geometrico lascia il nome vuoto molto spesso (9 righe su 12 nello
    # scontrino #57, prezzi corretti e nomi assenti; fase_d_carica_db.py le
    # scarta in silenzio).
    #
    # Dare credito al geometrico per righe che non sono nel database
    # significherebbe misurare dati che il progetto non possiede.
    righe = conn.execute("""
        SELECT r.id, r.total_declared,
               (SELECT ROUND(SUM(l.total_price), 2) FROM receipt_lines l
                WHERE l.receipt_id = r.id),
               q.review_notes,
               (SELECT COUNT(*) FROM receipt_lines l WHERE l.receipt_id = r.id),
               r.image_sha256
        FROM manual_review_queue q JOIN receipts r ON r.id = q.receipt_id
        WHERE q.reason LIKE 'taglio:ok%' ORDER BY r.id""").fetchall()

    geo_ok = vlm_ok = 0
    senza_totale = 0
    vuoti_vlm = illeggibili = 0
    dettaglio = []

    for rid, dichiarato, calcolato, nota, n_righe_geo, sha in righe:
        v = vlm.get(sha)
        prodotti_vlm = (v or {}).get("prodotti")
        somma_vlm = somma(prodotti_vlm)

        if v and v.get("stato") == "json_illeggibile":
            illeggibili += 1
        if v and prodotti_vlm == []:
            vuoti_vlm += 1

        if dichiarato is None:
            senza_totale += 1
            continue

        g = quadra(calcolato, dichiarato)
        w = quadra(somma_vlm, dichiarato)
        geo_ok += g
        vlm_ok += w
        dettaglio.append((rid, dichiarato, calcolato, somma_vlm, g, w,
                          n_righe_geo, len(prodotti_vlm or []), nota))

    n = len(dettaglio)
    if not n:
        raise SystemExit("nessuno scontrino confrontabile: manca il totale stampato.")

    print(f"CAMPIONE: {n} scontrini col taglio giudicato buono e un totale stampato")
    if senza_totale:
        print(f"  ({senza_totale} esclusi: nessun totale stampato, manca il giudice terzo)")
    print()
    print("METRICA PRINCIPALE - quadrano col totale stampato (+/- 0,02 EUR)")
    print(f"  geometrico: {geo_ok:>3} / {n}  ({geo_ok / n * 100:.0f}%)")
    print(f"  VLM:        {vlm_ok:>3} / {n}  ({vlm_ok / n * 100:.0f}%)")

    puliti = [d for d in dettaglio if d[0] not in TOTALE_INATTENDIBILE]
    if puliti:
        g2 = sum(1 for d in puliti if d[4])
        v2 = sum(1 for d in puliti if d[5])
        m = len(puliti)
        print(f"\n  escludendo i {n - m} col totale stampato letto male "
              f"(la revisione umana lo dichiara):")
        print(f"    geometrico: {g2:>3} / {m}  ({g2 / m * 100:.0f}%)")
        print(f"    VLM:        {v2:>3} / {m}  ({v2 / m * 100:.0f}%)")

    differenza = (vlm_ok - geo_ok) / n * 100
    # Declared before measuring: with ~28 receipts the margin of error is about
    # 18 points, so a smaller gap is not a result.
    margine = 18
    print(f"\n  differenza: {differenza:+.0f} punti", end="")
    if abs(differenza) < margine:
        print(f" - SOTTO il margine d'errore (+/-{margine}): NON e' un risultato.")
    else:
        print(f" - sopra il margine d'errore (+/-{margine}).")

    print("\nMETRICHE DI GUARDIA")
    print(f"  VLM senza prodotti:      {vuoti_vlm}")
    print(f"  VLM json illeggibile:    {illeggibili}")

    persi = sum(1 for d in dettaglio if d[6] > 0 and d[7] == 0)
    print(f"  righe perse dal VLM:     {persi}  (il geometrico ne trovava, il VLM no)")

    print("\nDETTAGLIO")
    print(f"  {'id':<5} {'stampato':>9} {'geom':>9} {'vlm':>9}  {'righe g/v':>9}  esito")
    for rid, dic, cal, sv, g, w, ng, nv, nota in dettaglio:
        segno = "geom" if g and not w else "VLM" if w and not g else \
                "entrambi" if g and w else "nessuno"
        print(f"  #{rid:<4} {dic:>9.2f} "
              f"{(f'{cal:.2f}' if cal is not None else '-'):>9} "
              f"{(f'{sv:.2f}' if sv is not None else '-'):>9}  "
              f"{ng:>4}/{nv:<4}  {segno}")

    print("\nUna metrica che sale non basta ad assolvere: guarda i nomi dei prodotti "
          "letti dal VLM\nprima di adottarlo (vedi il campo risposta_grezza).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
