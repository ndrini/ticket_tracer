"""Filesystem-backed archive: what the project does today."""
from pathlib import Path
from typing import Iterator

from app.storage.archivio import ArchivioImmagini, ChiaveAssente


class ArchivioLocale(ArchivioImmagini):
    def __init__(self, radice: str | Path):
        self.radice = Path(radice)

    def _percorso(self, chiave: str) -> Path:
        """Map an opaque key onto a path under the root.

        Keys containing ".." would otherwise write outside the root: a key is
        untrusted input, since it can come from a file name on disk.
        """
        destinazione = (self.radice / chiave).resolve()
        radice = self.radice.resolve()
        if not destinazione.is_relative_to(radice):
            raise ValueError(f"chiave fuori dall'archivio: {chiave!r}")
        return destinazione

    def leggi(self, chiave: str) -> bytes:
        try:
            return self._percorso(chiave).read_bytes()
        except FileNotFoundError as e:
            raise ChiaveAssente(chiave) from e

    def scrivi(self, chiave: str, dati: bytes) -> None:
        percorso = self._percorso(chiave)
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_bytes(dati)

    def esiste(self, chiave: str) -> bool:
        return self._percorso(chiave).is_file()

    def elenca(self, prefisso: str) -> Iterator[str]:
        radice = self.radice.resolve()
        for percorso in sorted(radice.rglob("*")):
            if not percorso.is_file():
                continue
            # Yield keys, not paths: they must work with leggi().
            chiave = percorso.relative_to(radice).as_posix()
            if chiave.startswith(prefisso):
                yield chiave

    def cancella(self, chiave: str) -> None:
        self._percorso(chiave).unlink(missing_ok=True)
