"""
Fase A — ingestione idempotente: dalle foto ai ritagli e al testo OCR.

Produce i livelli 1-2 dell'architettura (vedi docs/20_analisi_e_strategie_sviluppo.md):

    data/estratti/<sha256>.json    un file per scontrino, con testo OCR
    data/ritagli/<sha256>.jpg      il ritaglio corrispondente

Perche' su file e non subito nel database: i dati grezzi vanno corretti e
rifatti piu' volte, e su file basta cancellare e rilanciare, mentre in tabelle
relazionali servirebbero UPDATE incrociati. Il database si popola tardi, quando
i dati sono gia' normalizzati e categorizzati.

Due difese contro il doppio lavoro, a due livelli diversi:

1. SCONTRINO — l'identita' e' l'hash SHA-256 del RITAGLIO, non della foto: una
   foto contiene piu' scontrini, e il ritaglio e' cio' che diventera' una riga
   del database. Un ritaglio gia' presente viene saltato.

   L'hash cambia se cambia la segmentazione (un ritaglio spostato di un pixel
   e' un file diverso). E' voluto: un ritaglio diverso E' uno scontrino
   estratto diversamente, e va rielaborato.

2. FOTOGRAFIA — la stessa foto puo' arrivare da fonti diverse (backup,
   WhatsApp, un altro telefono) ricompressa: i byte cambiano, il contenuto no.
   L'SHA-256 qui non serve a nulla, ed e' stato misurato: una ricompressione
   che sposta i pixel di 2.30 livelli medi su 255 produce un hash
   completamente diverso. Serve un hash PERCETTIVO (dhash), che guarda la
   struttura dell'immagine.

   Misurato: la stessa foto ricompressa o ridimensionata resta a distanza 0-2.
   Ma il dhash NON basta a decidere: guarda la scena (carta chiara su tavolo
   scuro) e su 6216 coppie del registro ne colloca 112 sotto soglia, comprese
   foto di negozi e mesi diversi a distanza 0. Percio' da' solo i SOSPETTI, e
   il verdetto lo dà il testo OCR (conferma_duplicato): due scontrini diversi
   condividono poche parole, lo stesso scontrino ricompresso quasi tutte.
   Nel dubbio si elabora e si segnala, non si scarta.

   Il registro delle foto viste sta in data/foto_viste.json e fa anche da
   indice foto -> scontrini.

Uso:
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini --limite 5
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini --rifai
    uv run python scripts/fase_a_ingestione.py data/2025_scontrini --ricostruisci-registro
"""
import hashlib
import json
import logging
import os
import re
import sys
import time
import warnings

import numpy as np
import cv2

warnings.filterwarnings("ignore")
os.environ.setdefault("GLOG_minloglevel", "3")
sys.path.insert(0, os.getcwd())

from app.etl.etl_engine import ReceiptPipeline  # noqa: E402
from app.storage import costruisci_archivio  # noqa: E402
from app.etl.segmenter import ReceiptSegmenter  # noqa: E402

logging.basicConfig(level=logging.WARNING)

DIR_ESTRATTI = "data/estratti"
DIR_RITAGLI = "data/ritagli"
REGISTRO_FOTO = "data/foto_viste.json"

# Prefissi dentro l'archivio. Non sono percorsi: su S3 diventano prefissi di
# chiave, in locale sottocartelle di data/. Vedi docs/120_piano_archivio_immagini.md
PREFISSO_ESTRATTI = "estratti/"
PREFISSO_RITAGLI = "ritagli/"

# Distanza di Hamming sotto la quale due foto si SOMIGLIANO abbastanza da
# meritare un controllo sul testo. Non basta a dirle uguali: vedi sotto.
#
# Qui c'era scritto che foto diverse stanno a 23-31 e che la soglia cadeva in
# un margine ampio. E' falso, e misurarlo e' costato poco: su tutte le 6216
# coppie del registro (112 foto) la distanza minima fra foto DIVERSE e' 0, e
# 112 coppie stanno gia' sotto questa soglia. Le due piu' vicine sono scontrini
# di negozi e mesi diversi.
#
# La causa e' che il dhash guarda la SCENA, non lo scontrino: ridotte a 8x8
# pixel in grigio, due foto di carta chiara sullo stesso tavolo scuro sono
# identiche. Fotografando sempre allo stesso modo, la collisione e' la norma.
# Abbassare la soglia non salva: anche a 0 restano 3 collisioni.
SOGLIA_DUPLICATO = 8

