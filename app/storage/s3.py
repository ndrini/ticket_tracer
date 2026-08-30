"""
S3-backed archive.

Credentials are never passed in: boto3 picks them up from the environment
(.env / AWS_ACCESS_KEY_ID, or an instance role in production), so no secret
ever reaches settings.ini or git.
"""
from typing import Iterator

import boto3
from botocore.exceptions import ClientError

from app.storage.archivio import ArchivioImmagini, ChiaveAssente


class ArchivioS3(ArchivioImmagini):
    def __init__(self, bucket: str, prefisso: str = "", regione: str | None = None,
                 client=None):
        self.bucket = bucket
        self.prefisso = prefisso
        # An injected client keeps this testable without touching the network.
        self.s3 = client or boto3.client("s3", region_name=regione)

    def _oggetto(self, chiave: str) -> str:
        """Prepend the configured prefix. Keys stay opaque to callers."""
        return f"{self.prefisso}{chiave}"

    def leggi(self, chiave: str) -> bytes:
        try:
            risposta = self.s3.get_object(Bucket=self.bucket, Key=self._oggetto(chiave))
        except ClientError as e:
            # Translate S3's error into the shared one, or callers would have to
            # handle backend-specific exceptions and substitutability would go.
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise ChiaveAssente(chiave) from e
            raise
        return risposta["Body"].read()

    def scrivi(self, chiave: str, dati: bytes) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=self._oggetto(chiave), Body=dati)

    def esiste(self, chiave: str) -> bool:
        """One HEAD request. To check many keys, use elenca() once instead."""
        try:
            self.s3.head_object(Bucket=self.bucket, Key=self._oggetto(chiave))
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise
        return True

    def elenca(self, prefisso: str) -> Iterator[str]:
        # Paginated: a bucket holding more than 1000 objects is the normal case
        # here, and list_objects_v2 truncates silently without this.
        paginatore = self.s3.get_paginator("list_objects_v2")
        atteso = self._oggetto(prefisso)
        for pagina in paginatore.paginate(Bucket=self.bucket, Prefix=atteso):
            for oggetto in pagina.get("Contents", []):
                # Strip the prefix back off: callers must get the same keys they
                # wrote, usable as-is with leggi().
                yield oggetto["Key"][len(self.prefisso):]

    def cancella(self, chiave: str) -> None:
        # S3 delete is already idempotent: absent keys return 204.
        self.s3.delete_object(Bucket=self.bucket, Key=self._oggetto(chiave))
