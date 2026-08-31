"""Tests for pairing a product name with its amount.

The defect these describe, measured over 352 real receipts before the fix:
355 amounts out of 2131 (17%) had no name, and 191 (9%) had swallowed a
neighbouring row. Two wrong assumptions in `nome_per_addendo` caused it — the
receipt is upright, and name and amount share one printed row.
"""
import pytest

from app.etl.nomi import nome_per_addendo, nomi_di_uno_scontrino


def frammento(testo, x, y, larghezza=60, altezza=20, pendenza=0.0):
    """An OCR fragment, optionally on a tilted receipt.

    The whole box is rotated, not just its top edge — the same shape
    PaddleOCR returns, and what `inclinazione` reads the tilt from.
    """
    dy = pendenza * larghezza
    return {"testo": testo,
            "box": [[x, y], [x + larghezza, y + dy],
                    [x + larghezza, y + dy + altezza], [x, y + altezza]]}


class TestStessaRiga:
    """What already worked must keep working."""

    def test_nome_a_sinistra_dell_importo(self):
        righe = [frammento("GUACAMOLE", 20, 100, larghezza=140),
                 frammento("3,95", 400, 100)]
        assert nome_per_addendo(righe, 110, 400, 20) == "GUACAMOLE"

    def test_scarta_cio_che_sta_a_destra_dell_importo(self):
        """A fragment further right belongs to another column, not to us."""
        righe = [frammento("GUACAMOLE", 20, 100, larghezza=140),
                 frammento("3,95", 400, 100),
                 frammento("IVA", 480, 100)]
        assert nome_per_addendo(righe, 110, 400, 20) == "GUACAMOLE"


class TestInclinazione:
    """A tilted photo must not pull in the row above or below.

    Measured on the project's material: the median tilt is 0 degrees, but the
    worst tenth sits at 2.1 and the maximum at 4.2. Across 400px that is
    15-30px of drop — a whole line of text.
    """

    def test_riga_giusta_su_scontrino_storto(self):
        p = 0.07                                   # ~4 degrees
        righe = [frammento("GUACAMOLE", 20, 100, larghezza=140, pendenza=p),
                 frammento("3,95", 400, 100 + p * 380, pendenza=p),
                 frammento("PANET", 20, 140, larghezza=140, pendenza=p),
                 frammento("1,14", 400, 140 + p * 380, pendenza=p)]
        nome = nome_per_addendo(righe, 100 + p * 380 + 10, 400, 20)
        assert nome == "GUACAMOLE"


class TestNomeSullaRigaSopra:
    """Weighed goods print the name above the amount. It is how they print."""

    def test_formato_a_peso(self):
        """    Pastanaga Granel
                 1,204   1,78   2,14
        """
        righe = [frammento("Pastanaga Granel", 20, 100, larghezza=180),
                 frammento("1,204", 60, 123),
                 frammento("1,78", 220, 123),
                 frammento("2,14", 400, 123)]
        assert nome_per_addendo(righe, 133, 400, 20) == "Pastanaga Granel"

    def test_non_risale_oltre_una_riga(self):
        """Two rows up is not a continuation, it is another product."""
        righe = [frammento("GUACAMOLE", 20, 60, larghezza=140),
                 frammento("3,95", 400, 60),
                 frammento("1,204", 60, 130),
                 frammento("2,14", 400, 130)]
        assert nome_per_addendo(righe, 140, 400, 20) is None


class TestNonSiRiusaUnNome:
    """The fourth guard.

    Two agents asked for it, one argued it was already covered by the
    "the row above must not carry an amount" guard. Measured on the data:
    that guard covers negative amounts (5% of receipts), while amounts
    closer than 1.5 rows to each other occur in 66%. On weighed formats the
    name row carries no amount, so it passes that guard and gets reused.
    """

    def test_un_nome_gia_assegnato_non_si_riusa(self):
        righe = [frammento("Pastanaga Granel", 20, 100, larghezza=180),
                 frammento("2,14", 400, 123),
                 frammento("3,50", 400, 146)]
        nomi = nomi_di_uno_scontrino(righe, [(2.14, 133), (3.50, 156)], 400, 20)
        assert nomi == ["Pastanaga Granel", None]

    def test_lo_stesso_prodotto_comprato_due_volte_tiene_il_nome(self):
        """45 receipts in the material print one product name twice, and both
        purchases are real. The guard is on the printed fragment, not on the
        string, so a second printing keeps its own name."""
        righe = [frammento("Cogombre", 20, 100, larghezza=140),
                 frammento("1,20", 400, 100),
                 frammento("Cogombre", 20, 140, larghezza=140),
                 frammento("1,20", 400, 140)]
        nomi = nomi_di_uno_scontrino(righe, [(1.20, 110), (1.20, 150)], 400, 20)
        assert nomi == ["Cogombre", "Cogombre"]

    def test_lo_sconto_non_eredita_il_prodotto(self):
        """PANE 2,50 / SCONTO 20% / -0,50 — the discount must not become
        a second "PANE", which would keep the total balancing while naming
        a product that was never bought twice."""
        righe = [frammento("PANE CASERECCIO", 20, 100, larghezza=160),
                 frammento("2,50", 400, 100),
                 frammento("SCONTO 20%", 20, 130, larghezza=140),
                 frammento("-0,50", 400, 160)]
        nomi = nomi_di_uno_scontrino(righe, [(2.50, 110), (-0.50, 170)], 400, 20)
        assert nomi[0] == "PANE CASERECCIO"
        assert nomi[1] != "PANE CASERECCIO"


class TestImportoNegativoSenzaNome:
    """The fifth guard: mark it, do not guess it.

    25 negative amounts over 19 receipts. Flagging keeps them checkable;
    borrowing a neighbour's name would not.
    """

    def test_negativo_senza_nome_resta_senza_nome(self):
        righe = [frammento("-0,50", 400, 160)]
        assert nome_per_addendo(righe, 170, 400, 20, importo=-0.50) is None
