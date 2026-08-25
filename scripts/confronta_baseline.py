"""
Confronta l'estrazione di oggi con una baseline congelata.

PERCHE'. Una metrica che sale non basta ad assolvere: va guardato cosa sta
rompendo. Questo script mette in fila la metrica principale (quanti scontrini
quadrano) e le metriche di guardia dichiarate PRIMA della misura, cosi' un
miglioramento che rompe qualcosa d'altro si vede invece di nascondersi nella
media.

Le guardie sono quelle chieste dagli agenti consultati sul piano della
ricucitura:

  1. i VALIDO della baseline devono restare VALIDO — e devono estrarre GLI
     STESSI PRODOTTI, non solo continuare a quadrare per un'altra strada;
  2. SOMMA_IN_ECCESSO non deve crescere: sarebbe il segno che stiamo
     raccogliendo importi che prodotti non sono (IVA, resto, sconti);
  3. i nuovi VALIDO vanno elencati, perche' uno che quadra per caso e' peggio
     di uno che non quadra: va guardato a mano.

    uv run python scripts/confronta_baseline.py
    uv run python scripts/confronta_baseline.py --baseline private/regressione/altra.json
"""
import argparse
import glob
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "private" / "regressione" / "baseline_20260824.json"
STRUTTURATI = ROOT / "data" / "strutturati"


def carica_oggi(cartella):
    """Lo stato attuale, nella stessa forma della baseline."""
    stato = {}
    for percorso in sorted(glob.glob(str(cartella / "*.json"))):
        d = json.load(open(percorso))
        # Le tuple tornano dal JSON come liste: si normalizza a lista anche qui,
        # altrimenti il confronto con la baseline fallisce SEMPRE. Trovato dal
        # controllo di sanita': confrontare i dati con se stessi dava 62
        # scontrini "con prodotti diversi".
        stato[d["sha256"]] = {
            "esito": d["esito"],
            "total": d.get("total"),
            "somma": d.get("somma_prodotti"),
            "scarto": d.get("scarto"),
            "items": sorted([[i.get("name"), i.get("price")]
                             for i in (d.get("items") or [])],
                            key=lambda v: (str(v[0]), v[1] or 0)),
        }
    return stato


def confronta(base, oggi):
    """Stampa metrica principale e guardie. Restituisce True se le guardie tengono."""
    comuni = sorted(set(base) & set(oggi))
    print(f"scontrini confrontabili: {len(comuni)} "
          f"(baseline {len(base)}, oggi {len(oggi)})")

    prima = Counter(base[h]["esito"] for h in comuni)
    dopo = Counter(oggi[h]["esito"] for h in comuni)

    print("\nESITI")
    for esito in sorted(set(prima) | set(dopo)):
        a, b = prima[esito], dopo[esito]
        segno = f"{b - a:+d}" if a != b else "="
        print(f"  {esito:<18} {a:4d} -> {b:4d}   {segno}")

    # Metrica principale: quanti quadrano.
    a, b = prima["VALIDO"], dopo["VALIDO"]
    print(f"\nMETRICA PRINCIPALE  scontrini che quadrano: "
          f"{a}/{len(comuni)} ({100*a/len(comuni):.0f}%) -> "
          f"{b}/{len(comuni)} ({100*b/len(comuni):.0f}%)   {b-a:+d}")

    tiene = True

    # Guardia 1: i VALIDO non devono rompersi, e devono dare gli stessi prodotti.
    rotti = [h for h in comuni
             if base[h]["esito"] == "VALIDO" and oggi[h]["esito"] != "VALIDO"]
    mutati = [h for h in comuni
              if base[h]["esito"] == "VALIDO" and oggi[h]["esito"] == "VALIDO"
              and base[h]["items"] != oggi[h]["items"]]
    print(f"\nGUARDIA 1  VALIDO che hanno smesso di quadrare: {len(rotti)}")
    for h in rotti[:10]:
        print(f"    {h[:12]} -> {oggi[h]['esito']} "
              f"(somma {oggi[h]['somma']}, totale {oggi[h]['total']})")
    print(f"           VALIDO che quadrano ma con PRODOTTI DIVERSI: {len(mutati)}")
    for h in mutati[:10]:
        print(f"    {h[:12]} {len(base[h]['items'])} -> {len(oggi[h]['items'])} prodotti")
    if rotti:
        tiene = False

    # Guardia 2: raccogliere importi che non sono prodotti si vede qui.
    a, b = prima["SOMMA_IN_ECCESSO"], dopo["SOMMA_IN_ECCESSO"]
    print(f"\nGUARDIA 2  SOMMA_IN_ECCESSO: {a} -> {b}   {b-a:+d}")
    if b > a:
        print("    ⚠️ cresciuta: forse stiamo sommando IVA, resto o sconti")
        tiene = False

    # Guardia 3: i nuovi VALIDO vanno guardati a mano, non festeggiati.
    nuovi = [h for h in comuni
             if base[h]["esito"] != "VALIDO" and oggi[h]["esito"] == "VALIDO"]
    print(f"\nGUARDIA 3  nuovi VALIDO da controllare a mano: {len(nuovi)}")
    for h in nuovi:
        print(f"    {h[:12]}  era {base[h]['esito']:<18} "
              f"ora {len(oggi[h]['items'])} prodotti, totale {oggi[h]['total']}")

    return tiene


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", default=str(BASELINE))
    p.add_argument("--strutturati", default=str(STRUTTURATI))
    args = p.parse_args()

    base = json.load(open(args.baseline))
    oggi = carica_oggi(Path(args.strutturati))
    tiene = confronta(base, oggi)
    print("\n" + ("✅ le guardie tengono" if tiene else "⛔️ una guardia e' saltata"))


if __name__ == "__main__":
    main()
