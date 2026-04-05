# Ticket Tracer: Guida all'Uso (Transizione verso la Produzione)

Questo documento spiega come passeremo dalla **fase di sviluppo e test** alla **fase di utilizzo reale** dell'applicazione.

## 1. Il Database: Dove viene salvato?

Essendo Ticket Tracer basato su **SQLite**, il database non è un server separato, ma un semplice **file locale** (es. `ticket_tracer.db`).
Tutto il contenuto (scontrini, prodotti, dizionario aliases in varie lingue come Latte/Milk/Mleko) viene salvato fisicamente all'interno di questo file.

- **Durante i test (Fase di costruzione):** Usiamo un database temporaneo, ad esempio `data/test_spese.db` o un database in memoria (`:memory:`), che può essere distrutto e ricreato a ogni test.
- **Durante l'utilizzo reale (Produzione):** Creeremo un file persistente, ad esempio in `data/db/produzione.db` (o una directory specificata nell'ambiente di produzione). L'app userà _sempre_ questo file, facendo sì che i dati rimangano salvati e cumulati nel tempo.

Il passaggio avviene configurando l'app in modo che, quando viene avviata normalmente (non dai file di test), le venga passata la cartella e il nome del file definitivo.

## 2. Le Cartelle di Utilizzo (Fase Operativa)

Per usare Ticket Tracer nel quotidiano, organizzeremo l'ambiente con queste cartelle principali:

### `data/db/` (Il "Cervello" dei Dati)
Conterrà il file `produzione.db`. Nessuno deve toccare questo file manualmente (se non per i backup). È qui che lo script salverà tutti i riconoscimenti, le parole alias e i dati economici.

### `data/input_scontrini/` (La Casella di Ingresso)
Questa è la cartella dove tu ("l'utente") andrai a salvare fisicamente o tramite cellulare le foto degli scontrini (es. `scontrino_esselunga_12_marzo.jpg`).
Lo script principale (`main.py`) opera in due fasi (Step 1 e Step 2):

---
**Fase 1: Estrazione Testo (Lenta ma Singola)**
Lo script ascolta la cartella `input_scontrini/`:
1. Prende la foto.
2. La passa a `PaddleOCR` (per estrarre il testo grezzo).
3. Salva l'output in un file JSON nella cartella `data/ocr_cache/`.
4. Sposta l'immagine originale in `data/archived_scontrini/`.

### `data/ocr_cache/` (La Memoria Intermedia)
Qui finiscono i file JSON con il testo estratto. Poiché analizzare l'immagine con l'OCR è l'operazione più "pesante", la facciamo una sola volta. Il risultato testuale è salvato qui.

---
**Fase 2: Analisi Intelligente (Ripetibile e Veloce)**
Lo script guarda la cartella `data/ocr_cache/`:
1. Prende il testo JSON generato al punto precedente.
2. Lo passa a `Ollama` (per la normalizzazione multilingua, es: Yogurt, Milch).
3. Lo inserisce nel DB in `data/db/produzione.db`.
4. Sposta il file JSON in `data/archived_ocr/`.

In questo modo, se scopri che Ollama ha interpretato male qualcosa o decidi di aggiustare il prompt, **puoi ripescare il file JSON e ri-eseguire solo la Fase 2 in un istante**, senza dover ripassare l'immagine attraverso l'OCR.


### `data/archived_scontrini/` e `data/archived_ocr/` (Gli Archivi)
Una volta che l'immagine o il JSON sono stati processati con successo, l'app sposta i file originali qui. Così saprai sempre che le cartelle "input" o "cache" contengono solo ciò che deve ancora essere processato.

### `exports/` (I Risultati)
Qui verranno salvati tutti i report generati dal modulo `stat` (es. grafici delle spese mensili, report CSV per Excel sulla spesa suddivisa per categorie).

## 3. Come avviene il passaggio (Prossimi Passaggi Tecnici)

Attualmente stiamo costruendo i "mattoni" base (il database, il test dell'inserimento, il test di PaddleOCR).
Per passare all'uso pratico dovremo:

1. **Creare lo script principale (`main.py` o `run.py`)**: Uno script che unisce il modulo OCR, il modulo DB e il modulo Statistiche.
2. **Definire i percorsi assoluti**: Nello script `main.py` daremo come parametro `db_path = "data/db/produzione.db"` e il percorso per leggere le immagini `images_path = "data/input_scontrini/"`.
3. **Punto di caricamento iniziale del Dizionario**: Se hai già una mappatura delle parole in varie lingue (es. Ceco, Italiano, Francese), lo caricheremo nel DB della produzione una volta sola al primo avvio.

---
**In sintesi**: Non hai bisogno di server complessi, tutto rimarrà confinato nella cartella del tuo progetto (o dove preferisci tu), garantendo la privacy e la gestione offline al 100%. Quando riterremo i moduli stabili (passeranno tutti i test in pytest), lo script `main.py` sarà il nostro interruttore per avviare l'uso reale!
