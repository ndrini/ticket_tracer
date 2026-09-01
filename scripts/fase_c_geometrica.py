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
from app.etl.documento import tipo_documento  # noqa: E402
from app.etl.geometria import altezza_riga, centro_x, centro_y, colonna_dei_prezzi  # noqa: E402
from app.etl.nomi import nomi_di_uno_scontrino, qualita_nome  # noqa: E402
from app.etl.template_catena import ottieni_profilo_catena  # noqa: E402
from app.etl.totale import candidati_totale, trova_totale  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ESTRATTI = ROOT / "data" / "estratti"
STRUTTURATI = ROOT / "data" / "strutturati"
STRUTTURATI_GEOMETRICI = ROOT / "data" / "strutturati_geometrici"


import re
HA_NOME = re.compile(r"[A-Za-zÀ-ÿ]{3}")
SOSPETTO_FUSIONE = 30
PREFISSO_NUMERICO = re.compile(r"^[\d\s.,x×*/€-]+", re.I)
IMPORTI_IN_CODA = re.compile(r"(\s*-?\d{1,4}[.,]\d{2}\s*(?:€|EUR)?)+$", re.I)


def estrai_geometrico(righe_ocr, sha256, shop_name, total, date, foto_origine):
    """
    Estrae uno scontrino usando il metodo geometrico.

    Restituisce un dict strutturato per la serializzazione,
    oppure None se non c'è abbastanza per procedere.
    """
    if not righe_ocr:
        return None

    # Se il documento e' una ricevuta di pagamento POS pura (senza prodotti)
    tipo_doc = tipo_documento(righe_ocr)
    if tipo_doc == "PAGAMENTO_ELETTRONICO":
        importi = [float(imp.replace(",", ".")) for imp in re.findall(r"\d+[.,]\d{2}", " ".join(r.get("testo", "") for r in righe_ocr))]
        tot_pos = max(importi) if importi else total
        return {
            "sha256": sha256,
            "foto_origine": foto_origine,
            "shop_name": shop_name,
            "date": date,
            "total": tot_pos,
            "totale_riconosciuto_dalla_somma": False,
            "items": [],
            "esito": "PAGAMENTO_ELETTRONICO",
            "somma_prodotti": 0.0,
            "scarto": None,
            "template_usato": None,
            "elaborato_il": None
        }

    profilo_catena = ottieni_profilo_catena(shop_name)
    template_usato = shop_name if profilo_catena else "generico"

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
    # Tutti insieme: la guardia sul riuso deve sapere cosa hanno gia' preso gli
    # addendi precedenti, e un ciclo che chiama la funzione una volta per volta
    # non puo' saperlo.
    nomi = nomi_di_uno_scontrino(righe_ocr, trovati, x_col, altezza)
    for (v, y), nome in zip(trovati, nomi):
        quality = qualita_nome(nome)
        somma += v

        items.append({
            "name": nome if nome is not None else "",
            "price": round(v, 2),
            "name_quality": quality
        })

    somma = round(somma, 2)

    # Se il totale letto non quadra, si guarda se un ALTRO importo stampato
    # accanto a un'etichetta di totale quadrerebbe. Non e' cercare il numero che
    # fa tornare i conti: i candidati sono tutti realmente stampati accanto a
    # "TOTAL", e la posizione da sola non basta a distinguerli — MISURATO, su
    # 144 righe con piu' importi "il piu' a destra" e "il maggiore" divergono in
    # 96 casi e nessuna delle due regole e' giusta (la riga di riepilogo IVA
    # `TOTAL 31,10 2,03` mette la quota a destra; `Total 7,79 ... 20,00` mette il
    # contante come massimo).
    #
    # La scelta viene MARCATA: e' un totale riconosciuto, non letto, e chi legge
    # il dato deve poterlo sapere.
    totale_riconosciuto = False
    if total is None or abs(somma - total) > TOLLERANZA_SOMMA:
        for candidato in candidati_totale(righe_ocr):
            if abs(somma - candidato) <= TOLLERANZA_SOMMA:
                total = candidato
                totale_riconosciuto = True
                break

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
        "totale_riconosciuto_dalla_somma": totale_riconosciuto,
        "items": items,
        "esito": esito,
        "somma_prodotti": somma,
        "scarto": scarto,
        "template_usato": template_usato,
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

        # Il totale si LEGGE, non si copia dai file dell'LLM. Quelli esistono
        # solo per 218 scontrini su 287: per gli altri il totale restava None
        # anche quando trova_totale() lo legge benissimo dal testo OCR.
        # MISURATO il 2026-08-30: 69 totali su 91 recuperati cosi', fra cui
        # "TOTAL (€) 26,81" e "TOTAL (€) 16,29", perfettamente leggibili.
        totale = trova_totale(dati.get("righe_ocr") or [])
        if totale is None:
            totale = meta.get("total")

        risultato = estrai_geometrico(
            dati.get("righe_ocr", []),
            sha256,
            meta.get("shop_name"),
            totale,
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
