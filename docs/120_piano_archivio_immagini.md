# Fase 1 — Interfaccia `ArchivioImmagini` (storage commutabile)

Stato: **PIANO, in attesa di consenso**. Data: 2026-08-29.

## Il problema

Le immagini stanno solo sul filesystem locale. Il dataset non e' chiuso: le 96
foto attuali sono una frazione. Serve poter mettere le foto altrove (S3, poi
eventualmente Google Drive) **cambiando solo una configurazione**, senza
riscrivere le fasi.

Requisito esplicito dell'utente (2026-08-29):
> "ci deve essere una interfaccia che mi permetta di cambiare da uno storage
> all'altro senza traumi, solo con una configurazione di settings.ini"

## I dati misurati

- 306 scontrini nel DB; `receipts.immagine` (BLOB) e' **NULL su tutti e 306**.
  Le immagini vivono gia' solo su filesystem, indirizzate da `image_sha256`.
- 306/306 hanno `image_sha256` valorizzato.
- 317 ritagli in `data/ritagli/`, 96 foto in `data/2025_scontrini/`.
- 287 JSON in `data/strutturati_geometrici/`, **287/287 gia' presenti nel DB**
  (zero orfani).
- Nessun `settings.ini` nel progetto, nessun uso di `configparser`, `boto3` non
  installato. Terreno libero: nessun vincolo pregresso sulla forma.

## Punti di I/O da convertire

Percorso di produzione (obbligatori):

| File | Righe | Operazione |
|---|---|---|
| `scripts/fase_a_ingestione.py` | 139 | `cv2.imread(path)` — legge la foto |
| `scripts/fase_a_ingestione.py` | 154 | `os.path.exists(estratti/<sha>.json)` — **esistenza** |
| `scripts/fase_a_ingestione.py` | 198-201 | scrive `<sha>.json` e `<sha>.jpg` |
| `scripts/fase_a_ingestione.py` | 224,229 | `os.listdir` + `imread` (ricostruisci registro) |
| `scripts/fase_a_ingestione.py` | 261 | `os.listdir(sorgente)` — elenco foto |
| `app/etl/etl_engine.py` | 750 | `cv2.imread(image_path)` |
| `main.py` | 52, 73 | `glob` in ingresso, `imwrite` dei ritagli |

Fuori percorso (script diagnostici e Kaggle: NON si convertono ora)
`genera_fogli_debug.py`, `segmenta_detector.py`, `verifica_segmentazione.py`,
`metrica_iou.py`, `benchmark_*`, `kaggle_*`, `test_llava_local_quick.py`.
Motivo: girano a mano su dati locali; convertirli aggiunge superficie senza
beneficio. Rischio dichiarato: restano legati al disco.

## La forma proposta

```
app/storage/archivio.py    # ABC ArchivioImmagini
app/storage/locale.py      # filesystem (comportamento di oggi)
app/storage/s3.py          # boto3
app/storage/fabbrica.py    # settings.ini -> istanza
settings.ini               # [archivio] tipo = locale|s3
```

Interfaccia minima:

```python
class ArchivioImmagini(ABC):
    def leggi(self, chiave: str) -> bytes: ...
    def scrivi(self, chiave: str, dati: bytes) -> None: ...
    def esiste(self, chiave: str) -> bool: ...
    def elenca(self, prefisso: str) -> Iterator[str]: ...
```

**La regola che regge tutto: la chiave e' sempre lo sha256, mai un percorso.**
E' gia' cosi' su disco (`data/ritagli/<sha>.jpg`) e nel DB
(`receipts.image_sha256`). S3 riceve `ritagli/<sha>.jpg`; Google Drive, il
giorno che servira', tiene un indice sha -> fileId senza che le fasi se ne
accorgano. Se lasciassimo trapelare `Path` nelle firme, l'astrazione si
romperebbe al primo backend remoto.

`bytes` e non `ndarray`: la decodifica (`cv2.imdecode`) resta a carico del
chiamante. L'archivio trasporta byte, non sa cosa sia un'immagine.

I segreti (chiavi AWS) stanno in `.env`, gia' ignorato da git. `settings.ini`
porta solo tipo, bucket e prefisso: e' versionabile.

## SOLID

- **DIP**: le fasi dipendono dall'ABC, la scelta concreta la fa la fabbrica.
- **LSP**: `ArchivioS3` deve essere sostituibile a `ArchivioLocale` senza che i
  test delle fasi cambino. Verifica: **la stessa suite gira su entrambi.**
