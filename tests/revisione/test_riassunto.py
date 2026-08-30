"""Il quadro d'insieme: quanto e' fatto, senza lanciare nulla per scoprirlo.

Scritti PRIMA del codice. Devono fallire finche' app/revisione/riassunto.py non
esiste, e passare dopo.

La regola che pesa di piu' e' la seconda classe: il riassunto NON parla con
Google Drive. Contare 507 file remoti a ogni caricamento della pagina sarebbe
una chiamata di rete per un numero che cambia solo quando si preme un pulsante.
"""
import json

import pytest

from app.revisione.riassunto import riassumi


@pytest.fixture
def progetto(tmp_path):
    """Un progetto finto, con le sole cartelle che il riassunto guarda."""
    for nome in ("estratti", "strutturati_geometrici", "miniature", "ritagli",
                 "2025_scontrini"):
        (tmp_path / nome).mkdir()
    return tmp_path


def scontrino(cartella, sha, totale, righe):
    """Uno strutturato come lo scrive la fase geometrica."""
    (cartella / f"{sha}.json").write_text(json.dumps({
        "sha256": sha,
        "total": totale,
        "items": [{"name": n, "price": p} for n, p in righe],
    }))


class TestConta:
    def test_progetto_vuoto_da_tutti_zeri_e_non_alza(self, progetto):
        r = riassumi(progetto)
        assert r["foto"] == 0
        assert r["estratti"] == 0
        assert r["chiusi"] == 0
        assert r["da_ripassare"] == 0

    def test_conta_le_foto_da_elaborare(self, progetto):
        (progetto / "2025_scontrini" / "a.jpg").write_bytes(b"x")
        (progetto / "2025_scontrini" / "b.JPG").write_bytes(b"x")
        (progetto / "2025_scontrini" / "note.txt").write_bytes(b"x")
        assert riassumi(progetto)["foto"] == 2, "estensione maiuscola o file non immagine"

    def test_conta_gli_estratti_e_i_ritagli(self, progetto):
        (progetto / "estratti" / "aa.json").write_text("{}")
        (progetto / "ritagli" / "aa.jpg").write_bytes(b"x")
        r = riassumi(progetto)
        assert r["estratti"] == 1
        assert r["ritagli"] == 1

    def test_separa_i_chiusi_da_quelli_da_ripassare(self, progetto):
        s = progetto / "strutturati_geometrici"
        # Quadra e ha tutti i nomi: chiuso.
        scontrino(s, "a" * 8, 3.00, [("Pane", 1.00), ("Latte", 2.00)])
        # Quadra ma un nome manca: da ripassare.
        scontrino(s, "b" * 8, 3.00, [("Pane", 1.00), ("", 2.00)])
        # Non quadra: da ripassare.
        scontrino(s, "c" * 8, 9.99, [("Pane", 1.00)])
        r = riassumi(progetto)
        assert r["strutturati"] == 3
        assert r["chiusi"] == 1
        assert r["da_ripassare"] == 2

    def test_un_json_illeggibile_non_fa_cadere_tutto(self, progetto):
        """One broken file must not blank the whole summary."""
        s = progetto / "strutturati_geometrici"
        scontrino(s, "a" * 8, 3.00, [("Pane", 1.00), ("Latte", 2.00)])
        (s / "rotto.json").write_text("{ questo non e' json")
        r = riassumi(progetto)
        assert r["chiusi"] == 1
        assert r["illeggibili"] == 1

    def test_dice_quante_foto_restano_da_ingerire(self, progetto):
        """The number that decides whether pressing Ingestione is worth it."""
        (progetto / "2025_scontrini" / "a.jpg").write_bytes(b"x")
        (progetto / "2025_scontrini" / "b.jpg").write_bytes(b"x")
        (progetto / "foto_viste.json").write_text(json.dumps({"a.jpg": {"phash": "0"}}))
        assert riassumi(progetto)["da_ingerire"] == 1


class TestNonToccaLaRete:
    """The summary is built from local files only.

    Drive holds 507 files; counting them on every page load would be a network
    round-trip for a number that only changes when a button is pressed. The
    page must open instantly and offline.
    """

    def test_non_costruisce_un_archivio_remoto(self, progetto, monkeypatch):
        import app.storage

        def vietato(*a, **k):
            raise AssertionError("il riassunto ha provato a parlare con l'archivio remoto")

        monkeypatch.setattr(app.storage, "costruisci_archivio", vietato)
        riassumi(progetto)

    def test_non_apre_connessioni(self, progetto, monkeypatch):
        import socket

        def vietato(*a, **k):
            raise AssertionError("il riassunto ha aperto una connessione di rete")

        monkeypatch.setattr(socket.socket, "connect", vietato)
        riassumi(progetto)


class TestFasi:
    """The page shows the order; it does not enforce it.

    Every script is already idempotent and skips what is done. A second gate in
    the UI would be a second truth, free to drift from the real one.
    """

    def test_elenca_le_fasi_in_ordine(self):
        from app.revisione.riassunto import FASI

        nomi = [f["chiave"] for f in FASI]
        assert nomi.index("ingestione") < nomi.index("estrazione")
        assert nomi.index("estrazione") < nomi.index("miniature")
        assert nomi.index("miniature") < nomi.index("vaglio")
        assert nomi.index("vaglio") < nomi.index("drive_immagini")

    def test_ogni_fase_dice_cosa_fa(self):
        from app.revisione.riassunto import FASI

        for fase in FASI:
            assert fase["titolo"] and fase["spiega"], f"{fase['chiave']} senza descrizione"

    def test_la_fase_d_e_presente_ma_sospesa_col_motivo(self):
        """Not hidden: whoever comes back in six months must find out why.

        A missing button is a question; a disabled one with its reason is an
        answer.
        """
        from app.revisione.riassunto import FASI

        fase_d = next((f for f in FASI if f["chiave"] == "database"), None)
        assert fase_d is not None, "la fase D non deve sparire dalla pagina"
        assert fase_d.get("sospesa") is True
        assert fase_d.get("perche"), "una fase sospesa deve dire perche'"
        assert "peso" in fase_d["perche"].lower() or "prezzo" in fase_d["perche"].lower()

    def test_le_altre_fasi_non_sono_sospese(self):
        from app.revisione.riassunto import FASI

        attive = [f for f in FASI if not f.get("sospesa")]
        assert len(attive) >= 5
