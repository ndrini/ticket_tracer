"""Pairing a printed amount with the product name that belongs to it.

Extracted from `scripts/fase_c_geometrica.py`, where it lived beside an
identical copy in `scripts/report_nomi.py`. Two copies meant the report could
keep measuring by the old rule and report that all was well precisely while
the defect persisted, so the two now share this one.
"""
import re

HA_NOME = re.compile(r"[A-Za-zÀ-ÿ]{3}")
SOSPETTO_FUSIONE = 30
PREFISSO_NUMERICO = re.compile(r"^[\d\s.,x×*/€-]+", re.I)
IMPORTI_IN_CODA = re.compile(r"(\s*-?\d{1,4}[.,]\d{2}\s*(?:€|EUR)?)+$", re.I)


def _ripulisci(pezzi):
    """Fragments to the left of an amount, joined and stripped of numbers."""
    if not pezzi:
        return None
    testo = " ".join(t for _, t in sorted(pezzi))
    testo = IMPORTI_IN_CODA.sub("", testo)
    testo = PREFISSO_NUMERICO.sub("", testo).strip(" |×x*-–=.,:")
    return testo.strip() or None


PORTA_IMPORTO = re.compile(r"-?\d{1,4}[.,]\d{2}")


def nome_per_addendo(righe_ocr, y_addendo, x_addendo, altezza,
                     gia_usati=None, importo=None):
    """The name belonging to the amount at (x_addendo, y_addendo).

    Looks on the amount's own row first, then — only under the guards below —
    on the row above, because weighed goods and IKEA print the name there:

        Pastanaga Granel
           1,204     1,78     2,14

    Rows are compared with `stessa_riga()`, which straightens the receipt
    first. A plain `abs(y1 - y2) < k` assumes it is upright; measured on this
    material the worst tenth is tilted 2.1 degrees and the maximum 4.2, which
    across 400px is a whole line of drop.

    `gia_usati` is the set of fragment identities already consumed by earlier
    amounts, and the caller grows it through `segna_usati`. Without it a name
    found above would be handed to every amount underneath: measured, 66% of
    receipts have two amounts closer than 1.5 rows, so this is the common case,
    not an edge one. The "row above carries no amount" guard does not cover it
    — on weighed formats the name row carries none, so it passes.

    It tracks fragments and not strings because the same product bought twice
    prints its name twice, and both purchases are real.
    """
    from app.etl.geometria import centro_x, centro_y
    from app.etl.righe_logiche import stessa_riga

    vicine, _ = stessa_riga(righe_ocr)

    pezzi = []
    for r in righe_ocr:
        y, x = centro_y(r["box"]), centro_x(r["box"])
        if not vicine(y, x, y_addendo, x_addendo):
            continue
        if x >= x_addendo:
            continue
        pezzi.append((x, r["testo"]))

    # A name on the amount's own row needs no guard: it is printed level with
    # it, so no other amount can claim it without claiming this one too.
    nome = _ripulisci(pezzi)
    if nome is not None:
        return nome

    # Nothing on our own row. A negative amount with no name is a discount or
    # a refund, and the row above is the product it applies to: taking that
    # name would invent a second purchase that still balances the total.
    # Flag it instead — a declared hole stays checkable, an invented number
    # does not.
    if importo is not None and importo < 0:
        return None

    trovato = _nome_dalla_riga_sopra(righe_ocr, y_addendo, x_addendo, altezza,
                                     vicine, gia_usati or frozenset())
    return trovato[0] if trovato else None


def nomi_di_uno_scontrino(righe_ocr, trovati, x_colonna, altezza):
    """The name of every amount on one receipt, left to right, top to bottom.

    Names are resolved together rather than one call at a time because the
    fourth guard needs to know what earlier amounts already took. A caller
    looping over `nome_per_addendo` alone would let two amounts claim the same
    printed name.
    """
    usati, nomi = set(), []
    for valore, y in trovati:
        trovato = None
        pezzi_riga = _pezzi_sulla_riga(righe_ocr, y, x_colonna)
        nome = _ripulisci(pezzi_riga)
        if nome is None and not (valore is not None and valore < 0):
            from app.etl.righe_logiche import stessa_riga
            vicine, _ = stessa_riga(righe_ocr)
            trovato = _nome_dalla_riga_sopra(righe_ocr, y, x_colonna, altezza,
                                             vicine, usati)
            if trovato:
                nome, id_riga = trovato
                usati |= id_riga
        nomi.append(nome)
    return nomi


