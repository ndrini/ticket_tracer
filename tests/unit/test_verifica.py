"""Tests for the phase B check: item sum against the printed total."""
from app.etl.verifica import (RIGHE_ASSENTI, SCARTO_ECCESSIVO, TOTALE_ASSENTE,
                              VALIDO, somma_righe, verifica)


def riga(testo, x, y, larghezza=60, altezza=20):
    """An OCR fragment as Phase A records it."""
    return {"testo": testo,
            "box": [[x, y], [x + larghezza, y], [x + larghezza, y + altezza],
                    [x, y + altezza]]}


def scontrino(voci, totale=None, y_totale=400):
    """Prodotti (nome, importo) piu' la riga di totale."""
    righe = []
    for i, (nome, importo) in enumerate(voci):
        y = 100 + i * 30
        righe.append(riga(nome, 20, y, larghezza=140))
        righe.append(riga(importo, 400, y, larghezza=50))
    if totale is not None:
        righe.append(riga("TOTAL", 250, y_totale, larghezza=50))
        righe.append(riga(totale, 400, y_totale - 3, larghezza=50))
    return righe


class TestSommaRighe:
    def test_somma_la_colonna_di_destra(self):
        righe = scontrino([("1 PANET", "1,12"), ("1 GUACAMOLE", "3,95")],
                          totale="5,07")
        assert somma_righe(righe) == 5.07

    def test_ignora_la_colonna_dei_prezzi_unitari(self):
        """Su una riga con quantita' ci sono due numeri: conta solo l'ultimo.

        "2 PANET 1,14 2,28" vale 2,28, non 3,42."""
        righe = [riga("2 PANET 11 UN", 20, 100, larghezza=140),
                 riga("1,14", 300, 100, larghezza=50),
                 riga("2,28", 430, 100, larghezza=50),
                 riga("TOTAL", 250, 300, larghezza=50),
                 riga("2,28", 430, 297, larghezza=50)]
        assert somma_righe(righe) == 2.28

    def test_esclude_il_totale_dalla_somma(self):
        """L'etichetta TOTAL e il suo importo stanno sulla stessa riga fisica ma
        a y leggermente diverse: senza l'arretramento del confine il totale
        veniva sommato ai prodotti."""
        righe = scontrino([("1 PANET", "1,12"), ("1 PA", "2,00")], totale="3,12")
        assert somma_righe(righe) == 3.12

    def test_esclude_la_tabella_iva(self):
        """Sotto il totale c'e' il dettaglio IVA, con importi veri ma non prodotti."""
        righe = scontrino([("1 PANET", "1,12")], totale="1,12", y_totale=300)
        righe += [riga("BASE IMPOSABLE", 20, 400, larghezza=140),
                  riga("1,02", 400, 400, larghezza=50),
                  riga("IVA", 20, 430, larghezza=40),
                  riga("0,10", 400, 430, larghezza=50)]
        assert somma_righe(righe) == 1.12


class TestVerifica:
    def test_scontrino_che_quadra(self):
        righe = scontrino([("1 PANET", "1,12"), ("1 GUACAMOLE", "3,95")],
                          totale="5,07")
        esito = verifica(righe)
        assert esito["esito"] == VALIDO
        assert esito["scarto"] == 0.0

    def test_scontrino_che_non_quadra(self):
        righe = scontrino([("1 PANET", "1,12"), ("1 GUACAMOLE", "3,95")],
                          totale="9,99")
        esito = verifica(righe)
        assert esito["esito"] == SCARTO_ECCESSIVO
        assert esito["somma_righe"] == 5.07
        assert esito["totale_dichiarato"] == 9.99

    def test_tolleranza_sugli_arrotondamenti(self):
        """Uno scarto di un centesimo non e' un errore di estrazione."""
        righe = scontrino([("1 PANET", "1,12"), ("1 PA", "2,00")], totale="3,13")
        assert verifica(righe)["esito"] == VALIDO

    def test_totale_non_individuabile(self):
        righe = scontrino([("1 PANET", "1,12")])
        assert verifica(righe)["esito"] == TOTALE_ASSENTE

    def test_nessuna_riga(self):
        assert verifica([])["esito"] in (TOTALE_ASSENTE, RIGHE_ASSENTI)
