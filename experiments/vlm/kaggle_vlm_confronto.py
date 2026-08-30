# %% [markdown]
# Confronto geometrico vs VLM sui ritagli gia' giudicati a mano.
#
# Vedi docs/122_metrica_confronto_vlm.md. Legge il dataset privato
# `ticket-tracer-ritagli` (28 ritagli col taglio giudicato buono) e scrive
# `vlm_risultati.json` con i prodotti letti da ciascuno.
#
# NON decide chi vince: il confronto col totale stampato si fa a casa, dove
# stanno il database e i giudizi umani. Qui si produce solo la lettura del VLM.

# %%
import json
import os
import subprocess
import sys
import time

# NON si fissa transformers a una versione: MISURATO il 2026-08-30, imporre
# transformers==4.44.2 sull'immagine Kaggle rompe il caricamento del tokenizer
# con "data did not match any variant of untagged enum ModelWrapper", perche'
# il `tokenizers` preinstallato e' piu' recente di quello che quella versione
# si aspetta. L'immagine di Kaggle e' gia' internamente coerente: si usa quella.
subprocess.run([sys.executable, "-m", "pip", "install", "accelerate"], check=False)

import torch
import transformers
from PIL import Image
from transformers import AutoProcessor, LlavaForConditionalGeneration

# Stampate perche' il fallimento precedente era invisibile: pip girava con -q e
# il log non diceva quali versioni fossero davvero in uso.
print("transformers:", transformers.__version__)
print("torch:", torch.__version__)

# Il dataset e' dichiarato in dataset_sources e VERIFICATO presente nel metadata
# lato server, ma il montaggio si e' rivelato intermittente: MISURATO il
# 2026-08-30, al secondo tentativo /kaggle/input/ticket-tracer-ritagli esisteva
# (l'errore era su un singolo file mancante), al terzo l'intera cartella non
# c'era. Si cerca quindi fra tutto cio' che e' montato invece di fidarsi di un
# percorso fisso, e si dice cosa si e' trovato prima di fallire.
RADICE_INPUT = "/kaggle/input"
USCITA = "/kaggle/working/vlm_risultati.json"
MODELLO = "llava-hf/llava-1.5-7b-hf"

# Uno scontrino e' stretto e LUNGO: la mediana qui e' 363x1014, il piu' lungo
# 659x1725. Un limite di 1024 sul lato maggiore lo schiaccerebbe a 391px di
# larghezza, e a quel punto i nomi dei prodotti non sono leggibili nemmeno da un
# umano: si misurerebbe il ridimensionamento, non il modello. Si limita quindi
# la LARGHEZZA, lasciando correre l'altezza.
LARGHEZZA_MAX = 768
ALTEZZA_MAX = 2048

PROMPT = """You are an assistant that extracts structured product data from receipt images.

TASK: Extract ONLY purchased items (products with prices).

RULES:
1. Return ONLY valid JSON, no other text
2. Ignore: headers, totals, VAT, subtotals, discounts, empty lines, merchant info
3. Extract each item with name and price in decimal format (X.XX)
4. If multiple items on same line, extract each separately
5. If quality is poor or no items found, return: []

FORMAT:
[
  {"name": "product name", "price": X.XX},
  {"name": "another product", "price": Y.YY}
]"""


def ridimensiona(img):
    """Keep the text legible: cap width, allow the receipt to stay tall."""
    w, h = img.size
    scala = min(LARGHEZZA_MAX / w, ALTEZZA_MAX / h, 1.0)
    if scala < 1.0:
        img = img.resize((int(w * scala), int(h * scala)), Image.LANCZOS)
    return img


def estrai_json(testo):
    """Pull the JSON array out of the model's answer.

    The model is asked for JSON alone but does not always obey: a prose
    preamble is common. Returning [] on a parse failure would silently count as
    "found nothing", so the raw answer is kept for inspection.
    """
    inizio = testo.find("[")
    fine = testo.rfind("]")
    if inizio == -1 or fine == -1 or fine < inizio:
        return None
    try:
        return json.loads(testo[inizio:fine + 1])
    except json.JSONDecodeError:
        return None


# %%
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NESSUNA")


