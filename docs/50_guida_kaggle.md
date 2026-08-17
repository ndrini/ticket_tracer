# Usare Kaggle come GPU gratuita (guida per un altro progetto)

Nota per chi legge: qui Kaggle non serve per le competizioni, serve come **GPU gratuita a noleggio** (~30 ore/settimana). Il modello mentale è quello di un sistema batch: si carica un **dataset** (i dati in ingresso, immutabili), si spinge un **kernel** (uno script che gira dall'inizio alla fine e termina), si scarica l'**output**. Nessuna sessione interattiva, nessun notebook da guardare.

Le sigle usate: CLI = Command Line Interface, l'interfaccia a riga di comando; GPU = Graphics Processing Unit, la scheda grafica; EXIF = Exchangeable Image File Format, i metadati incorporati nelle foto (fra cui il GPS); T4 e P100 = due modelli di GPU Nvidia.

## 1. Autenticazione

`pip install kaggle` (o `uv add kaggle`). Le credenziali stanno in `~/.kaggle/access_token`, il formato nuovo.

- dove	~/.kaggle/access_token — nella tua home, fuori dal repository
- cos'è	il token nuovo KGAT_…, 38 byte
- permessi	-rw-------: leggibile solo da te
- dal 2 agosto 2026:funziona da allora

scaricabile da Kaggle → Settings → API → Create New Token. Due formati in circolazione:


 col token nuovo **lo username non è nel file**. Ogni identificatore su Kaggle è `username/slug`, quindi va ricavato altrove. Il modo che funziona è chiedere all'API i propri dataset e leggere il proprietario dalla prima riga:

```bash
kaggle datasets list --mine --csv
```

Da script, usare il modulo `csv` e non `split(",")`: un titolo che contiene una virgola produce uno username sbagliato, cioè un dataset creato nel posto sbagliato. E se non si deduce, **chiedere all'utente** invece di indovinare.

Permessi: `chmod 600 ~/.kaggle/kaggle.json`, altrimenti la libreria protesta.

## 2. Creare un dataset

Un dataset è una cartella più un file `dataset-metadata.json`:

```json
{
  "title": "Titolo leggibile",
  "id": "tuonome/mio-dataset",
  "licenses": [{"name": "other"}]
}
```

Poi:

```bash
kaggle datasets create -p cartella/ --dir-mode zip     # prima versione
kaggle datasets version -p cartella/ -m "nuovo lotto"  # versioni successive
```

Cose imparate a spese nostre:

- **La privacy non sta nel metadata.** Dipende solo dall'assenza di `--public` sulla riga di comando: nella libreria `dataset_create_new(public: bool = False)` e poi `is_private = not public`. Se i dati sono di un cliente, lo script non deve avere *nessun* modo di passare `--public`.
- **Verificare, non supporre.** `kaggle datasets metadata <owner>/<slug> -p <cartella>` riscarica il metadata; il campo è `isPrivate`. ⚠️ Il metadata **scaricato** annida tutto sotto `info`, mentre quello che si carica è piatto: cercare `isPrivate` al primo livello restituisce `None` anche su un dataset correttamente privato. Un falso allarme è peggio di nessun allarme, perché la volta che serve non gli si crede più.
- **Togliere l'EXIF prima di caricare**, se le foto sono di un cliente. Qui l'EXIF contiene il GPS, cioè esattamente il dato che si vende. La privacy è una politica; un file spogliato è un fatto. E il controllo va scritto **separato** dalla scrittura: una funzione copia-senza-metadati, un'altra che rilegge tutto e solleva al primo file che ha ancora metadati. Se un giorno lo spogliamento si rompe, il controllo se ne accorge prima dell'upload.
- **`rglob`, non `glob`**, se la cartella è annidata. Con `glob("*.jpg")` su un albero di sottocartelle si carica un dataset vuoto senza nessun errore.
- Ogni upload ha una **prova a vuoto** come comportamento predefinito e un flag `--esegui` per fare davvero. Il default non deve far uscire dati dalla macchina.

Nel kernel il dataset compare in sola lettura sotto `/kaggle/input/<slug>/`.

## 3. Creare ed eseguire un kernel

Cartella con lo script più `kernel-metadata.json`:

```json
{
  "id": "tuonome/mio-kernel",
  "title": "mio kernel",
  "code_file": "mio_kernel.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": true,
  "enable_gpu": true,
  "machine_shape": "NvidiaTeslaT4",
  "enable_tpu": false,
  "enable_internet": true,
  "dataset_sources": ["tuonome/mio-dataset"],
  "competition_sources": [],
  "kernel_sources": [],
  "model_sources": []
}
```

```bash
kaggle kernels push -p cartella/ --accelerator NvidiaTeslaT4
kaggle kernels status tuonome/mio-kernel
kaggle kernels output tuonome/mio-kernel -p data/output/
```

Il push **avvia anche l'esecuzione**: non serve un comando "run".

Le trappole, tutte pagate in ore perse:

- ⛔️ **La T4 va chiesta esplicitamente.** Lasciando scegliere a Kaggle arriva una **P100**, capability CUDA `sm_60`, mentre il PyTorch preinstallato parte da `sm_70`. Il modello si carica, scarica i pesi, e muore alla prima inferenza con `CUDA error: no kernel image is available for execution on the device`. L'avviso è nel log ("Tesla P100 … is not compatible with the current PyTorch installation") ma **non ferma l'esecuzione**: sembra innocuo ed è la causa.
- ⚠️ **`NvidiaTeslaT4` con la maiuscola iniziale.** `nvidiaTeslaT4` viene accettato senza errore e **ignorato**: la CLI non valida il valore e arriva comunque la P100. Fallimento silenzioso, costa un giro completo.
- ⚠️ **Lo slug deve corrispondere al titolo.** Se non corrisponde, Kaggle genera uno slug suo diverso dall'`id` richiesto, e da lì in poi `status` e `output` cercano un kernel che non esiste. Un titolo italiano tipo «pre-annotazione» diventa `…-pre-annotazione-…`: scrivere il titolo con parole semplici e lo slug identico in kebab-case.
- **`kernel_type: "script"`**, non `notebook`: gira in batch e termina. I marcatori `# %%` restano leggibili nell'editor di Kaggle, ma non si deve dipendere dalle magie di IPython — l'installazione delle dipendenze va fatta con `subprocess.run([sys.executable, "-m", "pip", "install", …])`, non con `!pip`.
- **`enable_internet: true`** serve per scaricare pesi da Hugging Face; senza, l'unico input sono i dataset.
- **`is_private: true`**: un kernel pubblica il codice **e l'output**. Se l'output riguarda dati del cliente, la privacy va affermata e lo script deve rifiutare il push se il flag è diverso.
- Un controllo prima del push (`is_private` vero, `enable_gpu` vero) costa cinque righe e ha già evitato di spingere lavori senza GPU.

Tutto ciò che lo script scrive in `/kaggle/working/` diventa l'output scaricabile.

## 4. Due regole di metodo che valgono più delle configurazioni

- **Smoke test obbligatorio.** Prima di ogni kernel nuovo, un giro su **una sola** immagine (o poche decine). I fallimenti sopra — la P100, lo slug sbagliato, il dataset vuoto — si manifestano tutti nei primi trenta secondi, ma solo se si guarda dopo trenta secondi invece che dopo l'ora.
- **Mai oltre l'ora di GPU per esperimento.** Il budget settimanale è finito e i lavori lunghi mascherano gli errori: un kernel che gira quattro ore e fallisce alla fine ha bruciato un ottavo della settimana per non dire niente.
- **Registrare il tempo per elemento**, sempre. Sembra ovvio e per mesi non lo abbiamo fatto: senza quel numero non si può scegliere fra un modello preciso e uno quindici volte più veloce, che a volume grande spesso vince.

## 5. Esempi da copiare

Nel progetto `vista_stradale` (branch `feat_fase1_screening`):

- `scripts/kaggle_carica_dataset.py` — upload privato con spogliamento EXIF, prova a vuoto, verifica della privacy dopo l'upload
- `scripts/kaggle_lancia_notebook.py` — push del kernel, `--stato`, `--scarica`, controlli pre-push
- `data/kaggle_*/kernel-metadata.json` — una dozzina di kernel reali già configurati
- `tests/test_kaggle_upload.py` — i test che coprono gli errori silenziosi qui sopra
