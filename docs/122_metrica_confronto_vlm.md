# Metrica del confronto geometrico vs VLM

**Dichiarata il 2026-08-29, PRIMA di misurare.** Cambiarla dopo e' lecito solo
dichiarandolo e rifacendo il confronto.

## La domanda

Il VLM va usato su tutti gli scontrini, solo su quelli che il geometrico sbaglia,
o quasi mai?

Non e' rispondibile oggi: `extraction_confidence` vale 0.0 su tutti e 306 i
record, quindi la soglia "confidenza < 50%" prevista dalla pipeline ibrida non ha
nessun segnale su cui applicarsi. Serve una misura contro un giudizio umano.

## Il campione

I primi ~50 scontrini della coda di revisione, giudicati a mano.

NON e' un campione casuale, ed e' voluto: la coda mette in testa i casi
sospetti, cioe' proprio quelli su cui il VLM dovrebbe aiutare. Il numero che ne
esce risponde a "quanto aiuta dove serve", NON a "quanto e' accurato in
generale". Un campione casuale risponderebbe alla seconda domanda, che qui non
interessa: sugli 85 scontrini gia' validi e quadrati non c'e' niente da
migliorare.

Conseguenza da tenere presente leggendo i risultati: l'accuratezza del
geometrico misurata qui sara' MOLTO piu' bassa del 58% dichiarato, perche' il
campione e' scelto fra i suoi fallimenti.

### Il campione non e' puro: circa 3 casi su 52 sono errori di TAGLIO

Si era detto che nei casi `estrazione` il taglio e' buono per costruzione.
E' FALSO, e lo ha mostrato la revisione a mano dello scontrino #302: il ritaglio
conteneva DUE scontrini appiccicati (Mercadona 15,75 EUR e Alcampo), quindi lo
scarto di 12,49 EUR non era un errore di lettura ma un errore di segmentazione
travestito da errore di estrazione. La coda non se ne accorge perche' classifica
`estrazione` chiunque abbia due o piu' righe e non quadri, senza sapere quanti
scontrini contenga il ritaglio.

MISURATO sui 52: il rapporto somma_righe/totale_stampato ha mediana 1.00, e solo
3 casi stanno sotto il 40% - il sintomo di un ritaglio che contiene un totale
appartenente a un altro scontrino. Su questi tre nessuno dei due estrattori puo'
vincere, perche' leggono entrambi un ritaglio sbagliato.

Tre casi su 52 non spostano il confronto, quindi il campione resta valido. Vanno
pero' esclusi dal conteggio finale ed elencati, invece di essere contati come
sconfitte dell'estrattore.

## Metrica principale

**Scontrini corretti**, cioe' giudicati `dati:giusti` da un umano.

    accuratezza = scontrini con dati giusti / scontrini giudicati

Confronto fra: estrazione geometrica (attuale) e VLM, sugli STESSI scontrini,
contro lo stesso giudizio umano.

LIMITE DICHIARATO: il giudizio umano e' binario (giusti/sbagliati per l'intero
scontrino), non riga per riga. Non si potra' quindi dire "quanti prodotti in
piu' azzecca il VLM", solo "quanti scontrini in piu'". E' la metrica meno
sensibile delle due, scelta perche' l'altra richiederebbe di trascrivere a mano
ogni riga di ogni scontrino.

## Metriche di guardia (non devono peggiorare)

- **Allucinazioni**: prodotti inventati, assenti dallo scontrino. Il benchmark
  precedente le dava al 4.2% per LLaVA e a 0% per il geometrico, che non puo'
  inventare per costruzione. Se il VLM vince sulla metrica principale ma
  allucina, non e' una vittoria: un numero inventato e' peggio di un buco
  dichiarato.
- **Scontrini che quadravano e smettono di quadrare**: il totale stampato e' un
  giudice terzo, che non ha letto ne' l'uno ne' l'altro estrattore.
- **Righe perse**: il VLM che restituisce `[]` dove il geometrico trovava righe
  giuste.

## Cosa conta come fallimento