def trova_ingresso():
    """The mounted folder holding the crops, wherever Kaggle put it.

    Cercata RICORSIVAMENTE: MISURATO il 2026-08-30, il montaggio non usa un
    percorso stabile. Tre esecuzioni, tre forme diverse:
    /kaggle/input/ticket-tracer-ritagli (esisteva), la stessa assente, e infine
    /kaggle/input/datasets/... - cioe' i file annidati sotto un livello in piu'.
    Un percorso fisso, o una ricerca a un solo livello, si rompe a ogni giro.
    """
    if not os.path.isdir(RADICE_INPUT):
        raise SystemExit(f"{RADICE_INPUT} non esiste: nessun dataset montato.")

    migliore, quanti = None, 0
    for cartella, _, file in os.walk(RADICE_INPUT):
        n = sum(1 for f in file if f.endswith(".jpg"))
        if n > quanti:
            migliore, quanti = cartella, n
    if migliore:
        return migliore

    # Nothing found: print the tree, so a rerun is not blind like this one was.
    print("nessun .jpg trovato. Ecco cosa e' montato:")
    for cartella, sotto, file in os.walk(RADICE_INPUT):
        livello = cartella.replace(RADICE_INPUT, "").count(os.sep)
        print("  " * livello, os.path.basename(cartella) or RADICE_INPUT,
              f"[{len(file)} file]", (file[:4] if file else ""))
    raise SystemExit("il dataset e' dichiarato in dataset_sources ma non "
                     "contiene immagini raggiungibili.")


# PRIMA di caricare il modello: scoprire che i dati mancano dopo aver speso
# minuti di GPU sui pesi butta via l'esecuzione, ed e' successo al terzo
# tentativo.
INGRESSO = trova_ingresso()
print("ingresso:", INGRESSO)

processor = AutoProcessor.from_pretrained(MODELLO)
model = LlavaForConditionalGeneration.from_pretrained(
    MODELLO, torch_dtype=torch.float16, device_map="auto", low_cpu_mem_usage=True)
model.eval()

# L'elenco si ricava dai file .jpg presenti, non da indice.json: MISURATO il
# 2026-08-30, Kaggle non serve quel file nel dataset (FileNotFoundError sul
# percorso, e l'API non lo elenca fra i file), probabilmente perche' scarta i
# JSON di controllo insieme a dataset-metadata.json. Il nome del file E' lo
# sha256, quindi l'indice non aggiunge nulla che i nomi non dicano gia'.
#
# Il receipt_id si recupera a casa dallo sha256: e' la chiave di tutta la
# pipeline, e il database ce l'ha.
indice = [{"sha256": f[:-4]}
          for f in sorted(os.listdir(INGRESSO)) if f.endswith(".jpg")]
print(f"{len(indice)} ritagli da leggere")

# %%
risultati = []
inizio_tutto = time.time()

for n, voce in enumerate(indice, 1):
    sha = voce["sha256"]
    percorso = os.path.join(INGRESSO, f"{sha}.jpg")
    esito = {"sha256": sha}

    try:
        img = ridimensiona(Image.open(percorso).convert("RGB"))
        # The chat template is what 1.5 was trained on; the bare prompt used by
        # the earlier benchmark script drifts off format more often.
        testo_prompt = f"USER: <image>\n{PROMPT} ASSISTANT:"
        inputs = processor(images=img, text=testo_prompt, return_tensors="pt").to(
            model.device, torch.float16)

        t0 = time.time()
        with torch.no_grad():
            uscita = model.generate(**inputs, max_new_tokens=512, do_sample=False)
        esito["secondi"] = round(time.time() - t0, 1)

        risposta = processor.decode(uscita[0], skip_special_tokens=True)
        risposta = risposta.split("ASSISTANT:")[-1].strip()
        prodotti = estrai_json(risposta)

        esito["prodotti"] = prodotti
        esito["risposta_grezza"] = risposta
        # Told apart on purpose: a model that answered nothing and a model whose
        # answer could not be parsed are different failures.
        esito["stato"] = "ok" if prodotti is not None else "json_illeggibile"

    except Exception as e:
        esito.update(stato="errore", errore=str(e), prodotti=None)

    risultati.append(esito)
    n_prod = len(esito.get("prodotti") or [])
    print(f"[{n:3}/{len(indice)}] {sha[:10]} {esito['stato']:<16} "
          f"{n_prod:>3} prodotti  {esito.get('secondi', 0)}s")

print(f"\nTotale: {(time.time() - inizio_tutto) / 60:.1f} min")

# %%
with open(USCITA, "w", encoding="utf-8") as f:
    json.dump(risultati, f, ensure_ascii=False, indent=1)

ok = sum(1 for r in risultati if r["stato"] == "ok")
vuoti = sum(1 for r in risultati if (r.get("prodotti") or []) == [])
print(f"scritti {len(risultati)} esiti in {USCITA}")
print(f"  letti bene:        {ok}")
print(f"  json illeggibile:  {sum(1 for r in risultati if r['stato'] == 'json_illeggibile')}")
print(f"  errori:            {sum(1 for r in risultati if r['stato'] == 'errore')}")
print(f"  senza prodotti:    {vuoti}")
