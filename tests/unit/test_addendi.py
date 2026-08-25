"""Tests for what counts as a product: the totals' addends."""
import json
import glob

from app.etl.addendi import addendi, confine_somma, e_addendo, e_sconto


def frammento(testo, x, y, larghezza=60, altezza=20):
    """An OCR fragment with a box around (x, y)."""
    return {"testo": testo,
            "box": [[x, y], [x + larghezza, y], [x + larghezza, y + altezza], [x, y + altezza]]}


def scontrino():
    """Two products in the right-hand column, then the summary block."""
    return [
        frammento("BARRA DE PA", 20, 100),
        frammento("0,45", 300, 100),
        frammento("GUACAMOLE", 20, 140),
        frammento("3,35", 300, 140),
        frammento("TOTAL", 20, 200),
        frammento("3,80", 300, 200),
        frammento("Base imposable", 20, 240),
        frammento("3,45", 300, 240),
    ]


def test_gli_addendi_sommano_al_totale():
    """The definition: a product is what contributes an addend."""
    assert round(sum(v for v, _ in addendi(scontrino())), 2) == 3.80


def test_il_riepilogo_non_e_un_addendo():
    """Below TOTAL there is no merchandise: IVA and change do not sum."""
    valori = [v for v, _ in addendi(scontrino())]
    assert 3.80 not in valori and 3.45 not in valori


def test_un_codice_col_prezzo_giusto_e_un_prodotto():
    """The name is not the criterion: SAMARRETA-0483123 is real merchandise."""
    righe = [
        frammento("SAMARRETA-0483123", 20, 100),
        frammento("3,49", 300, 100),
        frammento("TOTAL", 20, 200),
        frammento("3,49", 300, 200),
    ]
    assert [v for v, _ in addendi(righe)] == [3.49]


def test_un_numero_fuori_colonna_non_e_un_addendo():
    """A phone number in the body is not in the column that sums."""
    righe = [
        frammento("BARRA DE PA", 20, 100),
        frammento("0,45", 300, 100),
        frammento("PANET", 20, 140),
        frammento("1,10", 300, 140),
        frammento("93,30", 900, 170),  # far right: another receipt
        frammento("TOTAL", 20, 220),
        frammento("1,55", 300, 220),
    ]
    assert 93.30 not in [v for v, _ in addendi(righe)]


def test_il_confine_regge_una_coda_lunga():
    """IKEA prints half a page of return terms: the boundary must not slide."""
    righe = [
        frammento("OVERMATT", 20, 100),
        frammento("4,00", 300, 100),
        frammento("Total", 20, 160),
        frammento("4,00", 300, 160),
    ] + [frammento("condicions de venda i devolucions", 20, 300 + 40 * i)
         for i in range(20)]
    assert [v for v, _ in addendi(righe)] == [4.00]


def test_uno_sconto_si_riconosce_dal_segno():
    """A negative addend is a discount, not merchandise."""
    assert e_sconto(-4.51)
    assert not e_sconto(3.35)


def test_e_addendo_risponde_su_un_prezzo():
    """Given a price, is it one of the receipt's addends?"""
    righe = scontrino()
    assert e_addendo(0.45, righe)
    assert not e_addendo(99.99, righe)


def test_sul_caso_ikea_validato_a_mano():
    """The IKEA receipt the user read by hand: 8 articles, total 52,00."""
    percorsi = glob.glob("data/estratti/152cf78ab94f*.json")
    if not percorsi:
        return  # il materiale non e' versionato
    righe = json.load(open(percorsi[0]))["righe_ocr"]
    assert round(sum(v for v, _ in addendi(righe)), 2) == 52.00
