"""
Everything one review screen needs, and where the verdict goes.

The verdict is written into `manual_review_queue` and `receipt_lines`, tables
the Week-2 migration already created and nobody ever filled. Inventing a JSON
file of our own would have split the record in two.

NIENTE CORREZIONI: si registra un giudizio, non si modificano i dati. Segnalare,
non correggere d'ufficio.
"""
import json
import pathlib
from dataclasses import dataclass

RADICE = pathlib.Path(__file__).resolve().parent.parent.parent
REGISTRO_FOTO = RADICE / "data" / "foto_viste.json"


@dataclass(frozen=True)
class Riga:
    nome: str
    quantita: float | None
    prezzo: float | None


@dataclass(frozen=True)
class Fratello:
    """Another crop cut from the same photo."""
    receipt_id: int
    sha256: str
    negozio: str
    stato: str
    giudicato: bool
    corrente: bool


@dataclass(frozen=True)
class Scheda:
    """One receipt, ready to be shown."""
    receipt_id: int
    sha256: str
    sospetto: str
    motivo: str
    stato: str
    delta: float | None
    confidenza: float
    negozio: str
    data: str
    totale_dichiarato: float | None
    totale_calcolato: float | None
    righe: list[Riga]
    foto_origine: str | None
    fratelli: list["Fratello"]
    posizione: int
    totale_coda: int


def mappa_foto():
    """sha256 -> source photo, from the registry.

    Measured on 2026-08-29: receipts.foto_origine is empty for 88 of 306, while
    the registry covers 306/306. So the registry is the source, not the column.
    """
    if not REGISTRO_FOTO.is_file():
        return {}
    registro = json.loads(REGISTRO_FOTO.read_text())
    return {sha: foto
            for foto, voce in registro.items()
            for sha in (voce.get("scontrini") or [])}


def _fratelli(conn, foto, sha_corrente, mappa):
    """The other crops from the same photo, in the order they were cut.

    MISURATO il 2026-08-29: 192 dei 218 scontrini in coda hanno almeno un
    fratello, e una foto ne contiene fino a 5. Giudicare un ritaglio senza
    vedere gli altri della stessa foto costringe a ricostruire a mente quale
    pezzo di carta si sta guardando.

    Include the current one, flagged: the tab strip needs to show where you are.
    """
    if not foto:
        return []
    sha_foto = [sha for sha, f in mappa.items() if f == foto]
    if len(sha_foto) < 2:
        return []

    segnaposto = ",".join("?" * len(sha_foto))
    righe = conn.execute(f"""
        SELECT r.image_sha256, r.id, COALESCE(c.name, ''),
               COALESCE(r.validation_status, ''),
               EXISTS(SELECT 1 FROM manual_review_queue q
                      WHERE q.receipt_id = r.id AND q.completed_at IS NOT NULL)
        FROM receipts r LEFT JOIN commerces c ON c.id = r.id_commerce
        WHERE r.image_sha256 IN ({segnaposto})
        ORDER BY r.id""", sha_foto).fetchall()

    return [Fratello(rid, sha, negozio, stato, bool(fatto), sha == sha_corrente)
            for sha, rid, negozio, stato, fatto in righe]


def costruisci_scheda(conn, voce, posizione, totale_coda, mappa=None):
    mappa = mappa_foto() if mappa is None else mappa
    testata = conn.execute("""
        SELECT COALESCE(c.name, ''), COALESCE(r.data_ora, r.date, ''),
               r.total_declared, r.total_computed
        FROM receipts r LEFT JOIN commerces c ON c.id = r.id_commerce
        WHERE r.id = ?""", (voce.receipt_id,)).fetchone() or ("", "", None, None)

    righe = [Riga(nome or "(senza nome)", q, p) for nome, q, p in conn.execute("""
        SELECT COALESCE(p.name, ''), rl.quantity, rl.total_price
        FROM receipt_lines rl LEFT JOIN products p ON p.id = rl.product_id
        WHERE rl.receipt_id = ? ORDER BY rl.id""", (voce.receipt_id,))]

    return Scheda(
        receipt_id=voce.receipt_id, sha256=voce.sha256,
        sospetto=voce.sospetto.value, motivo=voce.motivo, stato=voce.stato,
        delta=voce.delta, confidenza=voce.confidenza,
        negozio=testata[0], data=testata[1],
        totale_dichiarato=testata[2], totale_calcolato=testata[3],
        righe=righe, foto_origine=mappa.get(voce.sha256),
        fratelli=_fratelli(conn, mappa.get(voce.sha256), voce.sha256, mappa),
        posizione=posizione, totale_coda=totale_coda,
    )


def registra_giudizio(conn, receipt_id, taglio_ok, dati_ok, nota, chi):
    """Record the verdict. Saved per keystroke, not on navigation.

    taglio_ok / dati_ok: True, False or None (not judged - a bad crop makes the
    data question moot, so it is legitimately left unanswered).
    """
    def parola(v):
        return "ok" if v is True else "sbagliato" if v is False else "non_giudicato"

    motivo = f"taglio:{parola(taglio_ok)} dati:{parola(dati_ok)}"

    # A second verdict on the same receipt replaces the first rather than
    # piling up: measured on 2026-08-29, receipt #302 had been saved three
    # identical times because Enter fired again while the first POST was still
    # in flight. Counting one receipt three times would skew any measure built
    # on these judgements.
    conn.execute("DELETE FROM manual_review_queue WHERE receipt_id = ?",
                 (receipt_id,))
    conn.execute("""
        INSERT INTO manual_review_queue
            (receipt_id, reason, review_notes, reviewed_by, action_taken,
             completed_at, started_at)
        VALUES (?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
        (receipt_id, motivo, nota or None, chi, "giudicato"))

    # Only a positive verdict marks the lines as human-checked: "wrong" says
    # they were looked at, not that they are right.
    if dati_ok is True:
        conn.execute("""
            UPDATE receipt_lines SET verified_by_human = 1,
                verification_timestamp = CURRENT_TIMESTAMP, verified_by_user = ?
            WHERE receipt_id = ?""", (chi, receipt_id))
    conn.commit()
