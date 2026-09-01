"""Tests for document classification (POS pure vs receipt)."""
from app.etl.documento import tipo_documento


def riga(testo):
    return {"testo": testo, "box": [[0, 0], [10, 0], [10, 10], [0, 10]]}


def test_scontrino_spesa_normale():
    righe = [
        riga("MERCADONA"),
        riga("PAN DE MOLDE 1,20"),
        riga("LECHE ENTERA 0,90"),
        riga("TOTAL 2,10"),
    ]
    assert tipo_documento(righe) == "SCONTRINO_SPESA"


def test_ricevuta_pos_pura():
    righe = [
        riga("BBVA BARCELONA"),
        riga("TERMINAL 334150042"),
        riga("VENTA VISA CREDIT"),
        riga("OPERACION CONTACTLESS"),
        riga("AUT 808953"),
        riga("45,60 EUR"),
    ]
    assert tipo_documento(righe) == "PAGAMENTO_ELETTRONICO"


def test_scontrino_spesa_con_sezione_pos_in_fondo():
    righe = [
        riga("KIABI DIAGO"),
        riga("CAMISETA 15,00"),
        riga("PANTALON 25,00"),
        riga("TOTAL 40,00"),
        riga("TARJETA CONTACTLESS"),
        riga("TERMINAL 0001 CAJA 542"),
    ]
    assert tipo_documento(righe) == "SCONTRINO_SPESA"