Il VLM NON viene adottato su tutti gli scontrini se:

- non supera il geometrico sulla metrica principale, OPPURE
- lo supera ma peggiora una metrica di guardia, OPPURE
- il campione e' troppo piccolo perche' la differenza sia distinguibile dal caso.

Con ~50 scontrini il margine d'errore e' circa ±14 punti (Perplexity e Vibe,
vedi 103): una differenza sotto i 14 punti NON e' un risultato, e va dichiarata
tale invece di essere letta come una vittoria.

## Cosa NON si decide qui

Come conciliare le due letture quando divergono. E' una decisione sulla
semantica dei dati, quindi va sottoposta agli agenti, e va presa DOPO aver visto
dove e quanto divergono. La regola proposta, da validare:

1. concordi e quadrano col totale stampato -> valido
2. uno solo quadra col totale stampato -> vince quello
3. nessuno quadra, o manca il totale -> nessuno vince, va in revisione con
   entrambe le letture visibili

Il VLM oggi NON riceve l'output dell'OCR: legge solo i pixel (vedi il prompt in
scripts/kaggle_benchmark_llava.py). E' una proprieta' da conservare: due lettori
indipendenti che sbagliano in modo scorrelato sono cio' che permette di dire
DOVE c'e' un problema. Dare al VLM la lettura dell'OCR lo ancorerebbe a quella e
farebbe perdere proprio l'indipendenza che rende utile il confronto.

---

# Revisione della metrica, 2026-08-30

Dichiarata PRIMA di guardare i risultati del VLM, e prima ancora di lanciarlo.

## Perche' la metrica principale non funziona piu'

Sui 33 scontrini giudicati a mano, quelli con **dati giusti sono ZERO**:

    taglio:ok        dati:sbagliato      28
    taglio:sbagliato dati:sbagliato       4
    taglio:sbagliato dati:non_giudicato   1

"Quanti scontrini corretti per ciascun metodo" darebbe quindi 0% al geometrico,
e qualunque risultato del VLM sarebbe un miglioramento. Non e' un confronto: e'
un pavimento. Il campione e' scelto fra i fallimenti del geometrico, quindi
questo era prevedibile - ma non era stato previsto, ed e' un errore di chi ha
scritto la metrica (io).

## Metrica principale, sostituita

**Righe di prodotto corrette per scontrino**, contro il totale stampato come
giudice terzo:

    quadra(metodo) = |somma_righe(metodo) - totale_stampato| <= 0,02 EUR

    metrica = scontrini che quadrano / 28

Il totale stampato non e' stato letto da nessuno dei due estrattori dalla stessa
via dei prodotti, quindi resta un arbitro indipendente. E' una misura debole (si
puo' quadrare per compensazione di errori) ma e' automatica e non richiede di
trascrivere a mano ogni riga.

Campione: i **28 con taglio:ok**. I 5 col taglio sbagliato sono esclusi: leggono
entrambi un ritaglio sbagliato, nessuno dei due puo' vincere.

## Metriche di guardia (invariate nella sostanza)

- **Allucinazioni**: prodotti assenti dallo scontrino. Il geometrico non puo'
  inventare per costruzione, LLaVA era dato al 4.2%.
