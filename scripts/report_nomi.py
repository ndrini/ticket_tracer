"""
Gli addendi sanno dire COME SI CHIAMANO?

PERCHE' QUESTO REPORT ESISTE. `report_addendi.py` misura che la somma degli
addendi geometrici da' il totale stampato: 117 scontrini su 218 contro i 62 di
oggi. Ma quel numero e' un TETTO, non un risultato, e confonderlo con un
risultato sarebbe l'errore piu' facile di tutto il progetto.

Il database non vuole una somma: vuole un ELENCO di prodotti con NOME e
prezzo. Un addendo di 2,82 che non sa di chiamarsi "LLET SEN.CONSUM 1L" non
entra in `spese.db`, e uno scontrino che quadra ma non sa nominare nulla non
vale piu' di uno che non quadra.

Fra la somma e l'elenco c'e' un passo che nessuno ha ancora misurato:
associare a ogni addendo il nome che gli sta accanto sulla carta. Questo
report misura QUEL passo, e niente altro. Non modifica niente.

LE METRICHE, DICHIARATE PRIMA DI MISURARE:

  principale   la COPERTURA: quanti addendi trovano un nome plausibile alla
               loro sinistra, sulla stessa riga fisica. Un addendo senza nome
               e' un buco: la somma quadra ma il prodotto non e' registrabile.
  guardia 1    gli scontrini COMPLETI: quelli in cui la somma quadra E ogni
               addendo ha un nome. Sono i soli utilizzabili davvero, ed e'
               questo il numero da confrontare con i 62 di oggi — non i 117.
  guardia 2    i nomi VUOTI O DEGENERI (una cifra, due lettere, un simbolo):
               un nome che non nomina e' peggio di un buco, perche' sembra
               buono e finisce nel catalogo.
  guardia 3    quanti nomi CAMBIEREBBERO rispetto a quelli estratti oggi dal
               modello, sui prodotti che oggi ci sono. Serve a vedere se la
               geometria stia rinominando cio' che gia' funzionava.
  guardia 4    i nomi FUSI: quando un importo cade fra due righe stampate, la
               raccolta prende frammenti di entrambe e ne esce un nome che
               contiene due prodotti ("LLEVAT ROYAL 80G 6 LLET SEN.CONSUM 1L").
               Il catalogo li registrerebbe come un articolo solo, inesistente.

Cosa conta come fallimento: se la copertura e' alta ma gli scontrini completi
sono pochi, il collo di bottiglia non e' il nome del singolo addendo ma la
loro somma; se i nomi degeneri superano il 5% degli addendi nominati, il
metodo non e' pronto per il catalogo.

    uv run python scripts/report_nomi.py
    uv run python scripts/report_nomi.py --dettaglio
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.getcwd())

from app.etl.addendi import addendi, confine_somma  # noqa: E402
from app.etl.geometria import (altezza_riga, centro_x, centro_y,  # noqa: E402
                               colonna_dei_prezzi, valore)

ROOT = Path(__file__).resolve().parent.parent
ESTRATTI = ROOT / "data" / "estratti"
STRUTTURATI = ROOT / "data" / "strutturati"

TOLLERANZA = 0.02

# Oltre questa lunghezza un nome ha quasi sempre inghiottito la riga vicina.
# Misurata la distribuzione sui 929 nomi validi: mediana 18, p90 26, p99 41,
# massimo 124. La soglia sta dopo il p90 e prima della coda anomala.
SOSPETTO_FUSIONE = 30

# Un nome deve contenere almeno tre lettere di fila: e' la stessa condizione
# che `prodotti_dalla_risposta` applica oggi, e tenerla uguale rende i due
# percorsi confrontabili invece che diversi per caso.
HA_NOME = re.compile(r"[A-Za-zÀ-ÿ]{3}")

# Cifre, quantita' e simboli che precedono il nome sulla riga stampata:
# "2 x 1,50 AMANIDA" -> "AMANIDA". Non e' un filtro sul nome, e' la pulizia
# della parte NUMERICA che sta a sinistra e che nome non e'.
PREFISSO_NUMERICO = re.compile(r"^[\d\s.,x×*/€-]+", re.I)

# Gli importi che l'OCR mette nello STESSO frammento del nome, o in frammenti
# alla sua destra ma prima della colonna: "ESTAC.CONSUM 250 0,86 1,72" e' il
# nome piu' il prezzo unitario piu' il totale di riga. Vanno tolti, altrimenti
# il catalogo si riempie di prodotti che portano il prezzo nel nome e lo stesso
# articolo comprato a due prezzi diventa due prodotti.
IMPORTI_IN_CODA = re.compile(r"(\s*-?\d{1,4}[.,]\d{2}\s*(?:€|EUR)?)+$", re.I)


def carica():
    """Gli scontrini strutturati, con accanto le righe OCR da cui vengono."""
    estratti = {}
    for p in glob.glob(str(ESTRATTI / "*.json")):
        d = json.load(open(p))
        estratti[d["sha256"]] = d["righe_ocr"]
    casi = []
    for p in sorted(glob.glob(str(STRUTTURATI / "*.json"))):
        d = json.load(open(p))
        if d["sha256"] in estratti:
            casi.append((d, estratti[d["sha256"]]))
    return casi


def nome_per_addendo(righe_ocr, y_addendo, x_addendo, altezza):
    """
    Il nome che sta a SINISTRA dell'addendo, sulla sua stessa riga fisica.

    Nessuna euristica sul contenuto: si prendono i frammenti che stanno sulla
    stessa riga (la y dista meno di mezza altezza) e piu' a sinistra della
    cifra, in ordine di x. E' la stessa regola geometrica del resto del
    modulo: la posizione decide, non le parole.
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


