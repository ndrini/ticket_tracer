"""Tests per la normalizzazione dei commercianti (app/etl/negozio.py)."""
from app.etl.negozio import normalizza_nome_negozio


def test_normalizzazione_mercadona():
    canonico, alias = normalizza_nome_negozio("MERCADUNA")
    assert canonico == "Mercadona"
    assert alias == "MERCADUNA"

    canonico_2, _ = normalizza_nome_negozio("Mercadona S.A.")
    assert canonico_2 == "Mercadona"


def test_normalizzazione_consum():
    canonico, alias = normalizza_nome_negozio("RUME SUPERMETCATS, SL")
    assert canonico == "Consum"
    assert alias == "RUME SUPERMETCATS, SL"

    canonico_charter, _ = normalizza_nome_negozio("CHARTER LLULL")
    assert canonico_charter == "Consum"


def test_normalizzazione_cal_fruitos():
    canonico, _ = normalizza_nome_negozio("CAL FRUIT NILDA")
    assert canonico == "Cal Fruitos"


def test_negozio_sconosciuto_o_generico():
    canonico, _ = normalizza_nome_negozio("")
    assert canonico == "Sconosciuto"

    canonico_altro, alias_altro = normalizza_nome_negozio("Panaderia Garcia")
    assert canonico_altro == "Panaderia Garcia"
