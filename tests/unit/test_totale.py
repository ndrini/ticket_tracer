"""Tests for finding the printed total on a receipt."""
from app.etl.totale import trova_totale


def riga(testo, x, y, larghezza=60, altezza=20):
    """An OCR fragment as Phase A records it."""
    return {"testo": testo,
            "box": [[x, y], [x + larghezza, y], [x + larghezza, y + altezza],
                    [x, y + altezza]]}


class TestTrovaTotale:
    def test_importo_a_destra_dell_etichetta(self):
        """Il caso normale: etichetta a sinistra, cifra a destra sulla stessa riga.

        L'OCR le restituisce come frammenti separati, ed e' la disposizione di
        gran lunga piu' frequente sugli scontrini reali."""
        righe = [riga("Total factura:", 10, 100), riga("28,80", 200, 100)]
        assert trova_totale(righe) == 28.80

    def test_importo_sulla_stessa_riga(self):
        righe = [riga("TOTAL 15,50", 10, 50, larghezza=120)]
        assert trova_totale(righe) == 15.50

    def test_reso_con_totale_negativo(self):
        """Un reso e' un dato valido: il segno va conservato, non ignorato."""
        righe = [riga("Total", 10, 440, larghezza=50), riga("-58.98", 230, 442)]
        assert trova_totale(righe) == -58.98

    def test_prosa_che_contiene_la_parola_totale(self):
        """"...lograr un silencio total" non e' un totale.

        Caso reale trovato sugli scontrini: senza il limite di lunghezza, la
        frase di cortesia veniva scambiata per un'etichetta e l'importo vicino
        per il totale dello scontrino."""
        righe = [riga("lograr un silencio total en la zona comun", 10, 10,
                      larghezza=400),
                 riga("4,00", 420, 12)]
        assert trova_totale(righe) is None

    def test_conteggio_articoli_non_e_un_importo(self):
        """"Total articles: 5" conta pezzi, non euro.

        Su uno scontrino IKEA vinceva sul totale vero perche' compare per
        ultimo, restituendo un totale di pochi centesimi."""
        righe = [riga("Total", 10, 100, larghezza=50), riga("58,98", 230, 100),
                 riga("Total articles:", 10, 130, larghezza=110),
                 riga("5", 230, 130, larghezza=20)]
        assert trova_totale(righe) == 58.98

    def test_sceglie_l_ultimo_totale(self):
        """Subtotale prima, totale definitivo dopo: vince quello conclusivo."""
        righe = [riga("Total", 10, 100, larghezza=50), riga("10,00", 200, 100),
                 riga("Total", 10, 200, larghezza=50), riga("12,50", 200, 200)]
        assert trova_totale(righe) == 12.50

    def test_nessuna_etichetta(self):
        assert trova_totale([riga("PANET 11 UN", 10, 10), riga("1,14", 200, 10)]) is None

    def test_righe_vuote(self):
        assert trova_totale([]) is None
        assert trova_totale(None) is None