- **Righe perse**: il VLM che restituisce [] dove il geometrico trovava righe.
- **Nomi di prodotto plausibili**: MISURATO che il geometrico sbaglia il nome del
  NEGOZIO quasi sempre (`Cal`, `Cae`, `NILDA DIAZ GONZALES` che e' il cliente,
  `C/VENEÇUELA` che e' l'indirizzo, `Sindria Ratlada` che e' un prodotto). Lo
  stesso difetto colpisce i nomi dei prodotti. Va guardato se il VLM lo ripete.

## Cosa conta come fallimento

Con 28 scontrini il margine d'errore e' circa ±18 punti. Una differenza sotto i
18 punti NON e' un risultato e va dichiarata tale.

Il VLM non viene adottato se non supera il geometrico, o se lo supera peggiorando
una guardia - in particolare inventando prodotti, perche' un numero inventato e'
peggio di un buco dichiarato.

## La diagnosi che ha motivato tutto questo

L'OCR NON e' il collo di bottiglia. MISURATO sullo scontrino #137: PaddleOCR
produce 91 righe di testo, coi nomi catalani corretti (`Alberginia`, `Cogombre`,
`Pastanaga`, `Pera Conference`), e nel database arrivano 3 prodotti.

L'OCR restituisce ogni parola su una riga separata: il nome e il suo prezzo non
sono mai sulla stessa riga, e il collegamento va ricostruito per coordinate
(app/etl/geometria.py). E' li' che si perde. Le note della revisione umana dicono
la stessa cosa: "preso solo colonna con importi, non voci" (#9), "prodotto preso
come nome del supermercato" (#14, #22), "preso EUR/kg per kg" (#45).

Sono tutti errori di ASSOCIAZIONE, non di lettura: il testo giusto nella casella
sbagliata. E' il compito in cui un modello che guarda l'immagine ha un vantaggio
strutturale, perche' VEDE l'allineamento invece di dedurlo.


---

# Scoperta collaterale: righe scartate in silenzio al caricamento

MISURATO il 2026-08-30, preparando il confronto.

In 12 casi su 25 il campo `receipts.total_computed` NON coincide con la somma
delle righe presenti in `receipt_lines`. Esempio, scontrino #57: il campo dice
33,71 EUR, le righe salvate sommano 6,39.

## Perche'

`fase_d_carica_db.py` scrive `total_computed` dalla somma calcolata in fase C su
TUTTI i prodotti trovati, ma inserisce solo le righe che hanno un NOME:
`trova_o_crea_prodotto` restituisce None sul nome vuoto e la riga viene saltata
con un `continue`, senza traccia.

E il geometrico lascia il nome vuoto molto spesso. Nel #57, su 12 prodotti
trovati **9 hanno prezzo corretto e nome assente**:

    nome=''                      prezzo=4.63
    nome='Pango Uutat Promecis'  prezzo=2.75
    nome=''                      prezzo=2.77
    ...

E' la stessa diagnosi della revisione umana, vista dall'altro capo: la nota di
chi rivedeva lo scontrino #9 diceva "preso solo colonna con importi, non voci".
Non era un caso isolato, e' il modo tipico in cui questo estrattore fallisce.

## Conseguenza sul confronto

La somma del geometrico si ricalcola dalle righe SALVATE, non si legge da
`total_computed`. Dare credito per righe che non sono nel database
significherebbe misurare dati che il progetto non possiede.

## Quanto pesa, su tutto il corpus

MISURATO il 2026-08-30 sui 287 scontrini geometrici:

    prodotti trovati:                     1752
    scartati perche' senza nome:           237  (14%)
    scontrini che ne perdono almeno uno:    57  (20%)

    valore dei prodotti trovati:       6133.62 EUR
    valore scartato:                   2054.67 EUR  (33%)

**Il 33% del valore economico non entra nel database.** Le righe perse sono il
14% in numero ma un terzo in valore: i prodotti costosi stanno spesso su righe
complesse, dove l'associazione col nome fallisce piu' facilmente.

Alcuni scontrini perdono il 100% del proprio valore - uno da 849,64 EUR in cui
OGNI prodotto ha prezzo corretto e nome vuoto, quindi non ne entra nessuno.

## Conseguenza sul progetto, da decidere a parte

Uno scontrino puo' oggi risultare `SOMMA_IN_DIFETTO` per due ragioni diverse che
il database non distingue: le righe non sono state lette, oppure sono state
lette e poi scartate perche' senza nome. Sono problemi diversi con rimedi
diversi, e oggi si confondono.

Il minimo sarebbe contare le righe scartate e riportarlo, invece di perderle in
silenzio: un buco dichiarato resta verificabile, uno silenzioso no. Un prezzo
noto senza nome e' un dato PARZIALE, non un dato assente: buttarlo perde anche
la parte che si sapeva, e falsa ogni report di spesa costruito sul database.


---

# RISULTATO, 2026-08-30

## Il numero

    METRICA PRINCIPALE - quadrano col totale stampato (+/- 0,02 EUR)
      geometrico:   0 / 28  (0%)
      VLM:          0 / 28  (0%)

      escludendo i 7 col totale stampato letto male:
        geometrico: 0 / 21   VLM: 0 / 21

    GUARDIE
      VLM json illeggibile:  23 / 28
      righe perse dal VLM:   20  (il geometrico ne trovava, il VLM no)

Differenza: 0 punti, sotto il margine di +/-18. **NON e' un risultato**, ed e'
anche una sconfitta secca sulle guardie.

## Verdetto: il VLM NON si adotta

Non per la metrica principale - che e' 0 a 0 e quindi non dice nulla - ma per le
guardie, che era esattamente il motivo per cui erano state dichiarate prima.

## Cosa fa davvero il VLM: inventa

Su Kaggle, 23 risposte su 28 sono JSON troncati perche' il modello entra in
LOOP e ripete la stessa riga fino a esaurire i token:

    {"name": "Burgos Natural", "price": 4.99},
    {"name": "Burgos Natural", "price": 4.99},
    ... all'infinito

I prezzi sono tutti dello stesso stampo - 4.99, 3.99, 24.99, 2.99 - cioe'
plausibili in astratto e non presi dallo scontrino.

L'unica risposta "riuscita" aveva RICOPIATO L'ESEMPIO DEL PROMPT:

    {"name": "product name", "price": 39.99},
    {"name": "another product", "price": 19.99}

`product name` e `another product` sono i segnaposto scritti nel FORMAT. Il
modello non ha guardato l'immagine.

## Il loop era colpa del kernel, l'allucinazione no

VERIFICATO facendo girare lo STESSO modello (llava:7b) in locale via Ollama:
4 su 4 con JSON valido, nessun loop. Quindi il troncamento veniva dalla
configurazione su Kaggle (max_new_tokens=512 con do_sample=False su
transformers 5.0), non dal modello.

Ma il locale allucina lo stesso, in forma piu' ordinata:

    #14  MERCADO SAN ANTONIO   21.90   <- e' il NEGOZIO, non un prodotto
    #23  MATTRESS             399.00   <- scontrino IKEA il cui totale e' 16,00 EUR
    #23  BEDDING               24.95
    #14  CHICKEN BREASTS        4.70   <- inglese, su scontrino catalano

Il modello riconosce "scontrino IKEA" e genera cio' che ci si ASPETTEREBBE di
comprare da IKEA. Non legge: immagina.

## Perche' e' peggio del geometrico, nonostante il pareggio

Il geometrico sbaglia in modo VERIFICABILE: lascia il nome vuoto, o prende la
colonna sbagliata. L'errore si vede e si puo' correggere.

Il VLM produce nomi e prezzi plausibili e sbagliati, che nessun controllo
automatico distingue da quelli veri. E' precisamente il caso che il metodo del
progetto vieta: "meglio un buco dichiarato che un numero inventato".

Nota su #14: la somma del VLM (30,10) era vicinissima al totale stampato
(30,47), grazie a una riga inventata da 21,90. Senza le metriche di guardia
questo sarebbe stato letto come una vittoria.

## Cosa NON e' stato dimostrato

Che i VLM in generale non servano. E' stato provato UN modello (LLaVA 7B) con UN
prompt, su 28 scontrini. Restano non provati:

- modelli piu' recenti e adatti al testo denso (qwen2.5vl e' installato in
  locale ma non e' stato misurato: va in timeout mentre la CPU e' occupata)
- un prompt senza esempio di formato, visto che l'esempio e' stato copiato
- dare al VLM il testo OCR insieme all'immagine (oggi non lo riceve)

## La cosa piu' utile emersa non riguarda il VLM

Il 33% del valore economico non entra nel database perche' le righe senza nome
vengono scartate in silenzio. Quello e' un difetto misurato, con un rimedio
chiaro, e vale piu' di qualunque cambio di estrattore.
