import os

import pytest

from app.db.db_manager import init_db, seed_db
from app.stat.stat_engine import calculate_statistics


@pytest.fixture
def populated_db():
    """
    Fixture that creates a temporary database, populates it with test data from a YAML file,
    and yields the path. After the test, it cleans up by removing the file.
    """

    db_path = "data/test_stat.db"
    yaml_path = "data/test_data.yaml"

    # Setup: pulizia preventiva e inizializzazione
    if os.path.exists(db_path):
        os.remove(db_path)

    init_db(db_path)
    seed_db(db_path, yaml_path)

    yield db_path

    # Teardown: pulizia finale
    if os.path.exists(db_path):
        os.remove(db_path)


def test_calculate_statistics(populated_db):
    # Eseguiamo il calcolo delle statistiche sul DB popolato dalla fixture
    stats = calculate_statistics(populated_db)

    # Verifiche basate sui dati in data/test_data.yaml:
    # Ticket 1: Esselunga. Prodotti: Milk (3.00) + Orange (3.99) = 6.99 Totale

    # 1. Verifica Spesa per Commercio
    commerces = dict(stats["total_spent_per_commerce"])
    assert commerces["Esselunga"] == 6.99

    # 2. Verifica Spesa per Prodotto
    products = dict(stats["total_spent_per_product"])
    assert products["milk"] == 3.00
    assert products["orange"] == 3.99

    # 3. Verifica Trend Mensile
    months = dict(stats["monthly_spending_trends"])
    assert months["2023-10"] == 6.99
