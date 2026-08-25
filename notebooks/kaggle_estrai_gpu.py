"""Estrae i dati degli scontrini su GPU Kaggle, con lo stesso modello di casa.

Gira come kernel batch: legge il testo OCR dal dataset in ingresso, interroga
qwen2.5:3b-instruct e scrive `estratti_gpu.json` in /kaggle/working/.

## Perche' esiste

Su questa macchina non c'e' GPU e il collo di bottiglia e' il PREFILL: leggere
il prompt costa ~29 s per scontrino a ~22 token/s, cioe' il 72-95% del tempo.
Su una T4 lo stesso prefill sta sotto il secondo.

## Il codice dell'estrazione NON si riscrive

I moduli `app/etl/*` viaggiano dentro il dataset insieme al testo OCR. Riscrivere
qui il parsing del totale, il filtro della coda o le regex delle date
significherebbe avere DUE implementazioni che divergono in silenzio, e i risultati
di Kaggle non sarebbero piu' confrontabili con quelli locali.

## vLLM, non Ollama

Ollama e' pensato per servire un modello, non per macinare un lotto. Su GPU
conviene vLLM, che raggruppa le richieste automaticamente: gli scontrini si
inviano tutti insieme e il motore li accorpa. Se vLLM non e' disponibile si
ripiega su transformers, piu' lento ma sempre molto piu' veloce della CPU.

## L'ordine del prompt resta quello vecchio, di proposito

In locale conviene [SCONTRINO][DOMANDA] per riusare la KV cache (28,0 s -> 0,8 s,
misurato). Qui NON si cambia: il confronto con i risultati locali deve isolare
l'effetto della GPU. L'inversione e' una modifica separata, con le sue metriche
di guardia.
"""

# %%
import json
import subprocess
import sys
import time
from pathlib import Path

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
MODELLO = "Qwen/Qwen2.5-3B-Instruct"

# Lo smoke test: la guida del progetto gemello dice di non spendere mai piu' di
# un'ora di GPU per esperimento, e di provare su pochi elementi prima del lotto.
# 0 = tutti.
LIMITE = int(__import__("os").environ.get("LIMITE", "3"))  # SMOKE TEST: rimettere "0"


# %%
def installa():
    """Dipendenze. `subprocess`, non `!pip`: questo e' uno script, non un notebook."""
    for pacchetto in ("vllm",):
        try:
            __import__(pacchetto)
        except ImportError:
            print(f"installo {pacchetto}...", flush=True)
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", pacchetto], check=False
            )


def trova_dataset() -> Path:
    """La cartella del dataset in ingresso, senza dipendere dal nome esatto.

    ⚠️ Non basta "la prima cartella che contiene JSON": Kaggle monta i dataset
    sotto un livello intermedio (`/kaggle/input/datasets/<slug>/`), e `rglob`
    faceva passare per buona la cartella intermedia. Il kernel cercava poi
    `app/etl/` al posto sbagliato e si fermava dicendo che il codice mancava,
    quando invece c'era. Misurato al primo smoke test (2026-08-17).

    Si cerca quindi la cartella che contiene DAVVERO i file attesi, scendendo
    di livello se serve.
    """
    def e_il_dataset(percorso: Path) -> bool:
        # Il marcatore e' il codice: senza, il kernel non parte comunque.
        return (percorso / "codice.zip").exists() or (
            percorso / "codice" / "app" / "etl" / "estrattore.py"
        ).exists()

    candidati = [p for p in sorted(INGRESSO.rglob("*")) if p.is_dir()]
    for percorso in [INGRESSO, *candidati]:
        if e_il_dataset(percorso):
            return percorso

    # Nessun marcatore: si ripiega sulla cartella con piu' JSON, che e' il
    # dataset vero e non un livello intermedio (questo ne contiene pochi o zero).
    migliore, quanti = None, 0
    for percorso in candidati:
        n = len(list(percorso.glob("*.json")))
        if n > quanti:
            migliore, quanti = percorso, n
    if migliore is not None:
        return migliore
    raise SystemExit(f"⛔️ nessun dataset con JSON sotto {INGRESSO}")


