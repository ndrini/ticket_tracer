"""Tests for the enforced answer format."""
from app.etl.schema_risposta import (CAMPO_TOTALE, SCHEMA_SCONTRINO, normalizza,
                                     prezzo_di_riga, prompt_scontrino)


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


# Il prezzo di riga contro quello unitario: due importi sulla stessa riga.

SCONTRINO = "\n".join([
    "2 4 ESTAC.CONSUM 250 0,86 1,72",
    "1 MONGETA PLANA IK CO 1,50",
    "TOTAL 3,22",
])


def test_corregge_il_prezzo_unitario_con_quello_di_riga():
    """0,86 is what one unit costs; 1,72 is what the line costs."""
    assert prezzo_di_riga("ESTAC.CONSUM 250", 0.86, SCONTRINO) == 1.72


def test_lascia_stare_il_prezzo_gia_giusto():
    """If the model already picked the line amount, do not touch it."""
    assert prezzo_di_riga("ESTAC.CONSUM 250", 1.72, SCONTRINO) == 1.72


def test_non_tocca_una_riga_con_un_solo_importo():
    """One amount on the line: there is nothing to choose between."""
    assert prezzo_di_riga("MONGETA PLANA IK CO", 1.50, SCONTRINO) == 1.50


def test_non_scambia_per_prezzo_un_numero_dentro_il_nome():
    """The 250 in ESTAC.CONSUM 250 is part of the name, not a price."""
    assert prezzo_di_riga("ESTAC.CONSUM 250", 0.86, SCONTRINO) != 250.0


def test_non_corregge_se_il_nome_non_e_identificabile():
    """Two matching lines: which one is it? Leave the value alone."""
    ambiguo = "1 PANET 1,10 2,20\n1 PANET 1,10 2,20"
    assert prezzo_di_riga("PANET", 1.10, ambiguo) == 1.10


def test_senza_testo_dello_scontrino_non_corregge_nulla():
    """The correction needs the receipt: without it, keep what we were given."""
    assert prezzo_di_riga("ESTAC.CONSUM 250", 0.86, None) == 0.86


def test_sostituisce_un_prezzo_che_sulla_riga_non_esiste():
    """250 comes from the product name; 1,72 is what that line costs."""
    # 250 non compare come importo (nessun decimale), ma la riga e' certa:
    # si prende il suo ultimo importo.
    assert prezzo_di_riga("ESTAC.CONSUM", 250.0, SCONTRINO) == 1.72


def test_sostituisce_anche_quando_la_riga_ha_un_solo_importo():
    """1 4 ESTAC.CONSUM 250 0,86 — the 250 is the name, the price is 0,86."""
    riga = "1 4 ESTAC.CONSUM 250 0,86\nTOTAL 0,86"
    assert prezzo_di_riga("ESTAC.CONSUM", 250.0, riga) == 0.86


def test_scarta_un_prezzo_che_lo_scontrino_non_stampa():
    """A phone number is not a price: the line must be dropped, not guessed."""
    testo = "TELEFONO VIA LAIETANA 651317190\nBARRA DE PA 0,45\nTOTAL 0,45"
    assert prezzo_di_riga("TELEFONO VIA LAIETANA", 651317190.0, testo) is None


def test_il_prodotto_col_prezzo_inventato_sparisce():
    """Better a declared hole than a number nobody read."""
    testo = "TELEFONO VIA LAIETANA 651317190\nBARRA DE PA 0,45\nTOTAL 0,45"
    risposta = {
        "shop_name": None,
        CAMPO_TOTALE: 0.45,
        "items": [
            {"name": "TELEFONO VIA LAIETANA", "price": 651317190.0},
            {"name": "BARRA DE PA", "price": 0.45},
        ],
    }
    prodotti = normalizza(risposta, testo)["items"]
    assert [p["name"] for p in prodotti] == ["BARRA DE PA"]