# Quanto testo devono avere in comune due foto per dirle lo stesso scontrino.
# Il phash da' i sospetti, queste due soglie danno il verdetto:
#
#   sopra CONFERMA   duplicato certo   -> si salta, dicendolo
#   sotto DISTINTE   scontrini diversi -> si elabora, e' una foto nuova
#   in mezzo         non si sa         -> si elabora COMUNQUE e si segnala
#
# La zona di mezzo non e' un difetto: e' il buco dichiarato. Nel dubbio si
# tiene il dato e lo si marca, perche' un doppione si vede e si toglie, mentre
# una foto scartata per errore non lascia traccia.
#
# Misurate sulle 112 coppie sotto soglia phash del registro:
#
#     foto DIVERSE      mediana 7.5%   p95 31.2%   MASSIMO 38.5%
#     duplicati VERI    93.6%, 100%
#
# Fra 38.5% e 93.6% ci sono 55 punti vuoti: la separazione e' larga, non una
# taratura fine. Le soglie stanno nel vuoto e non sui bordi, cosi' un caso
# leggermente fuori scala non ribalta il verdetto.
#
# Erano 0.50/0.20 prima di misurare: 0.20 mandava in zona grigia 18 coppie di
# foto palesemente diverse, cioe' 18 avvisi da leggere per nulla. A 0.45/0.40
# nessuna foto diversa viene segnalata e i due duplicati veri restano
# riconosciuti con oltre il doppio del margine.
SOGLIA_CONFERMA = 0.45
SOGLIA_DISTINTE = 0.40


def dhash(img, size=8):
    """
    Hash percettivo: confronta pixel adiacenti di una miniatura in grigio.

    L'hash SHA-256 non serve a riconoscere la stessa foto arrivata da fonti
    diverse: WhatsApp, un backup o un altro telefono la ricomprimono, e bastano
    2.30 livelli di differenza media su 255 — cioe' un'immagine visivamente
    identica — per cambiare completamente l'hash crittografico.

    Questo invece guarda la STRUTTURA dell'immagine (dove il chiaro passa allo
    scuro), che la ricompressione non altera.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return "".join("%02x" % int("".join("1" if b else "0" for b in bits[i:i + 8]), 2)
                   for i in range(0, len(bits), 8))


def distanza_hash(a, b):
    """Quanti bit differiscono fra due hash percettivi."""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def decodifica(dati):
    """Bytes from the archive -> image for OpenCV.

    The archive does not know what an image is: decoding belongs here.
    """
    if not dati:
        return None
    return cv2.imdecode(np.frombuffer(dati, np.uint8), cv2.IMREAD_COLOR)


def carica_registro():
    """Foto gia' elaborate, con il loro hash percettivo."""
    if os.path.exists(REGISTRO_FOTO):
        with open(REGISTRO_FOTO) as fh:
            return json.load(fh)
    return {}


def gia_viste(registro, phash):
    """Foto gia' elaborate che SOMIGLIANO a questa. Sospetti, non duplicati.

    Restituisce una lista e non il primo che capita: fra piu' candidati il
    duplicato vero puo' non essere il primo in ordine di dizionario, e sceglierlo
    per posizione significherebbe confrontare il testo con la foto sbagliata.
    """
    return [nome for nome, voce in registro.items()
            if distanza_hash(voce["phash"], phash) <= SOGLIA_DUPLICATO]


def parole(righe_ocr):
    """Parole di almeno due caratteri, per confrontare due scontrini.

    Un insieme, non una sequenza: l'ordine delle righe qui non conta, e cosi'
    il confronto regge anche dove la ricomposizione geometrica sbaglia a
    raggruppare (difetto noto, vedi AGENDA.md).
    """
    trovate = set()
    for riga in righe_ocr:
        trovate.update(re.findall(r"\w{2,}", (riga.get("testo") or "").lower()))
    return trovate


def somiglianza(a, b):
    """Quanto due insiemi di parole si sovrappongono: 0 = nulla, 1 = identici."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def conferma_duplicato(righe_nuove, sospetti, registro, archivio):
    """Il testo dice se e' davvero un duplicato. Torna (nome, somiglianza).

    Il phash guarda la SCENA — carta chiara su tavolo scuro — e su foto scattate
    sempre nello stesso modo collide di continuo: misurate 112 coppie sotto la
    soglia su 6216, e le due piu' vicine (distanza 0) sono scontrini di negozi e
    mesi diversi. Scartare su quella base cancellava foto nuove in silenzio.
    Il testo stampato invece distingue: due scontrini diversi condividono poche
    parole, lo stesso scontrino ricompresso le condivide quasi tutte.
    """
    nostre = parole(righe_nuove)
    if not nostre:
        return None, 0.0
    migliore, punteggio = None, 0.0
    for nome in sospetti:
        loro = set()
        for digest in registro.get(nome, {}).get("scontrini") or []:
            try:
                dati = archivio.leggi(PREFISSO_ESTRATTI + digest + ".json")
                loro |= parole(json.loads(dati).get("righe_ocr") or [])
            except Exception:
                # Un estratto illeggibile non deve far passare per nuovo cio'
                # che nuovo non e': si va avanti con gli altri.
                continue
        s = somiglianza(nostre, loro)
        if s > punteggio:
            migliore, punteggio = nome, s
    return migliore, punteggio


def sha256_immagine(img):
    """Hash of the encoded crop: the receipt's identity."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise ValueError("codifica JPEG fallita")
    return hashlib.sha256(buf.tobytes()).hexdigest(), buf


