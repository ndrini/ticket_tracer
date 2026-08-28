"""
Il report che decide se collegare `addendi.py` a `prodotti()`.

NON MODIFICA NIENTE. Misura e basta: mette a confronto, sui 218 scontrini
strutturati, gli addendi che la geometria riconosce e i prodotti che il
percorso attuale ha estratto. Chi legge decide.

PERCHE' UN REPORT PRIMA DEL COLLEGAMENTO. `addendi.py` propone di cambiare la
definizione di prodotto: non piu' un'euristica sul NOME ma la POSIZIONE
dell'importo nella colonna che somma. Il cambio tocca la semantica dei dati,
e i tre agenti consultati il 2026-08-28 hanno posto la stessa condizione:
misurare in sola lettura prima di collegare. Le loro obiezioni, che questo
script traduce in numeri:

  1. CIRCOLARITA' — la colonna dei prezzi e' dedotta dagli stessi importi che
     poi si vogliono selezionare. Se lo scontrino ha poche righe o l'OCR e'
     sporco, la colonna puo' essere un artefatto. Si misura guardando quanti
     scontrini producono una colonna e quanto e' popolata.
  2. FALSI ADDENDI — IVA, sconti, subtotali allineati alla stessa colonna.
     Si misura col giudice aritmetico: se la somma degli addendi supera il
     totale, stiamo raccogliendo di troppo.
  3. LAYOUT A PIU' COLONNE (prezzo unitario e importo di riga) — sommare la
     colonna sbagliata conta due volte.

LA METRICA SI DICHIARA PRIMA, e per questo report e':

  principale  quanti scontrini avrebbero la somma degli ADDENDI uguale al
              totale stampato, contro i 62/218 di oggi;
  guardia 1   i 62 VALIDO di oggi devono restare quadrati anche con gli
              addendi: un metodo che ne rompe di piu' di quanti ne aggiusta
              e' un peggioramento anche se il totale sale;
  guardia 2   gli addendi non devono eccedere il totale piu' spesso di oggi;
  guardia 3   gli scontrini senza colonna riconosciuta vanno CONTATI, non
              nascosti: sono i casi in cui il metodo geometrico non si
              applica, e restano da servire in un altro modo.

    uv run python scripts/report_addendi.py
    uv run python scripts/report_addendi.py --dettaglio PRODOTTI_ASSENTI
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.getcwd())

from app.etl.addendi import addendi, confine_somma, e_sconto  # noqa: E402
from app.etl.geometria import altezza_riga, colonna_dei_prezzi  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ESTRATTI = ROOT / "data" / "estratti"
STRUTTURATI = ROOT / "data" / "strutturati"

# Same tolerance the arithmetic judge uses, so the two are comparable.
TOLLERANZA = 0.02


def carica():
    """Gli scontrini strutturati, con accanto le righe OCR da cui vengono."""
    estratti = {}
    for p in glob.glob(str(ESTRATTI / "*.json")):
        d = json.load(open(p))
        estratti[d["sha256"]] = d["righe_ocr"]

    casi = []
    for p in sorted(glob.glob(str(STRUTTURATI / "*.json"))):
        d = json.load(open(p))
        righe = estratti.get(d["sha256"])
        if righe is not None:
            casi.append((d, righe))
    return casi


def quadra(somma, totale):
    """Il giudice aritmetico, identico a quello della fase B."""
    if totale is None or somma is None:
        return False
    return abs(somma - totale) <= TOLLERANZA


def analizza(strutturato, righe_ocr):
    """Cosa direbbe la geometria su questo scontrino, senza cambiarlo."""
    totale = strutturato.get("total")
    trovati = addendi(righe_ocr)
    somma = round(sum(v for v, _ in trovati), 2) if trovati else None

    altezza = altezza_riga(righe_ocr) if righe_ocr else None
    colonna = colonna_dei_prezzi(righe_ocr, altezza) if righe_ocr else None

    return {
        "sha": strutturato["sha256"][:12],
        "esito_oggi": strutturato["esito"],
        "totale": totale,
        "somma_oggi": strutturato.get("somma_prodotti"),
        "n_prodotti_oggi": len(strutturato.get("items") or []),
        "somma_addendi": somma,
        "n_addendi": len(trovati),
        "n_sconti": sum(1 for v, _ in trovati if e_sconto(v)),
        "colonna": colonna,
        "quadra_oggi": quadra(strutturato.get("somma_prodotti"), totale),
        "quadra_addendi": quadra(somma, totale),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dettaglio", help="elenca i casi di questo esito")
    args = ap.parse_args()

    casi = carica()
    righe = [analizza(d, r) for d, r in casi]
    n = len(righe)
    print(f"scontrini confrontabili: {n}\n")

    # --- guardia 3: dove il metodo geometrico non si applica affatto ---
    senza_colonna = [r for r in righe if r["colonna"] is None]
    senza_addendi = [r for r in righe if r["n_addendi"] == 0]
    print("APPLICABILITA'  (guardia 3)")
    print(f"  senza colonna dei prezzi riconosciuta: {len(senza_colonna):3d}"
          f"  ({100*len(senza_colonna)//n}%)")
    print(f"  con colonna ma zero addendi:           "
          f"{len(senza_addendi) - len(senza_colonna):3d}")
    print(f"  utilizzabili:                          "
          f"{n - len(senza_addendi):3d}  ({100*(n-len(senza_addendi))//n}%)")

    # --- metrica principale ---
    q_oggi = sum(1 for r in righe if r["quadra_oggi"])
    q_add = sum(1 for r in righe if r["quadra_addendi"])
    print(f"\nMETRICA PRINCIPALE  scontrini che quadrano")
    print(f"  oggi (prodotti estratti):  {q_oggi:3d}/{n}  ({100*q_oggi//n}%)")
    print(f"  con gli addendi geometrici:{q_add:3d}/{n}  ({100*q_add//n}%)"
          f"   {q_add - q_oggi:+d}")

    # --- guardia 1: chi quadrava e smetterebbe ---
    rotti = [r for r in righe if r["quadra_oggi"] and not r["quadra_addendi"]]
    nuovi = [r for r in righe if not r["quadra_oggi"] and r["quadra_addendi"]]
    print(f"\nGUARDIA 1  quadravano e NON quadrerebbero piu': {len(rotti)}")
    for r in rotti[:12]:
        print(f"    {r['sha']}  totale {r['totale']}  "
              f"oggi {r['somma_oggi']} ({r['n_prodotti_oggi']} prod)  "
              f"addendi {r['somma_addendi']} ({r['n_addendi']})")
    if len(rotti) > 12:
        print(f"    ... e altri {len(rotti)-12}")

    print(f"\n           non quadravano e quadrerebbero: {len(nuovi)}")
    for r in nuovi[:12]:
        print(f"    {r['sha']}  [{r['esito_oggi']}]  totale {r['totale']}  "
              f"oggi {r['somma_oggi']}  addendi {r['somma_addendi']} "
              f"({r['n_addendi']})")
    if len(nuovi) > 12:
        print(f"    ... e altri {len(nuovi)-12}")

    # --- guardia 2: il verso dello scarto, che e' cio' che conta ---
    def verso(r, chiave):
        s, t = r[chiave], r["totale"]
        if t is None or s is None:
            return "SENZA_TOTALE"
        if abs(s - t) <= TOLLERANZA:
            return "QUADRA"
        return "ECCESSO" if s > t else "DIFETTO"

    print("\nGUARDIA 2  il verso dello scarto")
    v_oggi = Counter(verso(r, "somma_oggi") for r in righe)
    v_add = Counter(verso(r, "somma_addendi") for r in righe)
    for k in ("QUADRA", "DIFETTO", "ECCESSO", "SENZA_TOTALE"):
        print(f"  {k:14s} {v_oggi[k]:3d} -> {v_add[k]:3d}"
              f"   {v_add[k]-v_oggi[k]:+d}")

    # --- il taglio che conta: cosa succede sui PRODOTTI_ASSENTI ---
    print("\nPER ESITO DI OGGI  (quanti quadrerebbero con gli addendi)")
    per_esito = {}
    for r in righe:
        per_esito.setdefault(r["esito_oggi"], []).append(r)
    for esito in sorted(per_esito):
        g = per_esito[esito]
        k = sum(1 for r in g if r["quadra_addendi"])
        senza = sum(1 for r in g if r["n_addendi"] == 0)
        print(f"  {esito:18s} {len(g):3d}  quadrerebbero {k:3d}"
              f"   senza addendi {senza:3d}")

    # --- perche' le regressioni: le cause, non solo il conteggio ---
    # Una guardia che conta senza spiegare non dice se il difetto sia
    # riparabile. Le tre cause qui sotto vengono dalla lettura a mano dei casi
    # rotti, e sono misurate su tutti gli scontrini, non sui casi che le hanno
    # suggerite.
    tot_dentro = doppio = confine_aperto = stretta = 0
    for r, (d, ocr) in zip(righe, casi):
        alt = altezza_riga(ocr) if ocr else None
        if ocr and confine_somma(ocr, alt) == float("inf"):
            confine_aperto += 1
        t_, s_ = r["totale"], r["somma_addendi"]
        if t_ is None or s_ is None:
            continue
        trovati = addendi(ocr)
        if len(trovati) > 1 and any(abs(v - t_) <= TOLLERANZA for v, _ in trovati):
            tot_dentro += 1
        if abs(s_ - 2 * t_) <= TOLLERANZA:
            doppio += 1
        if r["n_addendi"] == 1 and r["n_prodotti_oggi"] > 1:
            stretta += 1

    print("\nPERCHE' LE REGRESSIONI  (cause misurate su tutti gli scontrini)")
    print(f"  A. il TOTALE stampato raccolto come addendo:      {tot_dentro:3d}")
    print(f"     di cui la somma e' ESATTAMENTE il doppio:      {doppio:3d}")
    print(f"  B. nessun riepilogo trovato (confine = infinito): {confine_aperto:3d}")
    print(f"  C. un solo addendo ma piu' prodotti estratti:     {stretta:3d}")
    print("     A e B sono difetti di CONFINE: il riepilogo non viene")
    print("     riconosciuto e il totale finisce fra gli addendi.")
    print("     C e' una colonna troppo stretta, che perde gli altri prezzi.")

    if args.dettaglio:
        print(f"\nDETTAGLIO  {args.dettaglio}")
        for r in per_esito.get(args.dettaglio, []):
            print(f"  {r['sha']}  totale {r['totale']}  "
                  f"oggi {r['somma_oggi']} ({r['n_prodotti_oggi']} prod)  "
                  f"addendi {r['somma_addendi']} ({r['n_addendi']}, "
                  f"{r['n_sconti']} sconti)  "
                  f"{'QUADRA' if r['quadra_addendi'] else ''}")


if __name__ == "__main__":
    main()
