"""Tests for the enforced answer format."""
from app.etl.schema_risposta import (CAMPO_TOTALE, SCHEMA_SCONTRINO, normalizza,
                                     prompt_scontrino)


def test_il_totale_ammette_null():
    """A receipt whose total is unreadable must be able to say so."""
    tipi = SCHEMA_SCONTRINO["properties"][CAMPO_TOTALE]["type"]
    assert "null" in tipi


def test_lo_schema_vieta_campi_inventati():
    """The model must not add fields the pipeline does not know."""
    assert SCHEMA_SCONTRINO["additionalProperties"] is False
    voce = SCHEMA_SCONTRINO["properties"]["items"]["items"]
    assert voce["additionalProperties"] is False
    assert voce["required"] == ["name", "price"]


def test_il_testo_precede_la_domanda():
    """The receipt goes first so the prefix cache survives across receipts."""
    prompt = prompt_scontrino("1 GUACAMOLE 3,35")
    assert prompt.index("1 GUACAMOLE 3,35") < prompt.index("Estrai i dati")


def test_scarta_i_prodotti_ripetuti():
    """The model repeats the whole list: counting it twice doubles the sum."""
    risposta = {
        "shop_name": "Consum",
        CAMPO_TOTALE: 10.18,
        "items": [
            {"name": "MONGETA PLANA", "price": 1.50},
            {"name": "GUACAMOLE", "price": 3.35},
            {"name": "MONGETA PLANA", "price": 1.50},
            {"name": "GUACAMOLE", "price": 3.35},
        ],
    }
    prodotti = normalizza(risposta)["items"]
    assert len(prodotti) == 2
    assert sum(p["price"] for p in prodotti) == 4.85


def test_due_unita_dello_stesso_prodotto_a_prezzi_diversi_restano():
    """Same name, different price: those are two real lines, not a repeat."""
    risposta = {
        "shop_name": None,
        CAMPO_TOTALE: None,
        "items": [
            {"name": "PANET", "price": 1.10},
            {"name": "PANET", "price": 2.20},
        ],
    }
    assert len(normalizza(risposta)["items"]) == 2


def test_un_totale_assente_resta_assente():
    """No total means None, never a number made up downstream."""
    assert normalizza({"shop_name": "X", CAMPO_TOTALE: None, "items": []})[CAMPO_TOTALE] is None


def test_una_risposta_illeggibile_non_fa_cadere_la_pipeline():
    """A truncated answer costs one receipt, not the whole run."""
    vuoto = normalizza(None)
    assert vuoto["items"] == []
    assert vuoto[CAMPO_TOTALE] is None


def test_scarta_le_voci_senza_nome_o_senza_prezzo():
    """Half a product is not a product."""
    risposta = {
        "shop_name": None,
        CAMPO_TOTALE: None,
        "items": [
            {"name": "", "price": 1.0},
            {"name": "GUACAMOLE", "price": None},
            {"name": "PANET", "price": 1.10},
        ],
    }
    prodotti = normalizza(risposta)["items"]
    assert [p["name"] for p in prodotti] == ["PANET"]
