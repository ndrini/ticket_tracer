"""La pagina di elaborazione: i comandi che sa lanciare e cio' che mostra.

Non prova il server HTTP vero — avviare un socket in un test lo renderebbe
lento e capriccioso. Prova quello che puo' rompersi in silenzio: che i comandi
puntino a script esistenti, che ogni fase mostrata sia lanciabile, e che il
pulsante sospeso non lo sia.
"""
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RADICE / "scripts"))

from app.revisione.riassunto import FASI  # noqa: E402


@pytest.fixture(scope="module")
def comandi():
    from revisione_umana import comandi as fabbrica
    return fabbrica("2025_scontrini")


class TestComandi:
    def test_ogni_comando_punta_a_uno_script_che_esiste(self, comandi):
        """A typo here fails only when the button is pressed, minutes later."""
        for nome, argomenti in comandi.items():
            percorso = RADICE / argomenti[0]
            assert percorso.is_file(), f"{nome} -> {argomenti[0]} non esiste"

    def test_i_due_comandi_drive_ci_sono(self, comandi):
        assert "drive_immagini" in comandi
        assert "drive_dati" in comandi

    def test_i_comandi_drive_caricano_davvero(self, comandi):
        """Without --esegui both scripts only say what they would do: the
        button would look broken, reporting success and uploading nothing."""
        assert "--esegui" in comandi["drive_immagini"]
        assert "--esegui" in comandi["drive_dati"]

    def test_il_vaglio_non_cancella_di_nascosto(self, comandi):
        """--archivia moves aside, it does not delete. Guards the project rule
        that nothing irreversible happens without being asked."""
        assert "--elimina" not in comandi["vaglio"]
        assert "--cancella" not in comandi["vaglio"]


class TestFasiEComandiCombaciano:
    """The page is built from FASI; the server executes `comandi`. If the two
    drift, a button appears that nothing can run."""

    def test_ogni_fase_attiva_ha_il_suo_comando(self, comandi):
        for fase in FASI:
            if fase.get("sospesa"):
                continue
            assert fase["chiave"] in comandi, (
                f"la fase '{fase['chiave']}' e' nella pagina ma non e' lanciabile")

    def test_la_fase_sospesa_NON_ha_un_comando(self, comandi):
        """Suspended means unreachable, not just greyed out: a disabled button
        is client-side, and the route would still accept the request."""
        sospese = [f["chiave"] for f in FASI if f.get("sospesa")]
        assert sospese, "il test presume che ci sia almeno una fase sospesa"
        for chiave in sospese:
            assert chiave not in comandi, (
                f"'{chiave}' e' sospesa ma il server la eseguirebbe lo stesso")

    def test_solo_l_ingestione_chiede_una_cartella(self):
        richiedono = [f["chiave"] for f in FASI if f.get("serve_cartella")]
        assert richiedono == ["ingestione"]


class TestPagina:
    """Checks on the HTML itself: cheap, and they catch a renamed id."""

    @pytest.fixture(scope="class")
    def pagina(self):
        from revisione_umana import PAGINA_INGESTIONE
        return PAGINA_INGESTIONE

    def test_disegna_le_fasi_dai_dati_e_non_a_mano(self, pagina):
        """The buttons used to be hard-coded in the HTML. Listing them twice
        means one list quietly goes stale."""
        assert 'id="fasi"' in pagina
        assert "onclick=\"avvia('ingestione')\"" not in pagina, (
            "i pulsanti sono tornati scritti a mano nella pagina")

    def test_chiede_il_riassunto_all_apertura(self, pagina):
        assert "/riassunto" in pagina
        assert "riassunto();" in pagina

    def test_non_interroga_il_riassunto_di_continuo(self, pagina):
        """Only /lavori/stato is polled, and only while a job runs."""
        assert "setInterval(stato" in pagina
        assert "setInterval(riassunto" not in pagina