def _pezzi_sulla_riga(righe_ocr, y_addendo, x_addendo):
    """Fragments level with the amount and to its left."""
    from app.etl.geometria import centro_x, centro_y
    from app.etl.righe_logiche import stessa_riga

    vicine, _ = stessa_riga(righe_ocr)
    return [(centro_x(r["box"]), r["testo"]) for r in righe_ocr
            if vicine(centro_y(r["box"]), centro_x(r["box"]),
                      y_addendo, x_addendo)
            and centro_x(r["box"]) < x_addendo]


# How far up the name may sit, in rows. MEASURED, not chosen. On real receipts
# consecutive amounts sit 1.23-1.46 rows apart, so a wider window reaches the
# previous amount's own row and every name shifts down by one — seen on
# 20e8047e91, where "Cogombre 1,162" became "Cogombre 1,088".
#
# Swept 0.9 to 1.5 over 352 receipts: no name / fused
#     0.9  13% / 6%      1.2   9% / 7%
#     1.0  11% / 7%      1.3   9% / 7%
#     1.1  10% / 7%      1.5   9% / 7%
# 1.2 is the low edge of the plateau: the full gain at the smallest reach.
FINESTRA_SOPRA = 1.2


def _nome_dalla_riga_sopra(righe_ocr, y_addendo, x_addendo, altezza,
                           vicine, gia_usati):
    """The name printed one row above the amount, if it is really its own.

    Three guards, then the fourth. The row must be adjacent (further up is
    another product, not a continuation), must not itself carry an amount
    (then it is a complete row, not a split one), and its name must not
    already belong to an earlier amount.
    """
    from app.etl.geometria import centro_x, centro_y

    sopra = [r for r in righe_ocr
             if 0 < y_addendo - centro_y(r["box"]) < FINESTRA_SOPRA * altezza
             and not vicine(centro_y(r["box"]), centro_x(r["box"]),
                            y_addendo, x_addendo)]
    if not sopra:
        return None

    # The nearest fragment up is the anchor; the rest of its row is whatever
    # sits level WITH THAT ANCHOR. Both its own y and x go into the test —
    # passing the candidate's own x on both sides would compare a point with
    # itself, which is always true, and the row would swallow the one above it.
    ancora = max(sopra, key=lambda r: centro_y(r["box"]))
    y_ancora, x_ancora = centro_y(ancora["box"]), centro_x(ancora["box"])
    riga = [r for r in sopra
            if vicine(centro_y(r["box"]), centro_x(r["box"]),
                      y_ancora, x_ancora)]

    pezzi = [(centro_x(r["box"]), r["testo"]) for r in riga]
    testo = " ".join(t for _, t in sorted(pezzi))
    if PORTA_IMPORTO.search(testo):
        return None

    # The fourth guard is on the FRAGMENTS, not on the string: the same
    # product bought twice on one receipt prints its name twice and both
    # amounts are real (45 such cases in the material). What must not happen
    # is two amounts claiming the SAME printed name.
    id_riga = frozenset(id(r) for r in riga)
    if id_riga & gia_usati:
        return None

    nome = _ripulisci(pezzi)
    if nome is None:
        return None
    return nome, id_riga


def qualita_nome(nome):
    """How trustworthy the name is.

    - complete:   there is a name and it looks like one
    - fused:      it has swallowed part of a neighbouring row
    - incomplete: none found
    """
    if nome is None:
        return "incomplete"
    if len(nome) < 3 or not HA_NOME.search(nome):
        return "incomplete"
    if len(nome) > SOSPETTO_FUSIONE:
        return "fused"
    return "complete"
