"""
Fase C geometrica — estrae prodotti usando solo la posizione degli importi.

La geometria dice QUALI importi entrano nella somma (gli addendi).
La posizione dei nomi ACCANTO a quegli importi dice COME si chiamano.

Scrive in data/strutturati_geometrici/<hash>.json, separato dai dati LLM,
per mantenere la baseline congelata e tracciare la provenienza nel database.

Uso:
    uv run python scripts/fase_c_geometrica.py
    uv run python scripts/fase_c_geometrica.py --limite 20
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from app.etl.addendi import addendi, TOLLERANZA_SOMMA  # noqa: E402
from app.etl.geometria import altezza_riga, centro_x, centro_y, colonna_dei_prezzi  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ESTRATTI = ROOT / "data" / "estratti"
STRUTTURATI = ROOT / "data" / "strutturati"
STRUTTURATI_GEOMETRICI = ROOT / "data" / "strutturati_geometrici"


import re
HA_NOME = re.compile(r"[A-Za-zÀ-ÿ]{3}")
SOSPETTO_FUSIONE = 30
PREFISSO_NUMERICO = re.compile(r"^[\d\s.,x×*/€-]+", re.I)
IMPORTI_IN_CODA = re.compile(r"(\s*-?\d{1,4}[.,]\d{2}\s*(?:€|EUR)?)+$", re.I)


def nome_per_addendo(righe_ocr, y_addendo, x_addendo, altezza):
    """
    Il nome che sta a SINISTRA dell'addendo, sulla sua stessa riga fisica.
    """
    pezzi = []
    for r in righe_ocr:
        y, x = centro_y(r["box"]), centro_x(r["box"])
        if abs(y - y_addendo) >= 0.5 * altezza:
            continue
        if x >= x_addendo:
            continue
        pezzi.append((x, r["testo"]))
    if not pezzi:
        return None
    testo = " ".join(t for _, t in sorted(pezzi))
    testo = IMPORTI_IN_CODA.sub("", testo)
    testo = PREFISSO_NUMERICO.sub("", testo).strip(" |×x*-–=.,:")
    return testo.strip() or None


def qualita_nome(nome):
    """
    Categoria di qualità del nome rilevato.

    - complete: il nome c'è ed è credibile
    - fused: il nome ha ingoiato frammenti di un'altra riga
    - incomplete: nessun nome trovato (None)
    """
    if nome is None:
        return "incomplete"
    if len(nome) < 3 or not HA_NOME.search(nome):
        return "incomplete"
    if len(nome) > SOSPETTO_FUSIONE:
        return "fused"
    return "complete"


def estrai_geometrico(righe_ocr, sha256, shop_name, total, date, foto_origine):
    """
    Estrae un scontrino usando il metodo geometrico.

    Restituisce un dict strutturato per la serializzazione,
    oppure None se non c'è abbastanza per procedere.
    """
    if not righe_ocr:
        return None

    altezza = altezza_riga(righe_ocr)
    colonna = colonna_dei_prezzi(righe_ocr, altezza)
    if colonna is None or altezza is None:
        return None

    x_col = colonna[1]
    trovati = addendi(righe_ocr)

    if not trovati:
        return None

    somma = 0.0
    items = []
    for v, y in trovati:
        nome = nome_per_addendo(righe_ocr, y, x_col, altezza)
        quality = qualita_nome(nome)
        somma += v

        items.append({
            "name": nome if nome is not None else "",
            "price": round(v, 2),
            "name_quality": quality
        })

    somma = round(somma, 2)

    esito = None
    scarto = None
    if total is not None:
        scarto = round(somma - total, 2)
        if abs(scarto) <= TOLLERANZA_SOMMA:
            esito = "VALIDO"
        elif scarto < 0:
            esito = "SOMMA_IN_DIFETTO"
        else:
            esito = "SOMMA_IN_ECCESSO"
    else:
        esito = "TOTALE_ASSENTE"
        scarto = None

    return {
        "sha256": sha256,
        "foto_origine": foto_origine,
        "shop_name": shop_name,
        "date": date,
        "total": total,
        "items": items,
        "esito": esito,
        "somma_prodotti": somma,
        "scarto": scarto,
        "elaborato_il": None
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None,
                    help="processa solo i primi N scontrini")
    args = ap.parse_args(argv)

    STRUTTURATI_GEOMETRICI.mkdir(parents=True, exist_ok=True)

    # Carica i metadati dai file LLM (shop_name, total, date, foto_origine)
    metadati = {}
    for percorso in glob.glob(str(STRUTTURATI / "*.json")):
        with open(percorso) as fh:
            d = json.load(fh)
        metadati[d.get("sha256")] = {
            "shop_name": d.get("shop_name"),
            "total": d.get("total"),
            "date": d.get("date"),
            "foto_origine": d.get("foto_origine")
        }

    percorsi = sorted(glob.glob(str(ESTRATTI / "*.json")))
    if args.limite:
        percorsi = percorsi[:args.limite]
    if not percorsi:
        print(f"Nessuno scontrino in {ESTRATTI}/. Esegui prima la Fase C (LLM).")
        return 1

    print(f"Fase C geometrica — {len(percorsi)} scontrini\n")

    conteggi = {"elaborati": 0, "saltati": 0}
    for percorso in percorsi:
        with open(percorso) as fh:
            dati = json.load(fh)

        sha256 = dati.get("sha256")
        if not sha256:
            conteggi["saltati"] += 1
            continue

        meta = metadati.get(sha256, {})
        risultato = estrai_geometrico(
            dati.get("righe_ocr", []),
            sha256,
            meta.get("shop_name"),
            meta.get("total"),
            meta.get("date"),
            meta.get("foto_origine")
        )

        if risultato is None:
            conteggi["saltati"] += 1
            continue

        output_path = STRUTTURATI_GEOMETRICI / f"{sha256}.json"
        with open(output_path, "w") as fh:
            json.dump(risultato, fh, indent=2)

        conteggi["elaborati"] += 1

    print(f"\n  elaborati:  {conteggi['elaborati']}")
    print(f"  saltati:    {conteggi['saltati']}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
