"""
The storage abstraction: where the images live is a configuration choice.

DESIGN RULE, agreed with Gemini/Vibe/Perplexity on 2026-08-29 (see
docs/120_piano_archivio_immagini.md): **a key is an opaque string, never a
filesystem path.** Callers build keys by convention ("ritagli/<sha256>.jpg");
the archive only stores and retrieves bytes under them. Let a Path leak into
these signatures and the abstraction breaks at the first remote backend.

Transporting `bytes` and not decoded images is deliberate too: the archive does
not know what an image is. Decoding (cv2.imdecode) stays with the caller.
Objects here are 50KB-5MB, comfortably in RAM. Should objects ever exceed ~50MB,
the agreed way out is a separate ArchivioStreaming, not extra methods here.
"""
from abc import ABC, abstractmethod
from typing import Iterator


class ChiaveAssente(KeyError):
    """Raised by leggi() when a key does not exist, on every backend.

    Backends must translate their own errors (FileNotFoundError, S3 404) into
    this one, otherwise callers end up handling backend-specific exceptions and
    substitutability is lost.
    """


class ArchivioImmagini(ABC):
    @abstractmethod
    def leggi(self, chiave: str) -> bytes:
        """Return the stored bytes. Raises ChiaveAssente if not there."""

    @abstractmethod
    def scrivi(self, chiave: str, dati: bytes) -> None:
        """Store bytes under the key, overwriting any previous content."""

    @abstractmethod
    def esiste(self, chiave: str) -> bool:
        """Whether the key is present.

        COST WARNING: on remote backends this is one network round-trip per
        call. To check many keys, call elenca() once and keep the result in a
        set. The caller does this explicitly rather than the backend caching
        behind your back: an implicit cache goes stale when someone else writes
        to the bucket, and then esiste() lies.
        """

    @abstractmethod
    def elenca(self, prefisso: str) -> Iterator[str]:
        """Yield the keys starting with `prefisso`.

        The yielded keys must be usable as-is with leggi(): full keys, not bare
        file names.
        """

    @abstractmethod
    def cancella(self, chiave: str) -> None:
        """Remove the key. Idempotent: deleting an absent key is not an error."""