def ocr_righe(pipeline, crop):
    """OCR lines as plain text plus their box, ready to be re-parsed later."""
    righe = []
    for linea in pipeline._run_single_ocr(crop) or []:
        try:
            box, (testo, conf) = linea[0], linea[1]
            righe.append({
                "testo": testo,
                "confidenza": round(float(conf), 4),
                "box": [[int(p[0]), int(p[1])] for p in box],
            })
        except Exception:
            # A malformed line must not lose the whole receipt.
            continue
    return righe


def elabora_foto(chiave_foto, pipeline, segmenter, registro, rifai=False,
                 archivio=None, gia_estratti=None):
    """Orient, segment, OCR. Returns (nuovi, saltati, scontrini_trovati).

    `archivio` stores crops and extracts; `gia_estratti` is the set of keys
    already present, pre-scanned once by the caller. Checking membership in a
    set instead of asking the archive per receipt keeps this cheap on a remote
    backend, where each check would otherwise be a network round-trip.
    """
    nome = os.path.basename(chiave_foto)
    raw = decodifica(archivio.leggi(chiave_foto))
    if raw is None:
        print(f"  NON LEGGIBILE  {nome}")
        return 0, 0, 0

    # La stessa foto puo' arrivare da fonti diverse (backup, WhatsApp, un altro
    # telefono) con una ricompressione che ne cambia i byte ma non il contenuto.
    # L'hash percettivo la riconosce comunque.
    # Foto gia' completata: si esce PRIMA di orientare e segmentare.
    #
    # Saltare per singolo scontrino non basta a rendere economico un rilancio:
    # evita l'OCR, che e' la parte cara, ma orientamento e segmentazione girano
    # comunque, circa 26s per foto spesi per non produrre nulla. Su 96 foto sono
    # tre quarti d'ora. Il registro sa gia' quali scontrini ha dato ogni foto,
    # quindi basta verificare che i loro file esistano ancora.
    voce = registro.get(nome)
    if voce and not rifai:
        attesi = voce.get("scontrini") or []
        if attesi and all(PREFISSO_ESTRATTI + d + ".json" in gia_estratti
                          for d in attesi):
            return 0, len(attesi), len(attesi)

    # Il phash da' i SOSPETTI, non il verdetto: da solo scartava foto nuove.
    # Chi somiglia si porta avanti fino all'OCR, dove il testo decide (vedi
    # conferma_duplicato).
    phash = dhash(raw)
    sospetti = []
    if not rifai:
        sospetti = [n for n in gia_viste(registro, phash) if n != nome]

    img = pipeline._resize_safe(raw, 2000)
    img = pipeline._orient_whole_image(img, max_orient_dim=800)

    boxes = segmenter.boxes(img)
    nuovi = saltati = 0
    digests = []
    incerto = None          # (foto simile, somiglianza) se il testo non decide

    for indice, (x, y, w, h) in enumerate(boxes):
        crop = img[y:y + h, x:x + w]
        if crop.size == 0:
            continue
        digest, buf = sha256_immagine(crop)
        digests.append(digest)
        chiave_json = PREFISSO_ESTRATTI + digest + ".json"

        if chiave_json in gia_estratti and not rifai:
            saltati += 1
            continue

        righe = ocr_righe(pipeline, crop)

        # Il verdetto sui sospetti si da' qui, al primo ritaglio con del testo:
        # prima non c'era nulla da confrontare. Una volta deciso vale per tutta
        # la foto, percio' `sospetti` si svuota.
        if sospetti and righe:
            simile, punteggio = conferma_duplicato(righe, sospetti, registro,
                                                   archivio)
            sospetti = []
            if punteggio >= SOGLIA_CONFERMA:
                print(f"  DUPLICATO      {nome:<30} = {simile} "
                      f"(testo {punteggio:.0%})")
                return 0, 0, 0
            if punteggio >= SOGLIA_DISTINTE:
                # Ne' l'uno ne' l'altro: si tiene il dato e si segnala.
                incerto = (simile, punteggio)
                print(f"  DA VERIFICARE  {nome:<30} ~ {simile} "
                      f"(testo {punteggio:.0%}): elaborata comunque")

        record = {
            "sha256": digest,
            "foto_origine": nome,
            "indice_nella_foto": indice,
            "box": [x, y, w, h],
            "dimensioni_ritaglio": [w, h],
            "righe_ocr": righe,
            "n_righe_ocr": len(righe),
            "estratto_il": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if incerto:
            # Marcato nel dato, non solo stampato: un avviso a schermo si perde,
            # questo resta e da' modo di ritrovare i casi dubbi.
            record["sospetto_duplicato_di"] = incerto[0]
            record["somiglianza_testo"] = round(incerto[1], 3)
        archivio.scrivi(chiave_json,
                        json.dumps(record, indent=2,
                                   ensure_ascii=False).encode("utf-8"))
        archivio.scrivi(PREFISSO_RITAGLI + digest + ".jpg", buf.tobytes())
        gia_estratti.add(chiave_json)
        nuovi += 1

    # Il registro tiene anche la corrispondenza foto -> scontrini, cosi' serve
    # da indice per risalire dal ritaglio alla fotografia di provenienza.
    registro[nome] = {
        "phash": phash,
        "scontrini": digests,
        "elaborata_il": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return nuovi, saltati, len(boxes)


def ricostruisci_registro(sorgente):
    """
    Ricalcola l'hash percettivo delle foto gia' elaborate.

    Serve una volta sola, per le foto passate prima che il registro esistesse:
    senza, quelle foto non sono protette dal controllo duplicati. Costa poco,
    perche' l'hash percettivo non richiede ne' OCR ne' segmentazione.
    """
    registro = carica_registro()
    archivio = costruisci_archivio()
    aggiunte = 0
    for chiave in sorted(archivio.elenca(sorgente)):
        nome = os.path.basename(chiave)
        if not nome.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        if nome in registro:
            continue
        img = decodifica(archivio.leggi(chiave))
        if img is None:
            continue
        registro[nome] = {
            "phash": dhash(img),
            "scontrini": [],  # ignoto: la foto e' stata elaborata prima
            "elaborata_il": None,
        }
        aggiunte += 1
    with open(REGISTRO_FOTO, "w") as fh:
        json.dump(registro, fh, indent=2, ensure_ascii=False)
    print(f"Registro: {aggiunte} foto aggiunte, {len(registro)} in totale.")
    print(f"Scritto in {REGISTRO_FOTO}")
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    sorgente = argv[0]

    if "--ricostruisci-registro" in argv:
        return ricostruisci_registro(sorgente)
    rifai = "--rifai" in argv
    limite = None
    if "--limite" in argv:
        limite = int(argv[argv.index("--limite") + 1])

    archivio = costruisci_archivio()

    # ONE listing instead of one existence check per receipt. On a remote
    # backend the per-key form would be a network round-trip each time; the
    # caller keeps the set explicitly so the network cost stays visible here
    # rather than hidden in a cache inside the backend.
    gia_estratti = set(archivio.elenca(PREFISSO_ESTRATTI))

    chiavi = sorted(c for c in archivio.elenca(sorgente)
                    if c.lower().endswith((".jpg", ".jpeg", ".png")))
    nomi = chiavi
    if limite:
        nomi = nomi[:limite]
        chiavi = chiavi[:limite]

    print(f"Fase A — {len(nomi)} foto da {sorgente}/")
    print(f"  ritagli  -> {DIR_RITAGLI}/")
    print(f"  estratti -> {DIR_ESTRATTI}/\n")

    pipeline = ReceiptPipeline()
    segmenter = ReceiptSegmenter()
    registro = carica_registro()

    tot_nuovi = tot_saltati = tot_scontrini = 0
    prima = len(registro)
    inizio = time.time()

    for i, nome in enumerate(nomi, 1):
        t0 = time.time()
        nuovi, saltati, trovati = elabora_foto(
            nome, pipeline, segmenter, registro, rifai,
            archivio=archivio, gia_estratti=gia_estratti)
        tot_nuovi += nuovi
        tot_saltati += saltati
        tot_scontrini += trovati
        if trovati:
            print(f"  [{i:3d}/{len(nomi)}] {os.path.basename(nome):<30} "
                  f"{trovati} scontrini  ({nuovi} nuovi, {saltati} gia' presenti)"
                  f"  {time.time() - t0:.0f}s")
        # Salvataggio a ogni foto: un'interruzione a meta' non perde il lavoro.
        with open(REGISTRO_FOTO, "w") as fh:
            json.dump(registro, fh, indent=2, ensure_ascii=False)

    durata = time.time() - inizio
    print(f"\n{tot_scontrini} scontrini in {len(nomi)} foto "
          f"(media {tot_scontrini / max(1, len(nomi)):.1f} per foto)")
    print(f"{tot_nuovi} nuovi, {tot_saltati} gia' presenti")
    print(f"foto nel registro: {len(registro)} (erano {prima})")
    print(f"Tempo: {durata / 60:.1f} min ({durata / max(1, len(nomi)):.0f}s per foto)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