- **ISP**: quattro metodi, nessun backend costretto a implementare il superfluo.
- **OCP**: aggiungere Drive = una classe nuova, nessuna modifica alle fasi.

## Alternative scartate

1. **BLOB nel DB** (`receipts.immagine` esiste gia'): scartata, la colonna e'
   NULL su tutti e 306 — la scelta di fatto e' gia' stata fatta. Gonfierebbe
   SQLite e non risolve la condivisione.
2. **`fsspec`/`smart_open`**: darebbero S3+Drive gratis con le URL. Scartata
   per ora perche' nasconde il costo delle chiamate di rete dietro una `open()`
   dall'aria locale, e perche' `esiste()` per foto su S3 diventerebbe una HEAD
   per file, invisibile nel codice. Riconsiderabile se le implementazioni
   nostre si rivelassero piu' onerose del previsto.
3. **Convertire tutti i 28 punti di I/O**: scartata, vedi sopra.

## Metrica dichiarata PRIMA

- **Principale**: la fase A completa gira su `ArchivioLocale` producendo
  **esattamente gli stessi** 317 ritagli e lo stesso `foto_viste.json` di oggi
  (confronto per sha256). Zero regressioni.
- **Di guardia**: i test esistenti (`tests/unit`, `tests/test_db.py`) restano
  verdi; il tempo della fase A non peggiora oltre il 5% in locale.
- **LSP**: una suite di conformita' gira identica su locale e su S3 simulato.
- **Fallimento**: un solo ritaglio con sha diverso, o un test rosso.

## Domande aperte per gli agenti

1. La forma a 4 metodi con chiavi-stringa e' quella giusta, o manca qualcosa
   che si paghera' caro al secondo backend (es. `apri()` a stream per file
   grandi, cancellazione, metadati)?
2. `bytes` o oggetto-file/stream? Le foto sono ~2-5 MB, i ritagli ~50-200 KB.
3. Conviene davvero scrivere due implementazioni a mano invece di `fsspec`?
4. `esiste()` per-chiave su S3 e' una HEAD per file: su 96 foto x N scontrini
   diventa lento. Meglio un `elenca(prefisso)` unico da mettere in cache?

---

## Esito del consulto agli agenti (2026-08-29)

Consultati Gemini, Vibe, Perplexity col piano integrale.

| Domanda | Gemini | Vibe | Perplexity | Decisione |
|---|---|---|---|---|
| 1. Forma a 4 metodi | d'accordo, manca `cancella` | contrario, manca `cancella` | parziale, manca `cancella` | **`cancella` aggiunto** |
| 2. bytes o stream | bytes | stream | bytes | **bytes** (2 a 1, vedi sotto) |
| 3. a mano o fsspec | a mano | a mano | a mano | **a mano** |
| 4. `esiste()` su S3 | cache interna | cache su `elenca` | pre-scansione esplicita | **pre-scansione esplicita** |

### Le decisioni e il perche'

**`cancella(chiave)` entra subito.** Unanime. Aggiungerlo dopo sarebbe breaking
o produrrebbe scorciatoie laterali.

**`bytes`, non stream** — dissenso 2 a 1, sciolto con la misura e non con la
maggioranza: gli oggetti veri sono foto da 2-5 MB e ritagli da 50-200 KB. Vibe
motiva con "file da 5MB", cioe' col caso massimo, che resta comodamente in RAM.
Lo stream aggiungerebbe gestione di contesti e di fallimenti di rete a meta'
lettura senza guadagno misurabile.
**Via d'uscita dichiarata** (Perplexity): oltre ~50 MB per oggetto si introduce
una `ArchivioStreaming` separata, invece di gonfiare questa interfaccia.

**Niente `fsspec`.** Unanime. L'argomento decisivo e' di Perplexity: `fsspec`
spinge verso un modello *path-based* con `open()`, che confligge proprio con la
regola "la chiave non e' un percorso" su cui si regge tutto il piano.

**La chiave e' opaca — correzione al piano.** Rilievo di Perplexity accolto:
l'ABC **non deve sapere** che la chiave e' uno sha256. E' una stringa opaca; la
regola "sha -> chiave" appartiene al chiamante. Il piano originale confondeva
una convenzione di dominio con un vincolo dell'astrazione.

