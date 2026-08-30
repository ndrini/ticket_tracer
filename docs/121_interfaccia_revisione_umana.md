# Fase 2 — Interfaccia di revisione umana

Stato: **FATTA e provata**. Data: 2026-08-29.

## Il problema

Rivedere a mano 306 scontrini non ha senso, e rivederne un campione a caso
nemmeno: il campione pesca soprattutto scontrini che vanno bene. Serve guardare
**quelli che hanno piu' probabilita' di essere sbagliati**, e sapere quali sono
prima di aprirli.

## La coda nasce da una misura, non da un'intuizione

Sui 306 scontrini nel database, al 2026-08-29:

| Fascia | N | Sospetto |
|---|---|---|
| zero righe estratte | 39 | **ritaglio** |
| una riga sola | 65 | **ritaglio** |
| non quadrano (ECCESSO/DIFETTO) | 52 | **estrazione** |
| totale assente | 65 | non verificabile |
| validi e pieni | 85 | non si guardano |
| **in coda** | **221** | |

Il dato che ha deciso la forma dell'interfaccia: **104 scontrini su 306 hanno
zero o una riga**. Su uno scontrino della spesa una riga sola non e'
un'estrazione riuscita a meta': e' quasi certamente un ritaglio sbagliato. Per
questo la prima domanda e' sul taglio, non sui numeri.

### L'ordine, e perche' e' quello

1. **taglio** (104) — zero o una riga
2. **estrazione** (52) — non quadrano, dal delta piu' grande (fino a 671 EUR)
3. **non verificabile** (65) — manca il totale stampato

**Il taglio batte l'estrazione anche a parita' di gravita'**, ed e' una scelta
deliberata protetta da un test: un ritaglio sbagliato rende inutile qualunque
domanda sui dati, quindi chiedere prima "i conti tornano?" sprecherebbe il tempo
di chi rivede. Chi risponde "taglio sbagliato" puo' passare oltre senza
giudicare i numeri.

## Cosa si vede: quattro riquadri

Richiesta dell'utente (2026-08-29): *"ritaglio + foto affiancata + risultato
dell'estrazione + confidence del processo di estrazione, cosi da dover rivedere,
a processo rodato, solo le foto problematiche"*.

**Foto d'origine** (per vedere cosa il ritaglio ha tagliato via) · **Ritaglio** ·
**Righe estratte** (con negozio, data, totale stampato, somma righe, scarto) ·
**Confidenza**. Le immagini si ingrandiscono a schermo intero con un clic.

Tastiera: `1`/`2` taglio buono/sbagliato, `3`/`4` dati giusti/sbagliati,
`Invio` salva e avanza.

## Il dubbio che era stato dichiarato, e come si e' chiuso

Nel piano si era segnalato che `foto_origine` poteva essere vuoto. **Misurato:
lo e' per 88 scontrini su 306 nel database.** Ma `data/foto_viste.json` copre
**306 su 306**. Quindi la foto d'origine si ricava dal registro, non dalla
colonna: il riquadro non resta mai vuoto. Il buco dichiarato e' chiuso.

## Cosa NON fa: nessuna correzione

Decisione dell'utente: *"solo giudizio. se sbagliato poi le segneremo e le
correggeremo in un modo che decideremo"*. Coerente col metodo: **segnalare, non
correggere d'ufficio.**

Il giudizio va in `manual_review_queue` — la tabella che la migrazione Week 2
aveva gia' creato e che nessuno aveva mai riempito (0 righe) — piu'
`receipt_lines.verified_by_human`. Non si e' inventato un file JSON a parte:
avrebbe spezzato in due il registro di cio' che e' stato guardato.

Solo un giudizio **positivo** marca le righe come verificate: "sbagliato" dice
che sono state guardate, non che sono giuste.

## Come si usa

    uv run python scripts/revisione_umana.py --chi aless@ndrini.eu --apri

Poi http://localhost:8098. Tutto in locale. Si salva a ogni giudizio, non alla
chiusura: interrompere a meta' non perde nulla, e la coda si ricostruisce dal
database, quindi si riprende da dove si era rimasti.

Le immagini passano dall'`ArchivioImmagini` della fase 1: **la stessa interfaccia
funziona con le foto su S3**, senza modifiche.

## File

| File | Ruolo |
|---|---|
| `app/revisione/coda.py` | chi rivedere e in che ordine |
| `app/revisione/dati.py` | la scheda da mostrare, e dove va il giudizio |
| `scripts/revisione_umana.py` | server HTTP (stdlib) + pagina |
| `tests/revisione/test_coda.py` | 9 prove sull'ordinamento |

Modello: `vista_stradale/scripts/setaccio_umano.py` — `http.server`, HTML come
costante, una POST per azione, salvataggio a ogni battuta, e soprattutto
**scrivere nel registro che esiste gia'** invece di inventarsene uno.

## Verifica

- 9 test sull'ordinamento, verdi. L'HTML non e' testato: si verifica usandolo,
  mentre l'ordine decide dove va il tempo di chi rivede.
- Provata end-to-end su una **copia** del database: pagina 200, ritaglio 58 KB,
  foto d'origine 3 MB, chiave inesistente -> 404 (non un crash).
