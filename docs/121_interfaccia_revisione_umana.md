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