**`esiste()`: pre-scansione esplicita, non cache implicita.** Qui si segue
Perplexity contro Gemini. Una cache dentro `ArchivioS3` con invalidazione
automatica e' fragile e rende `esiste()` bugiardo se qualcuno scrive nel bucket
da fuori. Meglio che sia il chiamante (fase A) a fare **una** `elenca(prefisso)`
all'avvio e a tenersi il `set` in memoria. Il costo di rete resta visibile nel
codice, che era l'obiezione originale a `fsspec`.
Si documenta nell'ABC: su backend remoti `esiste()` va usato con parsimonia,
`elenca()` serve anche ad alimentare una cache di presenza.

### Interfaccia definitiva

```python
class ArchivioImmagini(ABC):
    def leggi(self, chiave: str) -> bytes: ...
    def scrivi(self, chiave: str, dati: bytes) -> None: ...
    def esiste(self, chiave: str) -> bool: ...
    def elenca(self, prefisso: str) -> Iterator[str]: ...
    def cancella(self, chiave: str) -> None: ...
```

Consenso raggiunto: si implementa. Il consenso non e' una prova — la metrica
dichiarata sopra (317 ritagli identici per sha256) resta da verificare sui dati.

---

## Esito dell'implementazione (2026-08-29)

Stato: **FATTO e verificato sui dati.**

### Cosa e' stato scritto

| File | Ruolo |
|---|---|
| `app/storage/archivio.py` | ABC `ArchivioImmagini` + `ChiaveAssente` |
| `app/storage/locale.py` | filesystem (comportamento di oggi) |
| `app/storage/s3.py` | S3 via boto3, `elenca()` paginato |
| `app/storage/fabbrica.py` | `costruisci_archivio()` legge settings.ini |
| `settings.ini` | `[archivio] tipo = locale\|s3` |
| `tests/storage/test_conformita_archivio.py` | suite di conformita' |

Convertiti al nuovo archivio: `scripts/fase_a_ingestione.py` (lettura foto,
scrittura ritagli ed estratti, elenco, controllo di esistenza) e
`app/etl/etl_engine.py::extract_raw_ocr` (parametro `archivio` opzionale, cosi'
i chiamanti esistenti e gli script diagnostici continuano a funzionare).

### Verifica della metrica dichiarata

**Principale — superata.** Rielaborate 3 foto (`2025-02-14 14.58.52`,
`2025-02-20 07.47.51`, `2025-02-20 07.51.40`) in un archivio vuoto e isolato:
**8 ritagli attesi, 8 prodotti, gli stessi sha256, identici byte per byte.**
Zero persi, zero in piu'. La conversione non cambia il risultato.

**Guardia — superata.** 181 test passati, 1 fallito
(`tests/test_ocr.py::test_pipeline_structure`): verificato con `git stash` che
**falliva gia' prima** di queste modifiche. Non e' una regressione.

**LSP — superata.** Le stesse 11 prove di conformita' girano su
`ArchivioLocale` e su `ArchivioS3` (moto): 22 verdi. `ArchivioS3` non ha un solo
test suo: se ne avesse bisogno, non sarebbe sostituibile.

### Due errori di misura commessi, e cosa insegnano

1. **Confronto sbagliato preso per fallimento.** Il primo confronto dava "1 su
   8" e sembrava una perdita di ritagli. Non lo era: il run precedente aveva
   gia' scritto il registro e il codice aveva correttamente **saltato** le foto
   note. Il ritaglio prodotto era identico all'atteso.
2. **Risultato parziale letto come definitivo.** Il secondo confronto dava
   "2 su 8" mentre il processo **stava ancora girando** (93s per foto su CPU).
   Mancava il riepilogo finale nel log: bastava guardarlo.

Entrambi avrebbero portato a "aggiustare" codice che era gia' corretto. Prima di
dichiarare un fallimento, verificare che la misura sia finita e che il termine di
paragone sia quello giusto.

### Il debito lasciato, dichiarato

- Gli script diagnostici (`genera_fogli_debug.py`, `metrica_iou.py`,
  `verifica_segmentazione.py`, `segmenta_detector.py`, i `benchmark_*`, i
  `kaggle_*`) leggono **ancora dal disco**. Scelta deliberata: girano a mano su
  dati locali. Con `tipo = s3` non funzionerebbero.
- `main.py` non e' stato convertito: e' un percorso alternativo piu' vecchio
  rispetto a `fase_a_ingestione.py`.
- `ArchivioS3` non e' mai stato provato su un bucket vero, solo su `moto`.
  Prima di usarlo in produzione va fatto un giro reale.
- La pre-scansione tiene in memoria un `set` delle chiavi degli estratti: a
  ~300 scontrini e' irrilevante, a milioni andra' ripensata.