- Giro completo del giudizio: scritto in `manual_review_queue`, coda scesa da
  221 a 220, scontrino giudicato uscito, righe marcate su giudizio positivo.
- Suite completa: 190 verdi, 1 rosso (`test_pipeline_structure`) **preesistente**.
- Database di produzione intatto: 0 righe in `manual_review_queue`.

## Debito lasciato, dichiarato

- Non c'e' modo di **tornare indietro** su un giudizio dato per sbaglio: si
  corregge a mano nel database. Da rivedere se capita spesso.
- La coda si ricalcola a ogni scheda: a 306 scontrini e' istantaneo, a decine di
  migliaia andra' paginata.
- Nessuna autenticazione: il server ascolta solo su `127.0.0.1`.
- **Ogni giudizio "sbagliato" e' un buco dichiarato che va poi chiuso.** Serve
  un passo successivo che li raccolga e decida cosa farne, altrimenti la
  marcatura diventa un alibi.

---

# Parte 2 — La pagina di elaborazione

Stato: **FATTA e provata**. Data: 2026-08-30.

La revisione risponde alla domanda "questo scontrino e' giusto?". Questa pagina
risponde a un'altra: "a che punto siamo, e cosa conviene fare adesso?".

## Il quadro d'insieme

Prima si scopriva solo lanciando i comandi. Ora `/riassunto` li dice
all'apertura. Sui dati veri del 2026-08-30:

    foto sul disco          207     di cui 13 mai ingerite
    scontrini ritagliati    360     360 col testo letto
    strutturati             325
      chiusi                178     la somma quadra e i nomi ci sono
      da ripassare          147

**Non chiede niente a Google Drive**, ed e' la scelta che conta. Lassu' ci sono
833 file: contarli a ogni caricamento sarebbe una chiamata di rete per un numero
che cambia solo quando si preme un pulsante, e la pagina diventerebbe lenta e
inservibile senza connessione. Due test lo impongono — uno vieta di costruire
l'archivio remoto, l'altro vieta `socket.connect` — perche' una buona intenzione
scritta in un commento non regge alla prima fretta.

## L'ordine si mostra, non si impone

Le fasi sono numerate da 1 a 7 e ognuna dice cosa fa, quando si esegue e quanto
costa. Ma nessun controllo impedisce di lanciarle fuori ordine.

E' deliberato: ogni script e' **gia' idempotente** e salta cio' che ha fatto. Un
blocco nell'interfaccia sarebbe una SECONDA verita' sullo stato del lavoro,
libera di divergere da quella vera — e quando divergesse, impedirebbe un'azione
legittima senza spiegare perche'.

## La fase D c'e', disabilitata, col motivo scritto

Il caricamento nel database e' sospeso: sui formati a peso il nome e il prezzo
vengono accoppiati male **e la somma quadra lo stesso**, quindi gli scontrini
sbagliati risulterebbero `chiuso`, cioe' certificati come buoni.

Il pulsante non e' stato tolto. Un pulsante assente e' una domanda ("perche' non
si puo' caricare nel database?"), uno disabilitato con la ragione accanto e' una
risposta. Chi torna fra sei mesi la trova nella pagina, non in un commento.

La difesa non e' solo visiva: `database` **non compare fra i comandi eseguibili**
del server, quindi la rotta non lo lancerebbe nemmeno ricevendo la richiesta a
mano. Un `disabled` nell'HTML sta nel browser, e il browser non e' un guardiano.
Un test lo verifica.

## Cosa NON e' stato aggiunto, e perche'

Consultati Vibe e Perplexity, concordi (Gemini fuori quota giornaliera):

| Tentazione | Perche' no |
|---|---|
| Pulsante "esegui tutto" | Bloccherebbe per ore senza potersi fermare in mezzo |
| Avvio automatico all'arrivo di foto nuove | Contro "segnalare, non correggere d'ufficio" |
| Framework web (Flask, FastAPI) | Il progetto sta in libreria standard, e basta |
| Stato di Drive in tempo reale | Una chiamata di rete a ogni caricamento |
| Autenticazione | Utente singolo in locale: sarebbe codice morto |
| Polling continuo del riassunto | Cambia solo dopo un lavoro: si rilegge allora |

## Come e' fatta

- `app/revisione/riassunto.py` — i numeri e l'elenco delle fasi. Nessuna rete.
- `scripts/revisione_umana.py` — rotta `GET /riassunto`, pagina che disegna i
  pulsanti **dai dati**: prima erano scritti a mano nell'HTML, cioe' due elenchi
  da tenere allineati a memoria. Un test impedisce che tornino.
- I comandi restano invocazioni degli stessi script della riga di comando, mai
  logica duplicata nel server.

## Prove

31 test, scritti prima del codice (rosso, poi verde). Oltre ai conteggi:

- il riassunto non tocca la rete (due test, uno per via);
- ogni comando punta a uno script che **esiste** — un refuso qui fallirebbe solo
  alla pressione del pulsante, minuti dopo;
- ogni fase mostrata e' lanciabile, e la sospesa non lo e';
- i comandi Drive contengono `--esegui`: senza, direbbero soltanto cosa
  farebbero, e il pulsante sembrerebbe riuscito senza caricare niente.

Provata anche contro il server vero: `/riassunto` risponde coi numeri qui sopra,
`/ingestione` e la pagina di revisione rispondono 200.
