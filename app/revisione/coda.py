"""
Which receipts deserve a human look, and in which order.

NASCE DA UNA MISURA, sui 306 scontrini del 2026-08-29:

    39  zero righe          -> quasi certamente un ritaglio sbagliato
    65  una riga sola       -> idem: uno scontrino della spesa non ha una riga
    52  non quadrano        -> le righe ci sono ma i conti no
    65  totale assente      -> non verificabile, non necessariamente sbagliato
    85  validi e pieni      -> non si guardano

L'ordine non e' un'opinione: **il taglio viene prima dei numeri**, perche' un
ritaglio sbagliato rende inutile qualunque domanda sui dati. Chiedere prima
"i conti tornano?" su uno scontrino tagliato male spreca il tempo di chi rivede.

Fra due scontrini che non quadrano vince lo scarto piu' grande: 671 euro di
differenza sono un errore piu' istruttivo di 3.

I RITAGLI DELLA STESSA FOTO STANNO INSIEME. Ordinandoli solo per sospetto
finivano lontanissimi: MISURATO il 2026-08-29 sui 218 in coda, due fratelli
distavano in mediana 78 posizioni e fino a 202, e solo 3 foto su 64 li avevano
entro cinque posti. Chi rivede riapriva percio' la stessa foto tre o quattro
volte a decine di scontrini di distanza, rifacendo ogni volta la fatica di
capire quale pezzo di carta stesse guardando.

La foto pesa quanto il suo ritaglio PIU' sospetto, cosi' raggrupparli non
seppellisce un caso urgente dietro una foto tranquilla.
"""
from dataclasses import dataclass
from enum import Enum


class Sospetto(Enum):
    """What we suspect is wrong. Decides which question to ask first."""
    TAGLIO = "taglio"
    ESTRAZIONE = "estrazione"
    NON_VERIFICABILE = "non_verificabile"


@dataclass(frozen=True)
class VoceDiCoda:
    receipt_id: int
    sha256: str
    sospetto: Sospetto
    motivo: str
    n_righe: int
    stato: str
    delta: float | None
    confidenza: float


# Lower sorts first.
_ORDINE = {Sospetto.TAGLIO: 0, Sospetto.ESTRAZIONE: 1, Sospetto.NON_VERIFICABILE: 2}


def _classifica(n_righe, stato, delta):
    if n_righe == 0:
        return Sospetto.TAGLIO, "nessuna riga estratta"
    if n_righe == 1:
        return Sospetto.TAGLIO, "una riga sola"
    if stato in ("SOMMA_IN_ECCESSO", "SOMMA_IN_DIFETTO"):
        scarto = f"{abs(delta):.2f} EUR" if delta is not None else "?"
        return Sospetto.ESTRAZIONE, f"non quadra: {stato.lower()} di {scarto}"
    if stato == "TOTALE_ASSENTE":
        return Sospetto.NON_VERIFICABILE, "manca il totale stampato"
    if stato == "PRODOTTI_ASSENTI":
        return Sospetto.TAGLIO, "nessun prodotto riconosciuto"
    return None, ""


def costruisci_coda(conn, limite=None, mappa_foto=None):
    """Receipts worth reviewing, most suspicious first, siblings kept together.

    Already-reviewed ones (completed_at set) drop out; an open, unfinished
    review stays, so an interrupted session resumes where it left off.

    mappa_foto: sha256 -> source photo. Without it the grouping is skipped and
    the order is the old flat one, so a caller with no registry still works.
    """
    righe = conn.execute("""
        SELECT r.id, r.image_sha256, r.validation_status, r.validation_delta,
               COALESCE(r.extraction_confidence, 0.0), COUNT(rl.id)
        FROM receipts r
        LEFT JOIN receipt_lines rl ON rl.receipt_id = r.id
        WHERE r.id NOT IN (SELECT receipt_id FROM manual_review_queue
                           WHERE completed_at IS NOT NULL)
        GROUP BY r.id
    """).fetchall()

    coda = []
    for rid, sha, stato, delta, confidenza, n_righe in righe:
        sospetto, motivo = _classifica(n_righe, stato, delta)
        if sospetto is None:
            continue  # valid and populated: not worth a human's time
        coda.append(VoceDiCoda(rid, sha, sospetto, motivo, n_righe,
                               stato or "", delta, confidenza))

    # Within a class, the largest discrepancy first; ties by id for stability.
    def peso(v):
        return (_ORDINE[v.sospetto], -abs(v.delta or 0), v.receipt_id)

    coda.sort(key=peso)

    if mappa_foto:
        # A photo inherits its most suspicious crop's rank, then its crops
        # follow in their own order. Crops with no known photo keep their own
        # place, each as a group of one.
        gruppi = {}
        for v in coda:
            chiave = mappa_foto.get(v.sha256) or f"\0{v.receipt_id}"
            gruppi.setdefault(chiave, []).append(v)
        coda = [v for _, membri in
                sorted(gruppi.items(), key=lambda kv: peso(kv[1][0]))
                for v in membri]

    return coda[:limite] if limite else coda
