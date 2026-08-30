"""Autorizza una volta sola l'accesso a Google Drive.

    uv run python scripts/autorizza_drive.py
    uv run python scripts/autorizza_drive.py --stato     # controlla e basta
    uv run python scripts/autorizza_drive.py --revoca    # cancella il permesso

Apre il browser, tu accetti, e il permesso viene salvato in
~/.config/ticket-tracer/token.json. Da li' in poi si rinnova da solo: questo
script non va piu' lanciato.

## Perche' non basta il client_secret.json

Sono due cose diverse, ed e' voluto:

    client_secret.json   chi e' l'APPLICAZIONE
    token.json           cosa puo' fare sui TUOI dati

Il primo funziona per chiunque lo abbia — identifica il programma, non concede
niente. Il secondo e' il tuo consenso, ed e' legato al tuo account.

## Cosa concede, esattamente

L'ambito richiesto e' `drive.file`: **solo i file creati da questa
applicazione**. Non da' alcun accesso al resto del tuo Drive — documenti, foto,
cartelle che gia' esistono restano invisibili al programma. E' l'ambito piu'
stretto che permetta di scrivere, scelto di proposito: se un domani il codice
avesse un difetto, il danno possibile resta confinato a cio' che ha creato.

Il permesso e' revocabile in ogni momento, da qui con --revoca oppure dalla
pagina https://myaccount.google.com/permissions
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.storage.drive import (  # noqa: E402
    AMBITI, CLIENT_SECRET, TOKEN, ArchivioDrive, credenziali)


def stato():
    presente = "c'e'" if CLIENT_SECRET.is_file() else "MANCA"
    print(f"client_secret.json  {presente:<12} {CLIENT_SECRET}")
    if not TOKEN.is_file():
        print(f"token.json          MANCA        {TOKEN}")
        print("\nNon sei ancora autorizzato. Lancia questo script senza argomenti.")
        return 1

    dati = json.loads(TOKEN.read_text())
    print(f"token.json          {"c'e'":<12} {TOKEN}")
    print(f"  account:  {dati.get('account') or '(non registrato)'}")
    print(f"  ambiti:   {', '.join(dati.get('scopes') or [])}")
    print(f"  scadenza: {dati.get('expiry') or '(non indicata)'}")
    print("\n  La scadenza e' normale: il token si rinnova da solo.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--stato", action="store_true", help="controlla e basta")
    p.add_argument("--revoca", action="store_true",
                   help="cancella il permesso salvato")
    p.add_argument("--radice", default="ticket-tracer",
                   help="cartella di primo livello su Drive")
    args = p.parse_args(argv)

    if args.stato:
        return stato()

    if args.revoca:
        if TOKEN.is_file():
            TOKEN.unlink()
            print(f"cancellato {TOKEN}")
            print("Il permesso resta comunque attivo lato Google: per toglierlo")
            print("davvero, vai su https://myaccount.google.com/permissions")
        else:
            print("nessun token da cancellare.")
        return 0

    if not CLIENT_SECRET.is_file():
        raise SystemExit(
            f"manca {CLIENT_SECRET}.\n"
            "Scaricalo dalla console Google: API e servizi -> Credenziali\n"
            "-> ID client OAuth -> App desktop -> Scarica JSON.")

    gia = TOKEN.is_file()
    if not gia:
        print("Si apre il browser: accetta, e il permesso viene salvato.")
        print("Se Google dice che l'app non e' verificata, e' normale — e' la")
        print("tua, e non e' pubblicata. Vai avanti da 'Avanzate'.\n")

    credenziali()          # fa il giro OAuth e scrive il token
    print("autorizzazione riuscita.\n")

    # Non si dichiara riuscito senza aver provato a usarlo davvero.
    archivio = ArchivioDrive(radice=args.radice)
    prova = "prova/autorizzazione.txt"
    archivio.scrivi(prova, b"ticket-tracer: prova di scrittura")
    letto = archivio.leggi(prova)
    archivio.cancella(prova)
    print(f"  scritto, riletto ({len(letto)} byte) e cancellato "
          f"un file di prova in {args.radice}/prova/")
    print(f"  Drive e' pronto. Ambito concesso: {AMBITI[0].rsplit('/', 1)[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
