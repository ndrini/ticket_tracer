"""Tests for rebuilding OCR fragments into printed lines."""
from app.etl import righe_logiche
from app.etl.righe_logiche import inclinazione, ricomponi


def frammento(testo, x, y, larghezza=60, altezza=20, pendenza=0.0):
    """
    An OCR fragment, optionally on a tilted receipt.

    The whole box is rotated, not just its top edge: PaddleOCR returns boxes
    that follow the text, and `inclinazione` reads the tilt from their shape.
    """
    dy = pendenza * larghezza
    return {"testo": testo,
            "box": [[x, y], [x + larghezza, y + dy],
                    [x + larghezza, y + dy + altezza], [x, y + altezza]]}


class TestRicomponi:
    def test_frammenti_sulla_stessa_altezza(self):
        """Nome e prezzo stanno lontani sulla carta ma sulla stessa riga."""
        righe = [frammento("1 PANET 11 UN", 20, 100, larghezza=140),
                 frammento("1,14", 400, 100)]
        assert ricomponi(righe) == ["1 PANET 11 UN 1,14"]

    def test_ordina_da_sinistra_a_destra(self):
        """Il testo va ricomposto nell'ordine in cui si legge, non di arrivo."""
        righe = [frammento("1,14", 400, 100),
                 frammento("1 PANET", 20, 100, larghezza=140)]
        assert ricomponi(righe) == ["1 PANET 1,14"]

    def test_righe_distinte_restano_distinte(self):
        righe = [frammento("1 PANET", 20, 100), frammento("1,14", 400, 100),
                 frammento("1 GUACAMOLE", 20, 140), frammento("3,95", 400, 140)]
        assert ricomponi(righe) == ["1 PANET 1,14", "1 GUACAMOLE 3,95"]

    def test_scontrino_inclinato(self):
        """Su una foto storta i frammenti a destra scivolano in basso.

        Con 6 gradi di inclinazione, su 380 px di distanza il dislivello supera
        i 40 px, molto piu' dell'altezza di una riga: senza seguire la pendenza
        la riga si spezzerebbe in due."""
        pend = 0.105          # circa 6 gradi
        righe = [frammento("1 PANET", 20, 100, larghezza=140, pendenza=pend),
                 frammento("1,14", 400, 100 + pend * 380, pendenza=pend),
                 frammento("1 GUACAMOLE", 20, 140, larghezza=140, pendenza=pend),
                 frammento("3,95", 400, 140 + pend * 380, pendenza=pend)]
        assert ricomponi(righe) == ["1 PANET 1,14", "1 GUACAMOLE 3,95"]

    def test_ordine_dall_alto_in_basso(self):
        righe = [frammento("SECONDA", 20, 200), frammento("PRIMA", 20, 100)]
        assert ricomponi(righe) == ["PRIMA", "SECONDA"]

    def test_nessun_frammento(self):
        assert ricomponi([]) == []


class TestInclinazione:
    def test_scontrino_dritto(self):
        righe = [frammento("A", 20, 100), frammento("B", 200, 100),
                 frammento("C", 20, 140), frammento("D", 200, 140)]
        assert abs(inclinazione(righe)) < 0.02

    def test_scontrino_storto(self):
        pend = 0.1
        righe = [frammento("A", 20, 100, pendenza=pend),
                 frammento("B", 200, 118, pendenza=pend),
                 frammento("C", 20, 140, pendenza=pend),
                 frammento("D", 200, 158, pendenza=pend)]
        assert inclinazione(righe) > 0.05

    def test_troppo_pochi_frammenti(self):
        assert inclinazione([frammento("A", 0, 0)]) == 0.0


class TestTestoRicomposto:
    def test_una_riga_per_riga_stampata(self):
        righe = [frammento("1 PANET", 20, 100), frammento("1,14", 400, 100),
                 frammento("TOTAL", 20, 200), frammento("1,14", 400, 200)]
        assert righe_logiche.testo_ricomposto(righe) == "1 PANET 1,14\nTOTAL 1,14"


def test_ricuce_nome_e_importo_su_righe_diverse():
    """IKEA prints a product over two lines: name and price come back joined."""
    righe_ocr = [
        frammento("OVERMATT N campana", 20, 100),
        frammento("4,00", 300, 130),
        frammento("BLANDA BLANK bol", 20, 180),
        frammento("8,00", 300, 210),
        frammento("TOTAL", 20, 300),
        frammento("12,00", 300, 300),
    ]
    righe = righe_logiche.testo_ricomposto(righe_ocr).splitlines()
    assert any("OVERMATT N campana" in r and "4,00" in r for r in righe)
    assert any("BLANDA BLANK bol" in r and "8,00" in r for r in righe)


def test_non_ricuce_una_riga_gia_completa():
    """A line that already carries its price must not swallow the next one."""
    righe_ocr = [
        frammento("3 CERVESA ESP LLAUNA", 20, 100),
        frammento("1,02", 300, 100),
        frammento("2 MOZZARELLA FRESCA", 20, 160),
        frammento("1,94", 300, 160),
        frammento("TOTAL", 20, 260),
        frammento("2,96", 300, 260),
    ]
    righe = righe_logiche.testo_ricomposto(righe_ocr).splitlines()
    assert any("CERVESA" in r and "1,02" in r and "MOZZARELLA" not in r
               for r in righe)


def test_non_ricuce_sotto_il_confine_del_riepilogo():
    """Below TOTAL there are no products: the IVA table must stay apart."""
    righe_ocr = [
        frammento("PANET INTEGRAL", 20, 100),
        frammento("1,10", 300, 100),
        frammento("TOTAL", 20, 200),
        frammento("1,10", 300, 200),
        frammento("Base imposable", 20, 260),
        frammento("1,00", 300, 290),
    ]
    righe = righe_logiche.testo_ricomposto(righe_ocr).splitlines()
    assert not any("Base imposable" in r and "1,00" in r for r in righe)


def test_non_ricuce_un_importo_fuori_dalla_colonna_dei_prezzi():
    """A price from the receipt photographed alongside must not be stitched in."""
    righe_ocr = [
        frammento("BARRA DE PA", 20, 100),
        frammento("0,45", 300, 100),
        frammento("FORMATGE RATLLAT", 20, 160),
        frammento("1,30", 300, 160),
        frammento("GUACAMOLE", 20, 220),
        # Far to the right: this belongs to the receipt photographed alongside.
        frammento("9,99", 1200, 250),
        frammento("TOTAL", 20, 320),
        frammento("1,75", 300, 320),
    ]
    righe = righe_logiche.testo_ricomposto(righe_ocr).splitlines()
    assert not any("GUACAMOLE" in r and "9,99" in r for r in righe)
