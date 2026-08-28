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


def test_la_ricapitolazione_non_e_un_addendo():
    """
    Il totale stampato sopra il riepilogo non va sommato ai prodotti.

    E' il caso di `8fbdc7a3f4e5`: 2,99 + 2,99 + 1,62 + 1,62 = 9,22, e sotto
    l'elenco lo scontrino ristampa 9,22. Senza il filtro la somma esce 18,44,
    il doppio esatto.
    """
    righe = [
        {"testo": "LEGGING", "box": [[10, 50], [120, 50], [120, 68], [10, 68]]},
        {"testo": "2,99", "box": [[280, 50], [320, 50], [320, 68], [280, 68]]},
        {"testo": "LEGGING", "box": [[10, 70], [120, 70], [120, 88], [10, 88]]},
        {"testo": "2,99", "box": [[280, 70], [320, 70], [320, 88], [280, 88]]},
        {"testo": "Q.RALLADO", "box": [[10, 90], [120, 90], [120, 108], [10, 108]]},
        {"testo": "1,62", "box": [[280, 90], [320, 90], [320, 108], [280, 108]]},
        {"testo": "Q.RALLADO", "box": [[10, 110], [120, 110], [120, 128], [10, 128]]},
        {"testo": "1,62", "box": [[280, 110], [320, 110], [320, 128], [280, 128]]},
        # the receipt reprints the total just above the summary
        {"testo": "9,22", "box": [[280, 130], [320, 130], [320, 148], [280, 148]]},
        {"testo": "TARJETA", "box": [[10, 155], [120, 155], [120, 173], [10, 173]]},
    ]
    valori = [v for v, _ in addendi(righe)]
    assert 9.22 not in valori
    assert round(sum(valori), 2) == 9.22


def test_un_addendo_uguale_alla_somma_ma_non_ultimo_resta():
    """
    Il filtro guarda SOLO l'ultimo addendo. Un prodotto che per coincidenza
    vale quanto gli altri messi insieme, ma che non e' l'ultimo, e' merce.
    """
    righe = [
        {"testo": "PANE", "box": [[10, 50], [120, 50], [120, 68], [10, 68]]},
        {"testo": "2,00", "box": [[280, 50], [320, 50], [320, 68], [280, 68]]},
        {"testo": "VINO", "box": [[10, 70], [120, 70], [120, 88], [10, 88]]},
        {"testo": "2,00", "box": [[280, 70], [320, 70], [320, 88], [280, 88]]},
        {"testo": "OLIO", "box": [[10, 90], [120, 90], [120, 108], [10, 108]]},
        {"testo": "5,00", "box": [[280, 90], [320, 90], [320, 108], [280, 108]]},
        {"testo": "TOTAL", "box": [[10, 120], [120, 120], [120, 138], [10, 138]]},
    ]
    assert [v for v, _ in addendi(righe)] == [2.00, 2.00, 5.00]