def degenere(nome):
    """Un nome che non nomina: troppo corto, o senza tre lettere di fila."""
    return nome is None or len(nome) < 3 or not HA_NOME.search(nome)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dettaglio", action="store_true",
                    help="elenca gli scontrini che quadrano ma non nominano")
    args = ap.parse_args()

    casi = carica()
    n = len(casi)

    tot_addendi = con_nome = degeneri = fusi = 0
    lunghezze = []
    quadrati = completi = quadrati_senza_nomi = 0
    nomi_diversi = confrontati = 0
    incompleti = []

    for d, righe in casi:
        altezza = altezza_riga(righe) if righe else None
        col = colonna_dei_prezzi(righe, altezza) if righe else None
        trovati = addendi(righe)
        totale = d.get("total")
        somma = round(sum(v for v, _ in trovati), 2) if trovati else None
        quadra = (totale is not None and somma is not None
                  and abs(somma - totale) <= TOLLERANZA)
        quadrati += quadra

        # x dell'addendo: si rilegge dalla colonna, che e' dove cade
        x_col = col[1] if col else None
        nomi = []
        for v, y in trovati:
            tot_addendi += 1
            nome = nome_per_addendo(righe, y, x_col, altezza) if x_col else None
            if nome is not None:
                con_nome += 1
                if degenere(nome):
                    degeneri += 1
                else:
                    lunghezze.append(len(nome))
                    # Un nome molto piu' lungo della norma ha quasi sempre
                    # inghiottito la riga vicina: la mediana e' 18 caratteri.
                    if len(nome) > SOSPETTO_FUSIONE:
                        fusi += 1
            nomi.append(nome)

        tutti_nominati = bool(trovati) and all(
            not degenere(nm) for nm in nomi)
        if quadra and tutti_nominati:
            completi += 1
        elif quadra:
            quadrati_senza_nomi += 1
            incompleti.append((d["sha256"][:12], d["esito"], totale,
                               len(trovati),
                               sum(1 for nm in nomi if not degenere(nm))))

        # guardia 3: i nomi cambierebbero rispetto a quelli di oggi?
        oggi = [i["name"] for i in (d.get("items") or [])]
        if oggi and nomi:
            confrontati += 1
            puliti = [nm for nm in nomi if nm and not degenere(nm)]
            if len(puliti) != len(oggi) or any(
                    a.strip().lower() not in b.strip().lower()
                    and b.strip().lower() not in a.strip().lower()
                    for a, b in zip(sorted(puliti), sorted(oggi))):
                nomi_diversi += 1

    print(f"scontrini: {n}   addendi totali: {tot_addendi}\n")

    pc = (100 * con_nome // tot_addendi) if tot_addendi else 0
    print("METRICA PRINCIPALE  copertura dei nomi")
    print(f"  addendi con un nome a sinistra: {con_nome:4d}/{tot_addendi}  ({pc}%)")
    print(f"  addendi senza nessun nome:      {tot_addendi - con_nome:4d}")

    print("\nGUARDIA 1  scontrini COMPLETI (quadrano E nominano tutto)")
    print(f"  quadrano:                    {quadrati:3d}")
    print(f"  di cui nominano tutto:       {completi:3d}   <- confrontabile con i 62 di oggi")
    print(f"  quadrano ma NON nominano:    {quadrati_senza_nomi:3d}")

    pd_ = (100 * degeneri // con_nome) if con_nome else 0
    print(f"\nGUARDIA 2  nomi degeneri (una cifra, due lettere, un simbolo)")
    print(f"  {degeneri}/{con_nome}  ({pd_}%)   soglia di fallimento dichiarata: 5%")

    print(f"\nGUARDIA 3  nomi diversi da quelli estratti oggi")
    print(f"  {nomi_diversi}/{confrontati} scontrini confrontabili")

    pf = (100 * fusi // len(lunghezze)) if lunghezze else 0
    lunghezze.sort()
    if lunghezze:
        mediana = lunghezze[len(lunghezze) // 2]
        print(f"\nGUARDIA 4  nomi FUSI (piu' di {SOSPETTO_FUSIONE} caratteri)")
        print(f"  {fusi}/{len(lunghezze)}  ({pf}%)   mediana {mediana} caratteri, "
              f"massimo {lunghezze[-1]}")

    if args.dettaglio and incompleti:
        print("\nQUADRANO MA NON NOMINANO TUTTO")
        for h, esito, tot, na, nn in incompleti[:30]:
            print(f"  {h}  [{esito:18s}] totale {tot}  addendi {na}  nominati {nn}")


if __name__ == "__main__":
    main()