def carica_moduli(radice: Path):
    """Rende importabile `app.etl.*` dal dataset, invece di duplicarne il codice.

    ⚠️ `--dir-mode zip` comprime le sottocartelle: `codice/` arriva come
    `codice.zip` e va estratto. Kaggle a volte lo scompatta da se', quindi si
    gestiscono entrambi i casi invece di dipendere dal comportamento.
    """
    import zipfile

    archivio = radice / "codice.zip"
    if archivio.exists():
        estratto = USCITA / "codice"
        estratto.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archivio) as zf:
            zf.extractall(estratto)
        # Lo zip puo' contenere `app/...` oppure `codice/app/...`
        for candidato in (estratto, estratto / "codice"):
            if (candidato / "app" / "etl" / "estrattore.py").exists():
                sys.path.insert(0, str(candidato))
                return True

    for candidato in (radice, radice / "codice"):
        if (candidato / "app" / "etl" / "estrattore.py").exists():
            sys.path.insert(0, str(candidato))
            return True
    return False


# %%
def prepara_prompt(righe_ocr) -> tuple[str, str]:
    """(testo ridotto per il modello, testo completo per la data).

    Riusa le stesse funzioni della pipeline locale. La data si cerca sul testo
    COMPLETO perche' sugli scontrini spagnoli e' stampata in coda, sotto il
    totale, e il filtro che toglie la coda la porterebbe via con se'.
    """
    from app.etl.coda import righe_corpo
    from app.etl.riduci_testo import riga_utile
    from app.etl.righe_logiche import testo_ricomposto

    righe = testo_ricomposto(righe_corpo(righe_ocr)).split("\n")
    ridotto = "\n".join(r for r in righe if riga_utile(r))
    completo = testo_ricomposto(righe_ocr)
    return ridotto, completo


