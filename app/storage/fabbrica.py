"""
Where the backend choice is made: one place, driven by settings.ini.

This is the point of the whole exercise. The phases ask the factory for an
archive and never name a concrete class, so switching local -> S3 is an edit to
settings.ini, not to the code (Dependency Inversion).

Secrets are NOT here: AWS credentials live in .env (git-ignored). settings.ini
carries only type, bucket and prefix, so it stays versionable.
"""
import configparser
import os
from pathlib import Path

from app.storage.archivio import ArchivioImmagini

RADICE_PROGETTO = Path(__file__).resolve().parent.parent.parent
SETTINGS = RADICE_PROGETTO / "settings.ini"


def costruisci_archivio(settings: str | Path | None = None) -> ArchivioImmagini:
    """Build the archive described by settings.ini.

    Falls back to a local archive rooted at data/ when the file is missing, so
    the project keeps working exactly as before for anyone who has not created
    a settings.ini yet.
    """
    percorso = Path(settings) if settings else SETTINGS
    conf = configparser.ConfigParser()
    if percorso.is_file():
        conf.read(percorso)

    tipo = conf.get("archivio", "tipo", fallback="locale").strip().lower()

    if tipo == "locale":
        from app.storage.locale import ArchivioLocale
        radice = conf.get("archivio", "radice", fallback="data")
        return ArchivioLocale(RADICE_PROGETTO / radice)

    if tipo == "s3":
        from app.storage.s3 import ArchivioS3
        # Credentials come from the environment (.env), never from settings.ini.
        return ArchivioS3(
            bucket=conf.get("archivio", "bucket"),
            prefisso=conf.get("archivio", "prefisso", fallback=""),
            regione=conf.get("archivio", "regione",
                             fallback=os.environ.get("AWS_REGION", "eu-south-1")),
        )

    raise ValueError(
        f"tipo di archivio sconosciuto: {tipo!r} in {percorso}. "
        f"Validi: locale, s3."
    )
