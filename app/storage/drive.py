"""Archivio su Google Drive: la terza implementazione di ArchivioImmagini.

Le chiavi restano stringhe opache ("miniature/<sha>.jpg"): qui diventano una
gerarchia di cartelle dentro Drive, create quando servono. Chi chiama non lo sa
e non deve saperlo.

## L'autenticazione non e' una chiave API

Drive rifiuta le API key ("API keys are not supported by this API. Expected
OAuth2 access token", verificato il 2026-08-30 con la chiave di Gemini). Serve
un consenso dell'utente, dato una volta dal browser: da li' esce un token che si
rinnova da solo finche' non viene revocato.

    client_secret.json   scaricato dalla console Google, e' l'identita' DELL'APP
    token.json           prodotto al primo accesso, e' il permesso DELL'UTENTE

Nessuno dei due sta nel repository: entrambi in ~/.config/ticket-tracer/.

## Perche' un livello di cache

Drive identifica i file per id, non per nome: risalire da "miniature/x.jpg"
all'id costa una ricerca di rete. Con centinaia di file la stessa cartella
verrebbe cercata centinaia di volte, quindi gli id delle CARTELLE si tengono in
memoria — sono pochi e non cambiano durante un'esecuzione.

Gli id dei FILE invece non si mettono in cache: un file puo' essere sostituito
da un'altra sessione, e una cache che mente su un id e' peggio di una ricerca
in piu'. Vale la stessa ragione per cui `esiste()` non e' memorizzato.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Iterator

from app.storage.archivio import ArchivioImmagini, ChiaveAssente

CONFIG = Path(os.environ.get("TICKET_TRACER_CONFIG",
                             Path.home() / ".config" / "ticket-tracer"))
CLIENT_SECRET = CONFIG / "client_secret.json"
TOKEN = CONFIG / "token.json"

# Solo i file creati da questa applicazione. Con questo ambito Drive non
# concede alcun accesso al resto del Drive dell'utente: se un domani il codice
# avesse un difetto, il danno possibile resta confinato a cio' che ha creato.
AMBITI = ["https://www.googleapis.com/auth/drive.file"]

CARTELLA = "application/vnd.google-apps.folder"


def credenziali(interattivo: bool = True):
    """Le credenziali OAuth, chiedendo il consenso solo la prima volta."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    cred = None
    if TOKEN.is_file():
        cred = Credentials.from_authorized_user_file(str(TOKEN), AMBITI)

    if cred and cred.valid:
        return cred

    if cred and cred.expired and cred.refresh_token:
        cred.refresh(Request())          # silenzioso, non apre nulla
    else:
        if not interattivo:
            raise SystemExit(
                "manca l'autorizzazione a Drive. Lanciala una volta a mano:\n"
                "  uv run python scripts/autorizza_drive.py")
        if not CLIENT_SECRET.is_file():
            raise SystemExit(
                f"manca {CLIENT_SECRET}.\n"
                "Scaricalo dalla console Google: API e servizi -> Credenziali\n"
                "-> ID client OAuth -> App desktop -> Scarica JSON.")
        flusso = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET), AMBITI)
        cred = flusso.run_local_server(port=0)

    CONFIG.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(cred.to_json())
    TOKEN.chmod(0o600)
    return cred


