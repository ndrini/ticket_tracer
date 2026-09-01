"""Tests per i template di layout geometrici delle catene (app/etl/template_catena.py)."""
from app.etl.template_catena import ottieni_profilo_catena


def test_riconoscimento_profilo_mercadona():
    profilo = ottieni_profilo_catena("MERCADUNA BARCELONA")
    assert profilo is not None
    assert profilo["x_prezzi_min_rel"] == 0.78


def test_riconoscimento_profilo_consum():
    profilo = ottieni_profilo_catena("CHARTER LLULL")
    assert profilo is not None
    assert profilo["ha_prodotti_a_peso_riga_sopra"] is True


def test_negozio_senza_profilo_dedicato():
    profilo = ottieni_profilo_catena("Panaderia Local")
    assert profilo is None
