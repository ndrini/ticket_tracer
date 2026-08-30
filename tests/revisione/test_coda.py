"""
The review queue: which receipts to look at, in which order.

Only the ordering logic is tested. The HTML is left out on purpose: it is
checked by using it, while the order is what decides whether the human's time
goes to the right receipts.
"""
import sqlite3

import pytest

from app.revisione.coda import Sospetto, costruisci_coda


@pytest.fixture
def db(tmp_path):
    percorso = tmp_path / "prova.db"
    c = sqlite3.connect(percorso)
    c.executescript("""
        CREATE TABLE receipts (id INTEGER PRIMARY KEY, image_sha256 TEXT,
            validation_status TEXT, validation_delta REAL, foto_origine TEXT,
            extraction_confidence REAL DEFAULT 0.0);
        CREATE TABLE receipt_lines (id INTEGER PRIMARY KEY, receipt_id INTEGER,
            product_id INTEGER, total_price REAL, verified_by_human BOOLEAN DEFAULT 0);
        CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE manual_review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_id INTEGER NOT NULL,
            reason TEXT NOT NULL, extraction_method TEXT, errors TEXT,
            priority INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP, completed_at TIMESTAMP, reviewed_by TEXT,
            review_notes TEXT, action_taken TEXT);
    """)
    c.commit()
    return c


def aggiungi(c, id, stato, righe, delta=None):
    c.execute("INSERT INTO receipts (id, image_sha256, validation_status, "
              "validation_delta) VALUES (?,?,?,?)", (id, f"sha{id}", stato, delta))
    for i in range(righe):
        c.execute("INSERT INTO receipt_lines (receipt_id, total_price) VALUES (?,?)",
                  (id, 1.0))
    c.commit()


def test_zero_righe_viene_prima_di_tutto(db):
    aggiungi(db, 1, "VALIDO", 5)
    aggiungi(db, 2, "VALIDO", 0)
    coda = costruisci_coda(db)
    assert coda[0].receipt_id == 2
    assert coda[0].sospetto is Sospetto.TAGLIO


def test_una_riga_e_sospetto_di_taglio(db):
    aggiungi(db, 1, "VALIDO", 1)
    coda = costruisci_coda(db)
    assert coda[0].sospetto is Sospetto.TAGLIO


def test_gli_scontrini_validi_e_pieni_non_entrano_in_coda(db):
    aggiungi(db, 1, "VALIDO", 6)
    assert costruisci_coda(db) == []


def test_chi_non_quadra_e_sospetto_di_estrazione(db):
    aggiungi(db, 1, "SOMMA_IN_ECCESSO", 5, delta=12.0)
    coda = costruisci_coda(db)
    assert coda[0].sospetto is Sospetto.ESTRAZIONE


def test_fra_due_che_non_quadrano_prima_il_delta_piu_grande(db):
    aggiungi(db, 1, "SOMMA_IN_DIFETTO", 5, delta=3.0)
    aggiungi(db, 2, "SOMMA_IN_DIFETTO", 5, delta=300.0)
    coda = costruisci_coda(db)
    assert [v.receipt_id for v in coda] == [2, 1]


def test_il_taglio_batte_l_estrazione_anche_con_delta_enorme(db):
    """Order matters: a bad crop invalidates the data, so asking about the
    figures first would waste the reviewer's time."""
    aggiungi(db, 1, "SOMMA_IN_ECCESSO", 5, delta=671.0)
    aggiungi(db, 2, "VALIDO", 0)
    assert [v.receipt_id for v in costruisci_coda(db)] == [2, 1]


def test_totale_assente_va_in_fondo_come_non_verificabile(db):
    aggiungi(db, 1, "TOTALE_ASSENTE", 5)
    aggiungi(db, 2, "SOMMA_IN_DIFETTO", 5, delta=1.0)
    coda = costruisci_coda(db)
    assert [v.receipt_id for v in coda] == [2, 1]
    assert coda[1].sospetto is Sospetto.NON_VERIFICABILE


def test_chi_e_gia_stato_rivisto_esce_dalla_coda(db):
    aggiungi(db, 1, "VALIDO", 0)
    db.execute("INSERT INTO manual_review_queue (receipt_id, reason, completed_at) "
               "VALUES (1, 'taglio', '2026-08-29')")
    db.commit()
    assert costruisci_coda(db) == []


def test_una_revisione_aperta_non_ancora_conclusa_resta_in_coda(db):
    aggiungi(db, 1, "VALIDO", 0)
    db.execute("INSERT INTO manual_review_queue (receipt_id, reason) VALUES (1,'x')")
    db.commit()
    assert len(costruisci_coda(db)) == 1
