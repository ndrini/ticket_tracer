"""
Verifica che S3 funzioni davvero, e che ArchivioS3 sia intercambiabile.

    uv run python scripts/prova_s3.py --bucket ticket-tracer-immagini

Credenziali da .env (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION).
Crea il bucket se manca, fa un giro completo scrivi/leggi/elenca/cancella, poi
carica DAVVERO alcuni ritagli veri e li rilegge confrontando gli sha256.

Serve a chiudere il debito dichiarato in docs/120: finora ArchivioS3 era stato
provato solo contro moto, mai su un bucket vero.
"""
import argparse
import hashlib
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.storage.archivio import ChiaveAssente  # noqa: E402
from app.storage.s3 import ArchivioS3  # noqa: E402

RADICE = pathlib.Path(__file__).resolve().parent.parent


def carica_env():
    """Read .env without extra dependencies: the project already keeps keys there."""
    percorso = RADICE / ".env"
    if not percorso.is_file():
        return
    for riga in percorso.read_text().splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        chiave, _, valore = riga.partition("=")
        os.environ.setdefault(chiave.strip(), valore.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--regione", default=None)
    ap.add_argument("--prefisso", default="prova/")
    ap.add_argument("--quanti", type=int, default=3,
                    help="quanti ritagli veri caricare")
    args = ap.parse_args()

    carica_env()
    regione = args.regione or os.environ.get("AWS_REGION", "eu-north-1")

    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        print("MANCANO LE CREDENZIALI.")
        print("Aggiungi a .env (che git ignora):")
        print("  AWS_ACCESS_KEY_ID=AKIA...")
        print("  AWS_SECRET_ACCESS_KEY=...")
        print(f"  AWS_REGION={regione}")
        return 1

    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3", region_name=regione)

    # 1. Bucket
    try:
        s3.head_bucket(Bucket=args.bucket)
        print(f"[1/5] bucket '{args.bucket}' gia' esistente")
    except ClientError:
        try:
            crea = {"Bucket": args.bucket}
            # us-east-1 is the one region that rejects an explicit constraint.
            if regione != "us-east-1":
                crea["CreateBucketConfiguration"] = {"LocationConstraint": regione}
            s3.create_bucket(**crea)
            print(f"[1/5] bucket '{args.bucket}' creato in {regione}")
        except ClientError as e:
            print(f"[1/5] FALLITO: {e}")
            return 1

    archivio = ArchivioS3(bucket=args.bucket, prefisso=args.prefisso,
                          regione=regione)

    # 2. Giro completo
    archivio.scrivi("diagnostica/ciao.txt", b"ciao S3")
    assert archivio.leggi("diagnostica/ciao.txt") == b"ciao S3"
    assert archivio.esiste("diagnostica/ciao.txt")
    print("[2/5] scrivi/leggi/esiste: ok")

    try:
        archivio.leggi("diagnostica/mai_scritto.txt")
        print("[3/5] FALLITO: doveva alzare ChiaveAssente")
        return 1
    except ChiaveAssente:
        print("[3/5] ChiaveAssente su chiave mancante: ok")

    # 4. Ritagli veri: e' qui che si vede se regge sui dati del progetto
    ritagli = sorted((RADICE / "data" / "ritagli").glob("*.jpg"))[:args.quanti]
    uguali = 0
    for p in ritagli:
        chiave = "ritagli/" + p.name
        originale = p.read_bytes()
        archivio.scrivi(chiave, originale)
        tornato = archivio.leggi(chiave)
        # The name IS the sha256 of the content: verify the round trip kept it.
        if tornato == originale and hashlib.sha256(tornato).hexdigest() == p.stem:
            uguali += 1
        else:
            print(f"      DIVERSO dopo il giro: {p.name}")
    print(f"[4/5] ritagli veri: {uguali}/{len(ritagli)} identici byte per byte")

    elencati = set(archivio.elenca("ritagli/"))
    print(f"      elenca('ritagli/') -> {len(elencati)} chiavi")

    # 5. Pulizia
    for chiave in list(elencati) + ["diagnostica/ciao.txt"]:
        archivio.cancella(chiave)
    rimasti = list(archivio.elenca(""))
    print(f"[5/5] pulizia: {len(rimasti)} chiavi rimaste")

    esito = uguali == len(ritagli) and not rimasti
    print("\n" + ("S3 FUNZIONA: ArchivioS3 e' intercambiabile con ArchivioLocale."
                  if esito else "QUALCOSA NON TORNA, vedi sopra."))
    if esito:
        print("\nPer usarlo davvero, in settings.ini:")
        print(f"  [archivio]\n  tipo = s3\n  bucket = {args.bucket}\n"
              f"  prefisso = produzione/\n  regione = {regione}")
    return 0 if esito else 1


if __name__ == "__main__":
    raise SystemExit(main())
