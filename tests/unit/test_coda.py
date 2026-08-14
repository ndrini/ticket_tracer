"""
Prove per la separazione fra corpo e coda dello scontrino.

I casi di testo sono TUTTI presi da scontrini veri, con le loro storpiature
OCR: sono la ragione per cui il confronto per parole intere non funzionava.
"""
import pytest

from app.etl import coda


def riga(testo, y, x=10, h=20):
    """Un frammento OCR come lo produce la Fase A."""
    return {"testo": testo,
            "box": [[x, y], [x + 100, y], [x + 100, y + h], [x, y + h]]}


# --- somiglianza con i marcatori di riepilogo ---------------------------------

@pytest.mark.parametrize("testo", [
    "SUBIOLAL 3,99",        # subtotal
    "CAM8IO €",             # cambio, con una cifra al posto di una lettera
    "IMPORIO PAGAIO",       # importo pagato
    "€* TOT",               # totale abbreviato
    "EFECTIVO_ 50.00",
    "€CAMILO_ 13.31",       # cambio
    "Pago en efoctivo",
    "LIURAMENT EFECTIU",
    "DEVOLUCIÓ",
    "Bonificacton: €",
    "IMPORTE:  EUR",
    "5UMA",                 # suma
])
def test_riconosce_i_marcatori_storpiati(testo):
    assert coda.sa_di_riepilogo(testo)


@pytest.mark.parametrize("testo", [
    "IOGURT AMB FRUITES 2,00",
    "PENNE INTEGRAL 2,42",
    "PASTA BONPREU FIDEUA 0,79",
    "SCAMORZA CONSORC 3,73",
    "MADUIXOT LA COLLITA 2,79",
    "BRIE PUNTAS AUCH 1,74",
    "VINO CATEDRAL LE 1,55",
    "PA OVALAT RUSTIK BAK 2,83",
    "MINI BURGER VEDELLA 7,90",
    "OUS ECOL-GICS BONPRE 5,30",
    "PASTISSET BLAT D MOR",
    "MONGETA BLANCA CUITA",
    "ESTAC.CONSUM 250",
    "GORGONZOLA DOP",
])
def test_non_scambia_i_prodotti_per_riepilogo(testo):
    """La somiglianza deve essere abbastanza stretta da lasciar stare i nomi
    di prodotto, che su uno scontrino della spesa sono la maggioranza."""
    assert not coda.sa_di_riepilogo(testo)


# --- confine geometrico -------------------------------------------------------

def test_confine_sotto_l_ultima_etichetta_di_totale():
    """Il confine sta all'altezza del totale, non della prima etichetta: le
    parole "total" compaiono anche in blocchi intermedi."""
    righe = [riga("PA DE PAGES 1,20", 100),
             riga("TOTAL ARTICLES 3", 200),
             riga("IOGURT 2,00", 300),
             riga("TOTAL 3,20", 400),
             riga("EFECTIU 5,00", 500)]
    y = coda.confine_coda(righe)
    assert y is not None
    assert 300 < y < 420


def test_senza_etichette_non_c_e_confine():
    assert coda.confine_coda([riga("PA DE PAGES 1,20", 100)]) is None


def test_righe_corpo_scarta_la_coda():
    righe = [riga("PA DE PAGES 1,20", 100),
             riga("IOGURT 2,00", 200),
             riga("TOTAL 3,20", 300),
             riga("EFECTIU 5,00", 400),
             riga("CANVI 1,80", 500)]
    corpo = [r["testo"] for r in coda.righe_corpo(righe)]
    assert "PA DE PAGES 1,20" in corpo
    assert "IOGURT 2,00" in corpo
    assert "EFECTIU 5,00" not in corpo
    assert "CANVI 1,80" not in corpo


def test_non_taglia_se_resterebbe_quasi_niente():
    """Caso di rottura previsto: il totale stampato IN CIMA. Tagliare sotto di
    esso butterebbe via l'intero scontrino, quindi si preferisce non tagliare:
    qualche riga di coda in piu' e' meno grave della perdita dei prodotti."""
    righe = ([riga("TOTAL 12,00", 50)]
             + [riga(f"PRODOTTO {i} 1,00", 100 + i * 50) for i in range(10)])
    assert len(coda.righe_corpo(righe)) == len(righe)


def test_righe_corpo_regge_l_elenco_vuoto():
    assert coda.righe_corpo([]) == []


# --- importo impossibile ------------------------------------------------------

def test_scarta_l_importo_maggiore_del_totale():
    assert coda.importo_impossibile(50.00, 36.69)


def test_tiene_l_importo_uguale_al_totale():
    """Il confronto e' stretto. Su uno scontrino di un solo prodotto (totale
    1,72, riga "ESTAC.CONSUM 250" a 1,72) il prodotto E' il totale, e scartarlo
    azzererebbe uno scontrino corretto. I casi ambigui li decide la geometria.
    Misurato: con `>=` si risolveva 1 caso e se ne rompevano 2."""
    assert not coda.importo_impossibile(1.72, 1.72)


def test_il_reso_negativo_resta_confrontabile():
    """I resi sono importi negativi legittimi: conta il valore assoluto."""
    assert not coda.importo_impossibile(-2.00, -58.98)
    assert coda.importo_impossibile(-99.00, 10.00)


def test_senza_totale_non_si_giudica():
    assert not coda.importo_impossibile(5.00, None)
