"""
Prove per la lettura della data dallo scontrino.

I casi vengono da scontrini veri: la data e' il campo che regge i report per
mese e per anno, e senza di essa uno scontrino corretto resta inutilizzabile.
"""
import pytest

from app.etl.estrattore import EstrattoreScontrino


@pytest.fixture
def estrattore():
    return EstrattoreScontrino()


@pytest.mark.parametrize("testo, atteso", [
    ("20/05/2025 19:51 0P:4164678", "2025-05-20"),
    ("13.01.2025 18:02:31", "2025-01-13"),
    ("C:4419 03/000009 09.06.2025 12:23 284493", "2025-06-09"),
    ("11/12/2024 18:57 0P:2040841", "2024-12-11"),
    # L'OCR perde i separatori e lascia degli spazi.
    ("04 06 2025 11 18 15", "2025-06-04"),
    ("30.06 2025 16 26:30", "2025-06-30"),
])
def test_legge_le_date_reali(estrattore, testo, atteso):
    assert estrattore.data(testo) == atteso


def test_non_costruisce_date_a_cavallo_di_due_righe():
    """L'errore che rendeva inutile il 66% degli scontrini: l'importo della riga
    sopra si attaccava alla data sotto, e "0,56" + "20/05/2025" diventava la
    data inesistente 56/20/05."""
    testo = "PA DE PAGES 0,56\n20/05/2025 19:51"
    assert EstrattoreScontrino().data(testo) == "2025-05-20"


def test_preferisce_l_anno_a_quattro_cifre():
    """Su uno scontrino reale il codice "03/03/04" precedeva la data vera
    "06/06/2025" e vinceva, datando l'acquisto al 2004."""
    testo = "OP: 03/03/04 cassa 2\nData 06/06/2025"
    assert EstrattoreScontrino().data(testo) == "2025-06-06"


@pytest.mark.parametrize("testo", [
    "08030 - BARCELONA - 93 834 22 65",   # codice postale e telefono
    "Llei 7/2022, inclouen en el preu",   # riferimento di legge
    "IVA 21/00/00",                       # aliquota
    "+34 933 56 06 32",                   # telefono con prefisso
    "TEL: 931 22 76 64",
    "93 12 04 95",                        # telefono che somiglia a una data
])
def test_non_scambia_i_codici_per_date(estrattore, testo):
    """Cio' che cade fuori dagli anni possibili non e' una data: le fotografie
    non contengono scontrini anteriori al 2015.

    I numeri di telefono sono il caso piu' insidioso, perche' hanno la stessa
    forma di una data separata da spazi. Misurato: nelle 18 righe dove lo
    spazio separava tre gruppi di cifre, la maggioranza erano telefoni."""
    letta = estrattore.data(testo)
    assert letta is None or letta[:4] >= "2015"


def test_lo_spazio_vale_solo_con_l_anno_esteso():
    """Con l'anno a due cifre lo spazio come separatore trasformerebbe ogni
    numero di telefono in una data. Con quattro cifre no: un telefono non
    contiene un gruppo di quattro cifre che valga come anno."""
    e = EstrattoreScontrino()
    assert e.data("07 08 2025 1957460") == "2025-08-07"
    assert e.data("93 12 04 95") is None


def test_senza_data_restituisce_none(estrattore):
    assert estrattore.data("PA DE PAGES 1,20\nTOTAL 1,20") is None


def test_testo_vuoto(estrattore):
    assert estrattore.data("") is None
    assert estrattore.data(None) is None
