"""
Conformance suite: every ArchivioImmagini backend must pass it unchanged.

This is the executable form of the Liskov substitution principle for this
project: ArchivioS3 must be swappable for ArchivioLocale without any phase
noticing. A backend that needs its own special-cased test has already broken
the contract.

New backends (Google Drive, ...) subclass ArchivioConforme and only provide the
`archivio` fixture.
"""
import pytest

from app.storage.archivio import ArchivioImmagini, ChiaveAssente


class ArchivioConforme:
    """Shared contract. Subclasses supply the `archivio` fixture."""

    def test_e_un_archivio(self, archivio):
        assert isinstance(archivio, ArchivioImmagini)

    def test_scrivi_poi_leggi_restituisce_gli_stessi_byte(self, archivio):
        dati = b"\xff\xd8\xff\xe0 finti byte jpeg \x00\x01\x02"
        archivio.scrivi("ritagli/abc123.jpg", dati)
        assert archivio.leggi("ritagli/abc123.jpg") == dati

    def test_esiste_e_falso_prima_e_vero_dopo(self, archivio):
        assert archivio.esiste("ritagli/nuovo.jpg") is False
        archivio.scrivi("ritagli/nuovo.jpg", b"x")
        assert archivio.esiste("ritagli/nuovo.jpg") is True

    def test_leggere_una_chiave_assente_alza_ChiaveAssente(self, archivio):
        with pytest.raises(ChiaveAssente):
            archivio.leggi("ritagli/mai_scritto.jpg")

    def test_scrivi_sovrascrive(self, archivio):
        archivio.scrivi("k.jpg", b"vecchio")
        archivio.scrivi("k.jpg", b"nuovo")
        assert archivio.leggi("k.jpg") == b"nuovo"

    def test_elenca_filtra_per_prefisso(self, archivio):
        archivio.scrivi("ritagli/a.jpg", b"1")
        archivio.scrivi("ritagli/b.jpg", b"2")
        archivio.scrivi("foto/c.jpg", b"3")
        assert sorted(archivio.elenca("ritagli/")) == ["ritagli/a.jpg", "ritagli/b.jpg"]

    def test_elenca_su_prefisso_vuoto_non_alza(self, archivio):
        assert list(archivio.elenca("niente/")) == []

    def test_elenca_restituisce_chiavi_rileggibili(self, archivio):
        """The keys elenca() yields must be valid input for leggi().

        Guards the trap that broke the design: a backend returning bare
        filenames instead of full keys would pass every other test.
        """
        archivio.scrivi("ritagli/x.jpg", b"contenuto")
        for chiave in archivio.elenca("ritagli/"):
            assert archivio.leggi(chiave) == b"contenuto"

    def test_cancella_rimuove(self, archivio):
        archivio.scrivi("k.jpg", b"x")
        archivio.cancella("k.jpg")
        assert archivio.esiste("k.jpg") is False

    def test_cancellare_una_chiave_assente_non_alza(self, archivio):
        archivio.cancella("mai_esistita.jpg")  # idempotent

    def test_i_byte_sopravvivono_intatti(self, archivio):
        """No text-mode mangling: images are binary."""
        dati = bytes(range(256))
        archivio.scrivi("binario.bin", dati)
        assert archivio.leggi("binario.bin") == dati


class TestArchivioLocale(ArchivioConforme):
    @pytest.fixture
    def archivio(self, tmp_path):
        from app.storage.locale import ArchivioLocale
        return ArchivioLocale(tmp_path)


class TestArchivioS3(ArchivioConforme):
    """The very same contract, on S3. If this class needed its own tests,
    ArchivioS3 would not be substitutable and the design would be broken."""

    @pytest.fixture
    def archivio(self):
        boto3 = pytest.importorskip("boto3")
        moto = pytest.importorskip("moto")
        from app.storage.s3 import ArchivioS3
        with moto.mock_aws():
            client = boto3.client("s3", region_name="eu-south-1")
            client.create_bucket(
                Bucket="prova",
                CreateBucketConfiguration={"LocationConstraint": "eu-south-1"},
            )
            yield ArchivioS3(bucket="prova", prefisso="produzione/", client=client)
