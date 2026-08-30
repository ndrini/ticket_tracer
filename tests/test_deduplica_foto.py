"""La deduplica non deve MAI scartare una foto nuova in silenzio.

Questi test esistono per un difetto vero, non per ipotesi: il dhash della foto
intera decideva da solo, e sulle 6216 coppie del registro ne dava 112 sotto
soglia — di cui 110 erano foto DIVERSE. Le due piu' vicine (distanza 0) erano
scontrini di negozi e mesi diversi, entrambi fotografati su un tavolo di legno.

La regressione da impedire e' precisa: che il phash torni a decidere da solo.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fase_a_ingestione import (  # noqa: E402
    SOGLIA_CONFERMA,
    SOGLIA_DISTINTE,
    conferma_duplicato,
    gia_viste,
    parole,
    somiglianza,
)


def righe(*testi):
    """OCR lines in the shape the pipeline produces."""
    return [{"testo": t, "confidenza": 0.99, "box": []} for t in testi]


class ArchivioFinto:
    """Minimal archive: conferma_duplicato only ever reads."""

    def __init__(self, contenuto):
        self.contenuto = contenuto

    def leggi(self, chiave):
        if chiave not in self.contenuto:
            raise KeyError(chiave)
        return self.contenuto[chiave]


class TestParole:
    def test_ignora_maiuscole_e_punteggiatura(self):
        assert parole(righe("TOTALE: 12,97 EUR")) == parole(righe("totale 12 97 eur"))

    def test_scarta_i_frammenti_di_un_carattere(self):
        """A stray "0" or "€" is noise, not a word: it would inflate every score."""
        assert parole(righe("a b totale")) == {"totale"}

    def test_l_ordine_delle_righe_non_conta(self):
        """Deliberate: the geometric phase mis-groups lines on weighed formats
        (see AGENDA.md). Comparing sets keeps this check working anyway."""
        assert parole(righe("pane", "latte")) == parole(righe("latte", "pane"))


class TestSomiglianza:
    def test_insiemi_uguali_danno_uno(self):
        assert somiglianza({"a", "b"}, {"a", "b"}) == 1.0

    def test_insiemi_disgiunti_danno_zero(self):
        assert somiglianza({"a"}, {"b"}) == 0.0

    def test_un_insieme_vuoto_non_alza(self):
        """A photo whose OCR found nothing must not be called a duplicate."""
        assert somiglianza(set(), {"a"}) == 0.0


class TestGiaViste:
    def test_restituisce_tutti_i_sospetti_non_solo_il_primo(self):
        """The real duplicate may not be first: picking by position would
        compare the text against the wrong photo."""
        registro = {
            "a.jpg": {"phash": "0000000000000000"},
            "b.jpg": {"phash": "0000000000000001"},
            "c.jpg": {"phash": "ffffffffffffffff"},
        }
        assert sorted(gia_viste(registro, "0000000000000000")) == ["a.jpg", "b.jpg"]

    def test_lista_vuota_se_niente_somiglia(self):
        registro = {"c.jpg": {"phash": "ffffffffffffffff"}}
        assert gia_viste(registro, "0000000000000000") == []

    def test_accetta_una_lista_di_hash_e_basta_che_uno_somigli(self):
        """The four orientations arrive as a list; any one matching is enough."""
        registro = {"a.jpg": {"phash": "ffffffffffffffff"}}
        assert gia_viste(registro, ["0000000000000000", "ffffffffffffffff"]) == ["a.jpg"]
        assert gia_viste(registro, ["0000000000000000"]) == []


class TestRotazione:
    """The same photo rotated used to pass as new: dhash lands 29-32 away."""

    def _foto(self):
        cv2 = pytest.importorskip("cv2")
        np = pytest.importorskip("numpy")
        # Asymmetric, or every rotation would hash the same by accident.
        img = np.zeros((120, 160, 3), dtype=np.uint8)
        img[10:60, 20:70] = 255
        img[70:90, 100:150] = 128
        return cv2, np, img

    def test_una_foto_ruotata_trova_l_originale(self):
        from fase_a_ingestione import dhash, hash_ruotati

        _, np, img = self._foto()
        registro = {"originale.jpg": {"phash": dhash(img)}}
        for giro in range(4):
            ruotata = np.rot90(img, giro)
            assert gia_viste(registro, hash_ruotati(ruotata)) == ["originale.jpg"], (
                f"la foto ruotata di {giro * 90} gradi non riconosce l'originale")

    def test_il_registro_conserva_un_hash_solo(self):
        """Rotate the incoming photo, not the stored hash.

        Collapsing the four rotations into one hash (their minimum) shortens
        distances and nothing else: measured on 58 photos it took the pairs
        under threshold from 0 to 10. Storing one hash keeps the archive's own
        distances exactly as they are.
        """
        from fase_a_ingestione import dhash, hash_ruotati

        _, _, img = self._foto()
        quattro = hash_ruotati(img)
        assert len(quattro) == 4
        assert quattro[0] == dhash(img), "il primo deve essere la foto dritta"


class TestConfermaDuplicato:
    """The heart of the fix: the text decides, not the perceptual hash."""

    def _caso(self, testo_archiviato):
        registro = {"vecchia.jpg": {"phash": "0" * 16, "scontrini": ["abc"]}}
        import json
        archivio = ArchivioFinto({
            "estratti/abc.json": json.dumps({"righe_ocr": righe(*testo_archiviato)}).encode()
        })
        return registro, archivio

    def test_lo_stesso_scontrino_e_riconosciuto(self):
        registro, archivio = self._caso(["Esselunga", "Latte UHT 1,50", "TOTALE 1,50"])
        nome, punteggio = conferma_duplicato(
            righe("Esselunga", "Latte UHT 1,50", "TOTALE 1,50"),
            ["vecchia.jpg"], registro, archivio)
        assert nome == "vecchia.jpg"
        assert punteggio >= SOGLIA_CONFERMA

    def test_due_scontrini_diversi_NON_sono_duplicati(self):
        """The defect that mattered: two different receipts on the same table
        collide in the perceptual hash. The text must keep them apart."""
        registro, archivio = self._caso(["Consum", "Mozzarella 1,62", "TOTALE 10,24"])
        _, punteggio = conferma_duplicato(
            righe("Alcampo", "Devolucion", "TOTALE 16,30"),
            ["vecchia.jpg"], registro, archivio)
        assert punteggio < SOGLIA_DISTINTE, (
            "due scontrini diversi finirebbero scartati come duplicati")

    def test_un_estratto_illeggibile_non_fa_passare_per_nuovo(self):
        """A missing extract must not silently score 0 and let a real
        duplicate through as brand new."""
        registro = {"vecchia.jpg": {"phash": "0" * 16, "scontrini": ["assente"]}}
        nome, punteggio = conferma_duplicato(
            righe("Esselunga"), ["vecchia.jpg"], registro, ArchivioFinto({}))
        assert punteggio == 0.0
        assert nome is None

    def test_senza_testo_non_si_decide(self):
        """No OCR text, no verdict: the caller must process the photo."""
        registro, archivio = self._caso(["Esselunga"])
        nome, punteggio = conferma_duplicato([], ["vecchia.jpg"], registro, archivio)
        assert nome is None and punteggio == 0.0

    def test_sceglie_il_piu_somigliante_fra_piu_sospetti(self):
        import json
        registro = {
            "lontana.jpg": {"phash": "0" * 16, "scontrini": ["x"]},
            "giusta.jpg": {"phash": "0" * 16, "scontrini": ["y"]},
        }
        archivio = ArchivioFinto({
            "estratti/x.json": json.dumps({"righe_ocr": righe("Alcampo", "Devolucion")}).encode(),
            "estratti/y.json": json.dumps({"righe_ocr": righe("Esselunga", "Latte UHT")}).encode(),
        })
        nome, _ = conferma_duplicato(
            righe("Esselunga", "Latte UHT"), list(registro), registro, archivio)
        assert nome == "giusta.jpg"


def test_le_soglie_lasciano_un_margine():
    """Measured: different photos peak at 38.5%, true duplicates sit at 93.6%+.
    The thresholds belong in that empty gap, not on either edge."""
    assert SOGLIA_DISTINTE > 0.385, "sotto il massimo misurato per foto diverse"
    assert SOGLIA_CONFERMA < 0.936, "sopra il minimo misurato per duplicati veri"
    assert SOGLIA_DISTINTE <= SOGLIA_CONFERMA


@pytest.mark.integration
def test_sui_dati_veri_nessuna_foto_nuova_viene_scartata():
    """The whole point, checked against the real registry.

    Skipped when the registry is absent (a fresh clone has no data).
    """
    import itertools
    import json

    registro_file = Path("data/foto_viste.json")
    if not registro_file.is_file():
        pytest.skip("registro assente")
    registro = json.loads(registro_file.read_text())

    from fase_a_ingestione import SOGLIA_DUPLICATO, distanza_hash

    def testo(nome):
        insieme = set()
        for digest in registro.get(nome, {}).get("scontrini") or []:
            percorso = Path(f"data/estratti/{digest}.json")
            if percorso.is_file():
                insieme |= parole(json.loads(percorso.read_text()).get("righe_ocr") or [])
        return insieme

    # Verified by eye: same eMISFERO receipt from phone and WhatsApp; same
    # receipt re-shot. Everything else under the phash threshold is a scene
    # collision between genuinely different receipts.
    veri = {
        frozenset(("2025-01-03 10.22.03.jpg", "IMG-20250103-WA0001.jpg")),
        frozenset(("2025-02-14 14.58.47.jpg", "foto_nuova.jpg")),
    }

    scartate_per_errore = []
    for a, b in itertools.combinations(sorted(registro), 2):
        if distanza_hash(registro[a]["phash"], registro[b]["phash"]) > SOGLIA_DUPLICATO:
            continue
        if frozenset((a, b)) in veri:
            continue
        if somiglianza(testo(a), testo(b)) >= SOGLIA_CONFERMA:
            scartate_per_errore.append((a, b))

    assert not scartate_per_errore, (
        f"{len(scartate_per_errore)} foto diverse scartate come duplicati: "
        f"{scartate_per_errore[:3]}")
