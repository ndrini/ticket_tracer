# Groq: usarlo negli script e dietro altri assistenti

Appunti verificati sul campo il 2026-08-18, riusabili fuori da questo progetto.
Groq non è un modello: è un fornitore che serve **modelli aperti** (di altri) molto in fretta, con un piano gratuito.
Da non confondere con **Grok** di xAI, che è un modello a pagamento e una società diversa.

## Cosa dà, concretamente

Chiave da `console.groq.com`, sezione *API Keys*, accesso con Google o GitHub.
L'interfaccia è **compatibile con quella di OpenAI**: qualunque programma che sappia parlare con OpenAI parla con Groq cambiando due impostazioni.

Il catalogo si legge da sé, e cambia nel tempo:

```bash
curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY" \
  | python3 -c "import sys,json;[print(m['id']) for m in json.load(sys.stdin)['data']]"
```

Al 2026-08-18: `openai/gpt-oss-120b` e `-20b` (ragionamento), `qwen/qwen3.6-27b` (**vede le immagini**), `whisper-large-v3` (trascrizione audio), `groq/compound` (con ricerca web incorporata).

## Le tre trappole, tutte incontrate davvero

**1. Errore 403 con `error code: 1010`.**
Non è la chiave sbagliata: è Cloudflare, davanti a Groq, che rifiuta lo `User-Agent` predefinito di `urllib`.
Serve un'intestazione qualsiasi non predefinita. Con `curl` il problema non si presenta.

```python
headers={"User-Agent": "nome-progetto/1.0", ...}
```

**2. Errore 413, ottomila token al minuto.**
Il piano gratuito concede **8000 token al minuto** (prompt e risposta insieme) e 1000 richieste al giorno, uguali per tutti i modelli — si leggono negli header `x-ratelimit-*` di ogni risposta.
Non è il limite del contesto del modello: è quanto puoi spendere in sessanta secondi.
Un documento di media lunghezza incollato nel prompt lo satura da solo, quindi o si tronca il contesto dichiarandolo, o si aspetta il minuto.

**3. L'apostrofo italiano dentro `python3 -c '...'`.**
Un commento che contiene `meta'` o `puo'` chiude la stringa della shell e rompe lo script in un punto lontano.
Il codice Python va in un file suo — vedi `scripts/chiedi_groq.py`.

## Dietro un altro assistente

Qualunque client compatibile con OpenAI: si impostano l'indirizzo e la chiave, e il modello si sceglie per nome.

```bash
export OPENAI_BASE_URL="https://api.groq.com/openai/v1"
export OPENAI_API_KEY="$GROQ_API_KEY"
```

- **Aider, Continue, Cline, Zed, LibreChat, Open WebUI** — hanno tutti un campo per l'indirizzo del fornitore e uno per la chiave: bastano quelli.
- **Aider** da riga di comando: `aider --openai-api-base https://api.groq.com/openai/v1 --openai-api-key "$GROQ_API_KEY" --model openai/gpt-oss-120b`
- **Claude Code** no: parla con l'interfaccia di Anthropic, non con quella di OpenAI. Ci vorrebbe un adattatore in mezzo, e non ne vale la pena.

**Il limite vero non è tecnico ma di capienza**: ottomila token al minuto sono pochi per un assistente di codice, che a ogni domanda manda file interi.
Va bene per domande singole e seconde opinioni; per lavorare su un repo si esaurisce in due scambi.

## Guardare le immagini

`qwen/qwen3.6-27b` accetta immagini come data URI in base64, nel formato di OpenAI:

```python
{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}
```

**Un fotogramma da 428 KB costa 795 token**, cioè circa **dieci immagini al minuto** entro il limite gratuito.
Abbastanza per mettere a punto una domanda, non per passare un archivio.

## Quanto fidarsi

Su una prova di geometria, `gpt-oss-120b` ha impostato le formule e fatto un esempio numerico coerente; `qwen3.6-27b` ha centrato i numeri chiave ma ha prodotto due affermazioni **inventate** («sfocatura crittografica», un angolo impossibile).
Regola pratica: `gpt-oss-120b` come predefinito, qwen quando servono gli occhi, e le sue affermazioni di fatto vanno sempre ricontrollate.
