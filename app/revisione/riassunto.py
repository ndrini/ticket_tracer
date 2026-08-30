"""Quanto e' fatto, letto dai file locali: la pagina si apre subito.

Serve a rispondere alla domanda che prima si poteva fare solo lanciando i
comandi: ci sono foto nuove da ingerire? quanti scontrini quadrano?

## Perche' non chiede niente a Google Drive

Su Drive ci sono 507 file, e contarli e' una chiamata di rete. Farla a ogni
caricamento significherebbe una pagina lenta e inservibile senza connessione,
per un numero che cambia solo quando si preme un pulsante. Chi vuole sapere
cosa manca lassu' lancia sincronizza_drive.py, che lo dice e non carica nulla
finche' non gli si passa --esegui.

Due test lo impongono, non e' solo una buona intenzione.

## Perche' non impedisce di sbagliare l'ordine

Le fasi hanno un ordine, e la pagina lo mostra numerato. Ma non blocca: ogni
script e' gia' idempotente e sa saltare cio' che e' fatto, quindi un blocco qui
sarebbe una SECONDA verita' sullo stato del lavoro, libera di divergere da
quella vera. Meglio dire cosa conviene fare e lasciar decidere.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.etl.chiusura import esamina

IMMAGINI = (".jpg", ".jpeg", ".png", ".webp")

# Cartelle di data/ che contengono FOTO da elaborare, non prodotti della
# pipeline. Tenute esplicite: un elenco per esclusione conterebbe come foto
# ogni cartella nuova, e il numero mostrato sarebbe sbagliato in silenzio.
CARTELLE_FOTO = ("2025_scontrini", "2026_scontrini", "pictures_input",
                 "receipts_input", "pictures_not_yet_used", "pictures_archived",
                 "receipts_archived")

# Le fasi in ordine, con cio' che va detto a chi guarda. `chiave` e' il nome
# che il server passa a Lavori.avvia().
FASI = [
    {
        "chiave": "ingestione",
        "titolo": "Ingestione",
        "spiega": "Ritaglia gli scontrini dalle foto e ne legge il testo. "
                  "Riconosce le foto gia' viste, anche ricompresse o ruotate, "
                  "e le salta.",
        "quando": "quando ci sono foto nuove",
        "costo": "~2 minuti per foto",
        "serve_cartella": True,
    },
    {
        "chiave": "estrazione",
        "titolo": "Estrazione prodotti",
        "spiega": "Dal testo ai prodotti con prezzo, riga per riga.",
        "quando": "dopo l'ingestione",
        "costo": "secondi",
    },
    {
        "chiave": "miniature",
        "titolo": "Miniature",
        "spiega": "Immagini piccole per il controllo a occhio e per Drive.",
        "quando": "dopo l'estrazione",
        "costo": "secondi",
    },
    {
        "chiave": "vaglio",
        "titolo": "Vaglio",
        "spiega": "Separa gli scontrini chiusi da quelli da ripassare. "
                  "Non cancella nulla.",
        "quando": "dopo le miniature",
        "costo": "secondi",
    },
    {
        "chiave": "drive_immagini",
        "titolo": "Immagini su Drive",
        "spiega": "Miniature di tutti gli scontrini, piu' gli originali a piena "
                  "risoluzione dei soli non chiusi. Salta cio' che c'e' gia'.",
        "quando": "quando vuoi una copia fuori da questo computer",
        "costo": "qualche minuto",
    },
    {
        "chiave": "drive_dati",
        "titolo": "Dati su Drive",
        "spiega": "I JSON strutturati e una copia datata del database, accanto "
                  "alle immagini.",
        "quando": "insieme alle immagini",
        "costo": "qualche minuto",
    },
    {
        "chiave": "database",
        "titolo": "Caricamento nel database",
        "spiega": "Versa gli scontrini nelle tabelle per i report di spesa.",
        "quando": "quando il difetto qui accanto sara' risolto",
        "costo": "secondi",
        "sospesa": True,
        # Il motivo sta qui e non in un commento: chi torna fra sei mesi lo
        # trova nella pagina, dove serve. Un pulsante assente e' una domanda,
        # uno disabilitato con la ragione e' una risposta.
        "perche": "Sui formati a peso il nome e il prezzo vengono accoppiati "
                  "male e la somma quadra lo stesso: gli scontrini sbagliati "
                  "risulterebbero chiusi, cioe' certificati come buoni. "
                  "Vedi AGENDA.md.",
    },
]


def _conta_immagini(cartella: Path) -> int:
    if not cartella.is_dir():
        return 0
    return sum(1 for f in cartella.iterdir()
               if f.is_file() and f.suffix.lower() in IMMAGINI)


def _conta(cartella: Path, motivo: str) -> int:
    if not cartella.is_dir():
        return 0
    return sum(1 for f in cartella.iterdir() if f.is_file() and f.name.endswith(motivo))


def riassumi(radice: Path) -> dict:
    """I numeri della pagina. Solo file locali: vedi il docstring del modulo."""
    radice = Path(radice)

    foto = {c: _conta_immagini(radice / c) for c in CARTELLE_FOTO}

    # Quante foto non sono ancora passate dall'ingestione. Il registro tiene i
    # nomi gia' visti; qui basta la differenza, senza rileggere le immagini.
    viste = set()
    registro = radice / "foto_viste.json"
    if registro.is_file():
        try:
            viste = set(json.loads(registro.read_text()))
        except (OSError, json.JSONDecodeError):
            viste = set()

    nomi_su_disco = set()
    for cartella in CARTELLE_FOTO:
        percorso = radice / cartella
        if percorso.is_dir():
            nomi_su_disco.update(
                f.name for f in percorso.iterdir()
                if f.is_file() and f.suffix.lower() in IMMAGINI)

    chiusi = da_ripassare = illeggibili = strutturati = 0
    cartella_strutturati = radice / "strutturati_geometrici"
    if cartella_strutturati.is_dir():
        for percorso in cartella_strutturati.glob("*.json"):
            strutturati += 1
            try:
                dati = json.loads(percorso.read_text())
            except (OSError, json.JSONDecodeError):
                # Un file rotto si conta e si dichiara: azzerare il riassunto
                # per colpa sua sarebbe peggio del buco che segnala.
                illeggibili += 1
                continue
            if esamina(dati)[0] == "chiuso":
                chiusi += 1
            else:
                da_ripassare += 1

    return {
        "foto": sum(foto.values()),
        "foto_per_cartella": {k: v for k, v in foto.items() if v},
        "da_ingerire": len(nomi_su_disco - viste),
        "gia_viste": len(viste),
        "estratti": _conta(radice / "estratti", ".json"),
        "ritagli": _conta_immagini(radice / "ritagli"),
        "miniature": _conta_immagini(radice / "miniature"),
        "strutturati": strutturati,
        "chiusi": chiusi,
        "da_ripassare": da_ripassare,
        "illeggibili": illeggibili,
    }