class ArchivioDrive(ArchivioImmagini):
    """ArchivioImmagini su Google Drive.

    `radice` e' il nome della cartella di primo livello; viene creata se manca.
    """

    def __init__(self, radice: str = "ticket-tracer", servizio=None):
        self.radice = radice
        self._servizio = servizio
        self._cartelle: dict[str, str] = {}   # percorso -> id, solo cartelle

    @property
    def servizio(self):
        if self._servizio is None:
            from googleapiclient.discovery import build
            self._servizio = build("drive", "v3", credentials=credenziali(),
                                   cache_discovery=False)
        return self._servizio

    # --- navigazione interna -------------------------------------------------

    def _cerca(self, nome: str, genitore: str, cartella: bool):
        """L'id del figlio che si chiama cosi', o None."""
        tipo = "=" if cartella else "!="
        # Gli apostrofi vanno protetti o chiudono la stringa della query.
        sicuro = nome.replace("\\", "\\\\").replace("'", "\\'")
        query = (f"name = '{sicuro}' and '{genitore}' in parents "
                 f"and mimeType {tipo} '{CARTELLA}' and trashed = false")
        esito = self.servizio.files().list(
            q=query, spaces="drive", fields="files(id, name)",
            pageSize=1).execute()
        file = esito.get("files") or []
        return file[0]["id"] if file else None

    def _cartella(self, percorso: str, crea: bool) -> str | None:
        """L'id della cartella, creandola se richiesto.

        `percorso` e' la parte di chiave prima dell'ultimo "/", radice esclusa.
        """
        chiave_cache = percorso
        if chiave_cache in self._cartelle:
            return self._cartelle[chiave_cache]

        genitore = "root"
        parti = [self.radice] + [p for p in percorso.split("/") if p]
        costruito = []
        for parte in parti:
            costruito.append(parte)
            memorizzata = "/".join(costruito)
            if memorizzata in self._cartelle:
                genitore = self._cartelle[memorizzata]
                continue

            trovata = self._cerca(parte, genitore, cartella=True)
            if trovata is None:
                if not crea:
                    return None
                trovata = self.servizio.files().create(
                    body={"name": parte, "mimeType": CARTELLA,
                          "parents": [genitore]},
                    fields="id").execute()["id"]
            self._cartelle[memorizzata] = trovata
            genitore = trovata

        self._cartelle[chiave_cache] = genitore
        return genitore

    def _id_file(self, chiave: str) -> str | None:
        percorso, _, nome = chiave.rpartition("/")
        cartella = self._cartella(percorso, crea=False)
        if cartella is None:
            return None
        return self._cerca(nome, cartella, cartella=False)

    # --- l'interfaccia -------------------------------------------------------

    def leggi(self, chiave: str) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        identificativo = self._id_file(chiave)
        if identificativo is None:
            raise ChiaveAssente(chiave)

        buffer = io.BytesIO()
        scarico = MediaIoBaseDownload(
            buffer, self.servizio.files().get_media(fileId=identificativo))
        fatto = False
        while not fatto:
            _, fatto = scarico.next_chunk()
        return buffer.getvalue()

    def scrivi(self, chiave: str, dati: bytes) -> None:
        import mimetypes

        from googleapiclient.http import MediaIoBaseUpload

        percorso, _, nome = chiave.rpartition("/")
        cartella = self._cartella(percorso, crea=True)
        tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
        supporto = MediaIoBaseUpload(io.BytesIO(dati), mimetype=tipo,
                                     resumable=False)

        esistente = self._cerca(nome, cartella, cartella=False)
        if esistente:
            # Sostituisce il contenuto invece di creare un omonimo: Drive
            # permette due file con lo stesso nome nella stessa cartella, e la
            # lettura successiva prenderebbe uno dei due a caso.
            self.servizio.files().update(
                fileId=esistente, media_body=supporto).execute()
        else:
            self.servizio.files().create(
                body={"name": nome, "parents": [cartella]},
                media_body=supporto, fields="id").execute()

    def esiste(self, chiave: str) -> bool:
        return self._id_file(chiave) is not None

    def elenca(self, prefisso: str) -> Iterator[str]:
        """Le chiavi che cominciano col prefisso.

        Scende ricorsivamente dalla cartella corrispondente. Un prefisso che non
        finisce con "/" viene trattato come cartella piu' filtro sul nome, cosi'
        elenca("miniature") e elenca("miniature/") danno lo stesso risultato.
        """
        cartella_prefisso = prefisso.rstrip("/")
        radice_id = self._cartella(cartella_prefisso, crea=False)
        if radice_id is None:
            # Puo' essere un prefisso parziale di nomi dentro una cartella
            # superiore: si scende da li' e si filtra.
            genitore, _, inizio = cartella_prefisso.rpartition("/")
            radice_id = self._cartella(genitore, crea=False)
            if radice_id is None:
                return
            da_visitare = [(radice_id, genitore)]
            filtro = inizio
        else:
            da_visitare = [(radice_id, cartella_prefisso)]
            filtro = ""

        while da_visitare:
            identificativo, percorso = da_visitare.pop()
            pagina = None
            while True:
                esito = self.servizio.files().list(
                    q=f"'{identificativo}' in parents and trashed = false",
                    spaces="drive", fields="nextPageToken, files(id, name, mimeType)",
                    pageToken=pagina, pageSize=1000).execute()
                for file in esito.get("files", []):
                    sotto = f"{percorso}/{file['name']}" if percorso else file["name"]
                    if file["mimeType"] == CARTELLA:
                        da_visitare.append((file["id"], sotto))
                    elif sotto.startswith(prefisso) or not filtro:
                        yield sotto
                pagina = esito.get("nextPageToken")
                if not pagina:
                    break

    def cancella(self, chiave: str) -> None:
        identificativo = self._id_file(chiave)
        if identificativo is None:
            return  # idempotente, come richiede l'interfaccia
        self.servizio.files().delete(fileId=identificativo).execute()