def main() -> int:
    dataset = trova_dataset()
    print(f"dataset in ingresso: {dataset}", flush=True)

    if not carica_moduli(dataset):
        # Cosa c'e' davvero sotto /kaggle/input: senza questo, un errore di
        # percorso costa un giro completo per capire dove sia finito il codice.
        print("contenuto di /kaggle/input:", flush=True)
        for percorso in sorted(INGRESSO.rglob("*"))[:40]:
            print(f"  {percorso}", flush=True)
        raise SystemExit(
            "⛔️ `app/etl/` non e' nel dataset. Il kernel NON riscrive l'estrazione: "
            "ricarica il dataset col codice incluso (default di kaggle_carica_dataset.py)."
        )

    file_ocr = sorted(p for p in dataset.rglob("*.json") if p.name != "dataset-metadata.json")
    if LIMITE:
        file_ocr = file_ocr[:LIMITE]
    print(f"{len(file_ocr)} scontrini da elaborare", flush=True)

    installa()
    from vllm import LLM, SamplingParams

    from app.etl.estrattore import (EstrattoreScontrino, prodotti_dalla_risposta,
                                    prompt_prodotti)

    avvio = time.time()
    llm = LLM(model=MODELLO, max_model_len=4096, gpu_memory_utilization=0.90)
    print(f"modello caricato in {time.time() - avvio:.0f}s", flush=True)

    # Un solo estrattore, usato per i suoi PARSER (regex di data, filtri delle
    # righe prodotto): le domande al modello le fa vLLM in blocco.
    estrattore = EstrattoreScontrino()

    testi, completi, sha = [], [], []
    righe_per_sha = {}
    for percorso in file_ocr:
        dati = json.loads(percorso.read_text())
        righe = dati.get("righe_ocr") or []
        if not righe:
            continue
        ridotto, completo = prepara_prompt(righe)
        chiave = dati.get("sha256", percorso.stem)
        testi.append(ridotto)
        completi.append(completo)
        sha.append(chiave)
        righe_per_sha[chiave] = righe

    # Il totale si legge per COORDINATE. Riesce nel 97% dei casi sull'intero
    # dataset, ma NON sempre: dove fallisce, la pipeline locale ripiega sul
    # modello (`EstrattoreScontrino.totale`). Il kernel deve fare lo stesso,
    # altrimenti perde i totali che in locale ci sono — misurato allo smoke
    # test: 3 scontrini su 10 senza totale, e non era un difetto di trasporto
    # ma questo ripiego mancante.
    from app.etl.totale import trova_totale

    totali = [trova_totale(righe_per_sha[s]) for s in sha]
    da_chiedere = [i for i, t in enumerate(totali) if t is None]

    # Tutte le domande in un colpo solo: vLLM le raggruppa da se'.
    p_negozio = [
        "Come si chiama il negozio di questo scontrino?\n"
        "Rispondi SOLO col nome, senza indirizzo ne' partita IVA.\n\n"
        + "\n".join(t.split("\n")[:6])
        + "\n\nNegozio:"
        for t in testi
    ]
    # La domanda arriva da `app.etl.estrattore`, non riscritta qui: una seconda
    # formulazione darebbe risposte diverse e i due percorsi non sarebbero piu'
    # confrontabili. (Era gia' duplicata, con "PRODOTTO acquistato" su una riga
    # sola invece che spezzato: differenza minima, ma proprio per questo il tipo
    # di divergenza che non si nota.)
    p_prodotti = [prompt_prodotti(t) for t in testi]

    t0 = time.time()
    r_negozio = llm.generate(p_negozio, SamplingParams(temperature=0, max_tokens=16))
    r_prodotti = llm.generate(p_prodotti, SamplingParams(temperature=0, max_tokens=600))
    durata = time.time() - t0

    # vLLM restituisce le risposte nell'ordine dei prompt, ma se cosi' non fosse
    # i campi finirebbero sullo scontrino sbagliato — un errore silenzioso che
    # produce dati plausibili e falsi. Meglio fermarsi.
    if not (len(r_negozio) == len(r_prodotti) == len(sha)):
        raise SystemExit(
            f"⛔️ risposte disallineate: {len(r_negozio)} negozi, "
            f"{len(r_prodotti)} prodotti, {len(sha)} scontrini attesi."
        )

    # Il ripiego: si chiede il totale SOLO dove le coordinate non l'hanno
    # trovato. Stesso prompt della pipeline locale, per non introdurre una
    # seconda formulazione che darebbe risposte diverse.
    if da_chiedere:
        from app.etl.estrattore import _numero

        p_totale = [
            "Questo e' uno scontrino di un negozio spagnolo o catalano.\n"
            "Qual e' il TOTALE FINALE PAGATO?\n"
            "Non e' il contante consegnato (Efectiu, Entregado) ne' il resto "
            "(Canvi, Cambio) ne' una quota IVA.\n"
            "Rispondi SOLO con il numero, senza simboli.\n\n"
            f"{testi[i]}\n\nTotale:"
            for i in da_chiedere
        ]
        r_totale = llm.generate(p_totale, SamplingParams(temperature=0, max_tokens=16))
        for posizione, risposta in zip(da_chiedere, r_totale):
            totali[posizione] = _numero(risposta.outputs[0].text)
        print(f"totale chiesto al modello per {len(da_chiedere)} scontrini", flush=True)

    # ⚠️ Si itera sugli SHA, non su `file_ocr`: gli scontrini senza `righe_ocr`
    # sono stati saltati nel ciclo di preparazione, quindi gli indici delle
    # risposte NON corrispondono piu' a quelli dei file. `righe_per_sha`
    # conserva le righe gia' lette invece di rileggere il file sbagliato.
    risultati = []
    for i, chiave in enumerate(sha):
        # Gia' calcolato sopra: coordinate, col ripiego al modello dove serve.
        totale = totali[i]
        nome = r_negozio[i].outputs[0].text.strip().strip('".').split("\n")[0][:60]
        # ⛔️ NON `estrattore.prodotti()`: quel metodo CHIEDE la risposta a
        # Ollama su localhost:11434, che su Kaggle non esiste. Ignorava il testo
        # gia' generato da vLLM, falliva la connessione e restituiva zero
        # prodotti su OGNI scontrino — misurato allo smoke test, 0 su 24.
        # `prodotti_dalla_risposta` e' lo stesso filtro senza la chiamata.
        prodotti = prodotti_dalla_risposta(r_prodotti[i].outputs[0].text, totale)
        risultati.append(
            {
                "sha256": chiave,
                "shop_name": nome or None,
                "date": estrattore.data(completi[i]),
                "total": totale,
                "items": prodotti,
            }
        )

    (USCITA / "estratti_gpu.json").write_text(
        json.dumps(risultati, ensure_ascii=False, indent=1)
    )
    # Le risposte grezze: rileggerle non deve richiedere una seconda sessione GPU.
    (USCITA / "risposte_grezze.json").write_text(
        json.dumps(
            [
                {"sha256": s, "negozio": rn.outputs[0].text, "prodotti": rp.outputs[0].text}
                for s, rn, rp in zip(sha, r_negozio, r_prodotti)
            ],
            ensure_ascii=False,
        )
    )

    n = len(risultati)
    print(f"\n{n} scontrini in {durata:.0f}s = {durata / max(n, 1):.2f} s/scontrino")
    print("  in locale, senza GPU: ~40-75 s/scontrino")
    quadrati = sum(
        1
        for r in risultati
        if r["total"] and abs(sum(i["price"] for i in r["items"]) - r["total"]) < 0.02
    )
    print(f"  quadrati: {quadrati}/{n}   con totale: {sum(1 for r in risultati if r['total'])}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
