"""
Fase D — carica nel database gli scontrini gia' estratti e verificati.

Legge i file prodotti dalla Fase C (`data/strutturati/<hash>.json`) e li scrive
in SQLite: commercio, scontrino, prodotti, righe.

IDEMPOTENTE per costruzione: `receipts.image_sha256` e' UNIQUE, quindi uno
scontrino gia' caricato viene riconosciuto e saltato. Rilanciare dopo aver
aggiunto altre foto carica solo le novita'.

GLI SCONTRINI CHE NON QUADRANO VENGONO CARICATI LO STESSO, marcati con il loro
esito. Scartarli falserebbe i report piu' di quanto li correggerebbe: sono
sistematicamente i piu' lunghi e costosi (la spesa grande, con sconti e molte
righe), quindi tenerne conto solo quando tornano i conti sottostimerebbe la
spesa proprio dove pesa di piu'. Il campo `validation_status` permette ai report
di distinguere il dato certo da quello indicativo.

Uso:
    uv run python scripts/fase_d_carica_db.py
    uv run python scripts/fase_d_carica_db.py --db data/spese.db
    uv run python scripts/fase_d_carica_db.py --limite 20
"""
import glob
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.getcwd())

from app.db.db_manager import init_db  # noqa: E402

DIR_STRUTTURATI = "data/strutturati"
DIR_STRUTTURATI_GEOMETRICI = "data/strutturati_geometrici"
DB_PREDEFINITO = "data/spese.db"


def trova_o_crea_commercio(cursore, nome):
    """L'id del negozio, creandolo se e' la prima volta che si incontra."""
    nome = (nome or "Sconosciuto").strip() or "Sconosciuto"
    cursore.execute("SELECT id FROM commerces WHERE name = ?", (nome,))
    riga = cursore.fetchone()
    if riga:
        return riga[0]
    cursore.execute(
        "INSERT INTO commerces (name, address) VALUES (?, ?)", (nome, ""))
    return cursore.lastrowid


def trova_o_crea_prodotto(cursore, nome, nome_originale=None):
    """
    L'id del prodotto. `aka` raccoglie i nomi con cui e' comparso.

    Non si tenta qui l'omogeneizzazione fra nomi diversi dello stesso prodotto
    (`PA DE PAGES` e `BARRA DE PA 3 U`): e' un problema semantico, che va
    affrontato sul catalogo completo con una revisione umana, non a una riga per
    volta mentre si carica.
    """
    nome = (nome or "").strip()
    if not nome:
        return None

    cursore.execute("SELECT id, aka FROM products WHERE name = ?", (nome,))
    riga = cursore.fetchone()
    if riga:
        id_prodotto, aka = riga
        if nome_originale:
            elenco = json.loads(aka) if aka else []
            if nome_originale not in elenco:
                elenco.append(nome_originale)
                cursore.execute("UPDATE products SET aka = ? WHERE id = ?",
                                (json.dumps(elenco), id_prodotto))
        return id_prodotto

    aka = json.dumps([nome_originale] if nome_originale else [])
    cursore.execute("INSERT INTO products (name, aka) VALUES (?, ?)", (nome, aka))
    return cursore.lastrowid


def carica_scontrino(cursore, dati, extraction_method="llm"):
    """
    Scrive uno scontrino e le sue righe. Restituisce l'esito.

    "gia_presente" quando l'hash e' gia' nel database: e' il caso normale di un
    rilancio, non un errore.

    extraction_method: 'llm' o 'geometric' — quale algoritmo ha generato questi dati.
    """
    digest = dati.get("sha256")
    if not digest:
        return "senza_hash"

    cursore.execute("SELECT id FROM receipts WHERE image_sha256 = ?", (digest,))
    if cursore.fetchone():
        return "gia_presente"

    id_commercio = trova_o_crea_commercio(cursore, dati.get("shop_name"))
    cursore.execute(
        """INSERT INTO receipts
           (id_commerce, data_ora, image_sha256, total_declared,
            total_computed, validation_status, validation_delta, foto_origine,
            extraction_method)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id_commercio, dati.get("date"), digest, dati.get("total"),
         dati.get("somma_prodotti"), dati.get("esito"), dati.get("scarto"),
         dati.get("foto_origine"), extraction_method))
    id_scontrino = cursore.lastrowid

    for prodotto in dati.get("items") or []:
        id_prodotto = trova_o_crea_prodotto(
            cursore, prodotto.get("name"), prodotto.get("original_name"))
        if id_prodotto is None:
            continue
        prezzo = prodotto.get("price")
        name_quality = prodotto.get("name_quality")  # solo per metodo geometrico
        cursore.execute(
            """INSERT INTO receipt_lines
               (receipt_id, product_id, quantity, unity_price, total_price,
                extraction_method, name_quality)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id_scontrino, id_prodotto, 1, prezzo, prezzo,
             extraction_method, name_quality))

    return dati.get("esito") or "CARICATO"


def main(argv):
    db = argv[argv.index("--db") + 1] if "--db" in argv else DB_PREDEFINITO
    limite = int(argv[argv.index("--limite") + 1]) if "--limite" in argv else None

    # Raccogli i percorsi da ENTRAMBI i directory (LLM e geometrico)
    percorsi_llm = sorted(glob.glob(os.path.join(DIR_STRUTTURATI, "*.json")))
    percorsi_geom = sorted(glob.glob(os.path.join(DIR_STRUTTURATI_GEOMETRICI, "*.json")))

    # Priorizza il geometrico se esiste sia LLM che geometrico per lo stesso scontrino
    sha256_geom = {os.path.basename(p)[:-5]: p for p in percorsi_geom}
    percorsi_da_caricare = []
    caricati_geom = set()

    # Leggi prima il geometrico (se esiste)
    for sha256, percorso in sorted(sha256_geom.items()):
        percorsi_da_caricare.append((percorso, "geometric"))
        caricati_geom.add(sha256)

    # Poi aggiungi il LLM che non hanno il geometrico
    for percorso in percorsi_llm:
        sha256 = os.path.basename(percorso)[:-5]
        if sha256 not in caricati_geom:
            percorsi_da_caricare.append((percorso, "llm"))

    if limite:
        percorsi_da_caricare = percorsi_da_caricare[:limite]

    if not percorsi_da_caricare:
        print(f"Nessuno scontrino in {DIR_STRUTTURATI}/ o {DIR_STRUTTURATI_GEOMETRICI}/.")
        print("Esegui prima la Fase C (LLM) e/o la Fase C geometrica.")
        return 1

    os.makedirs(os.path.dirname(db) or ".", exist_ok=True)
    init_db(db)

    print(f"Fase D — {len(percorsi_da_caricare)} scontrini -> {db}\n")

    conteggi = {}
    connessione = sqlite3.connect(db)
    cursore = connessione.cursor()
    try:
        for percorso, extraction_method in percorsi_da_caricare:
            with open(percorso) as fh:
                dati = json.load(fh)
            esito = carica_scontrino(cursore, dati, extraction_method)
            conteggi[esito] = conteggi.get(esito, 0) + 1
        connessione.commit()
    finally:
        connessione.close()

    for esito, n in sorted(conteggi.items(), key=lambda z: -z[1]):
        print(f"  {esito:<20} {n:4d}")

    connessione = sqlite3.connect(db)
    for tabella in ("commerces", "receipts", "products", "receipt_lines"):
        n = connessione.execute(f"SELECT COUNT(*) FROM {tabella}").fetchone()[0]
        print(f"\n  {tabella:<16} {n:5d}" if tabella == "commerces"
              else f"  {tabella:<16} {n:5d}")
    connessione.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
