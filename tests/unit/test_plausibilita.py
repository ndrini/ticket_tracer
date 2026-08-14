"""Tests for the price sanity checks."""
from app.etl.plausibilita import controlla_prezzo, controlla_scontrino


class TestControllaPrezzo:
    def test_prezzo_normale(self):
        """La mediana misurata sugli scontrini che quadrano e' 2,00 euro."""
        assert controlla_prezzo(2.00) is None
        assert controlla_prezzo(0.78) is None
        assert controlla_prezzo(6.48) is None

    def test_prezzo_troppo_basso(self):
        """Uno yogurt non costa 5 centesimi: e' una virgola letta male."""
        assert controlla_prezzo(0.05) is not None
        assert controlla_prezzo(0.01) is not None

    def test_prezzo_nullo(self):
        assert controlla_prezzo(0.0) is not None

    def test_prezzo_insolito_ma_possibile(self):
        """Sopra 30 euro capita (IKEA, Decathlon): segnalato, non respinto."""
        motivo = controlla_prezzo(47.85)
        assert motivo is not None and "insolito" in motivo

    def test_prezzo_fuori_scala(self):
        """Oltre 200 euro e' quasi certamente un totale scambiato per prodotto."""
        motivo = controlla_prezzo(350.00)
        assert motivo is not None and "fuori scala" in motivo

    def test_i_resi_sono_leciti(self):
        """Un reso ha prezzo negativo ed e' un dato valido, non un errore.

        Il piu' grande misurato e' -29,88 su uno scontrino IKEA."""
        assert controlla_prezzo(-29.88) is None
        assert controlla_prezzo(-3.73) is None

    def test_prezzo_mancante(self):
        assert controlla_prezzo(None) is not None


class TestControllaScontrino:
    def test_scontrino_plausibile(self):
        prodotti = [{"name": "PANET", "price": 1.14},
                    {"name": "GUACAMOLE", "price": 3.95}]
        assert controlla_scontrino(prodotti, totale=5.09) == []

    def test_segnala_il_prodotto_sbagliato(self):
        prodotti = [{"name": "PANET", "price": 1.14},
                    {"name": "YOGURT", "price": 0.02}]
        problemi = controlla_scontrino(prodotti, totale=1.16)
        assert len(problemi) == 1
        assert problemi[0]["nome"] == "YOGURT"

    def test_prodotto_piu_caro_del_totale(self):
        """Se un articolo supera il totale, uno dei due e' stato letto male."""
        prodotti = [{"name": "PANET", "price": 1.14},
                    {"name": "SPESA", "price": 25.00}]
        problemi = controlla_scontrino(prodotti, totale=5.00)
        assert any("maggiore del totale" in p["motivo"] for p in problemi)

    def test_senza_totale_controlla_comunque_i_prezzi(self):
        problemi = controlla_scontrino([{"name": "X", "price": 0.01}])
        assert len(problemi) == 1

    def test_scontrino_vuoto(self):
        assert controlla_scontrino([]) == []
        assert controlla_scontrino(None) == []
