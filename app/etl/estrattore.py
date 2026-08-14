"""
Estrae i dati di uno scontrino interrogando un modello linguistico locale.

Fase 3 di docs/40_dal_testo_ai_dati.md. Riceve il testo OCR gia' ricomposto in
righe e ridotto, e restituisce negozio, data, totale e prodotti.

DOMANDE BREVI, NON UNA SOLA GRANDE. Misurato su tre scontrini: due chiamate
brevi costano 208 s contro 267 s di una richiesta unica, il 22% in meno.
Controintuitivo, perche' ogni chiamata ripaga la lettura del prompt, che su CPU
vale il 57% del tempo; ma la richiesta unica genera molti piu' token e a volte
diverge (153 s su un caso contro i 50 tipici).

C'e' anche una ragione di qualita': chiedendo un JSON completo il modello da 3B
azzeccava il totale su 1 scontrino su 4, mentre la domanda isolata sul totale
risponde correttamente anche dove il parser geometrico sbagliava.

IL TOTALE SI CHIEDE PRIMA. E' il campo che serve alla verifica, ed e' quello che
decide se lo scontrino e' utilizzabile: se non torna, non vale la pena spendere
la seconda chiamata per i prodotti.
"""
import json
import logging
import re

import requests

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELLO_PREDEFINITO = "qwen2.5:3b-instruct"

# Un importo, eventualmente negativo (i resi esistono).
IMPORTO = re.compile(r"-?\d{1,4}[.,]\d{2}")

# Data in una delle forme che compaiono sugli scontrini spagnoli.
DATA = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")


# Righe che il modello ricopia ma che non sono prodotti. Il filtro sta qui, nel
# codice, perche' e' deterministico: chiedere al modello di saltarle non ha
# funzionato, le copia comunque.
NON_PRODOTTO = re.compile(
    r"\b(total|subtotal|suma|iva|base|quota|desglossament|desglose|"
    r"efectiu|efectivo|entregado|entregat|canvi|cambio|devoluci|targetes?|"
    r"tarjeta|import|abonar|articles|articulos|descompte|descuento|"
    r"ticket|caixer|cajero|atendido|ates per|gracies|gracias|"
    r"descripcio|descripcion|unit|pvp)\b", re.IGNORECASE)

# Righe di dettaglio che accompagnano un prodotto senza esserlo: il peso e il
# prezzo al chilo compaiono su una riga propria, e sommarli raddoppierebbe il
# contributo di quel prodotto.
DETTAGLIO_PESO = re.compile(
    r"(kg\s*(net|neto)?\s*(x|×)?\s*/?\s*kg|€\s*/\s*kg|"
    r"\bkg\b.*\bkg\b|^\s*\d+[.,]\d{3}\s)", re.IGNORECASE)


def _numero(testo):
    """Il primo importo in una risposta del modello, o None."""
    trovati = IMPORTO.findall(testo or "")
    if not trovati:
        return None
    return float(trovati[0].replace(",", "."))


def _e_riga_prodotto(riga):
    """Una riga ricopiata dal modello descrive davvero un acquisto?"""
    if len(riga) < 6 or not IMPORTO.search(riga):
        return False
    if NON_PRODOTTO.search(riga) or DETTAGLIO_PESO.search(riga):
        return False
    # Deve contenere un nome, non solo cifre e percentuali.
    return bool(re.search(r"[A-Za-zÀ-ÿ]{3}", riga))


class EstrattoreScontrino:
    """Interroga il modello una domanda per volta."""

    def __init__(self, modello=MODELLO_PREDEFINITO, url=OLLAMA_URL, timeout=300):
        self.modello = modello
        self.url = url
        self.timeout = timeout

    def _chiedi(self, prompt, max_token):
        """Una domanda al modello. Restituisce il testo della risposta."""
        try:
            risposta = requests.post(
                self.url,
                json={"model": self.modello, "prompt": prompt, "stream": False,
                      "options": {"num_predict": max_token, "temperature": 0}},
                timeout=self.timeout)
            return risposta.json().get("response", "")
        except Exception as e:
            logger.warning("Modello non raggiungibile: %s", e)
            return ""

    def totale(self, testo, righe_ocr=None):
        """
        Il totale finale pagato.

        Se sono disponibili i frammenti OCR con le coordinate, si usa la lettura
        geometrica: e' piu' affidabile del modello su questo campo, perche' sa
        DOVE guardare invece di indovinare. Il modello da 3B cade su un tranello
        ricorrente — l'ultima riga della tabella IVA, che l'OCR legge come
        "OTAL 17 47" e che somiglia a un totale pur essendo una quota d'imposta.
        Su uno scontrino Mercadona restituiva 17,47 invece di 18,97, sbagliando
        proprio dove i prodotti erano stati estratti alla perfezione.

        Il modello resta come ripiego quando le coordinate non ci sono.
        """
        if righe_ocr:
            from app.etl.totale import trova_totale
            valore = trova_totale(righe_ocr)
            if valore is not None:
                return valore

        prompt = (
            "Questo e' uno scontrino di un negozio spagnolo o catalano.\n"
            "Qual e' il TOTALE FINALE PAGATO?\n"
            "Non e' il contante consegnato (Efectiu, Entregado) ne' il resto "
            "(Canvi, Cambio) ne' una quota IVA.\n"
            "Rispondi SOLO con il numero, senza simboli.\n\n"
            f"{testo}\n\nTotale:")
        return _numero(self._chiedi(prompt, 16))

    def negozio(self, testo):
        """Il nome del negozio, che sta quasi sempre nelle prime righe."""
        testa = "\n".join(testo.split("\n")[:6])
        prompt = (
            "Come si chiama il negozio di questo scontrino?\n"
            "Rispondi SOLO col nome, senza indirizzo ne' partita IVA.\n\n"
            f"{testa}\n\nNegozio:")
        nome = self._chiedi(prompt, 16).strip().strip('".')
        return nome.split("\n")[0][:60] or None

    def data(self, testo):
        """
        La data dell'acquisto, in formato ISO.

        Si cerca prima con un'espressione regolare: una data e' un motivo
        regolare, e chiederlo al modello costerebbe una domanda intera per un
        risultato che il testo contiene gia' in chiaro.
        """
        for giorno, mese, anno in DATA.findall(testo):
            g, m = int(giorno), int(mese)
            a = int(anno) + (2000 if int(anno) < 100 else 0)
            if 1 <= g <= 31 and 1 <= m <= 12 and 2000 <= a <= 2100:
                return f"{a:04d}-{m:02d}-{g:02d}"
        return None

    def prodotti(self, testo):
        """
        I prodotti acquistati, come lista di {name, price}.

        SI CHIEDE DI COPIARE, NON DI RIFORMATTARE. Chiedendo un formato
        "nome|prezzo" il modello da 3B si fermava a 5 prodotti su 13, aggiungeva
        un preambolo di cortesia e trasformava le quantita' in espressioni
        ("3.95 × 2 = 7.90"). Chiedendo invece di ricopiare le righe cosi' come
        sono, le riporta tutte e undici, e la loro somma da' esattamente il
        totale stampato.

        Copiare e' un compito che un modello piccolo sa fare; riformattare no.
        Il prezzo di questa scelta e' che copia anche totali e IVA nonostante
        l'istruzione di saltarli: a scartarli pensa `_e_riga_prodotto`, che e'
        codice deterministico e non sbaglia.
        """
        prompt = (
            "Copia le righe di questo scontrino che descrivono un PRODOTTO "
            "acquistato.\n"
            "Copiale ESATTAMENTE come sono, una per riga.\n"
            "Non riassumere, non calcolare, non aggiungere commenti.\n\n"
            f"{testo}\n\nRighe prodotto:")
        risposta = self._chiedi(prompt, 600)

        prodotti = []
        for riga in (risposta or "").split("\n"):
            riga = riga.strip()
            if not _e_riga_prodotto(riga):
                continue
            # L'ULTIMO importo della riga, non il primo: quando c'e' una
            # quantita' la riga porta prima il prezzo unitario e poi il totale
            # di riga ("2 AMANIDA 0,86 1,72"), ed e' il secondo che conta.
            importi = IMPORTO.findall(riga)
            prezzo = float(importi[-1].replace(",", "."))
            nome = IMPORTO.sub("", riga).strip(" |×x*-–=.,").strip()
            nome = nome.lstrip("0123456789 ").strip()
            if nome and len(nome) >= 3:
                prodotti.append({"name": nome[:80], "price": prezzo})
        return prodotti

    def estrai(self, testo, righe_ocr=None, con_prodotti=True):
        """
        Tutti i campi di uno scontrino.

        `righe_ocr` sono i frammenti con le coordinate, se disponibili: servono
        a leggere il totale geometricamente invece di chiederlo al modello.

        `con_prodotti=False` ferma dopo il totale: utile per una prima passata
        che stabilisce quali scontrini valga la pena approfondire.
        """
        if not testo or not testo.strip():
            return {"shop_name": None, "date": None, "total": None, "items": []}

        return {
            "shop_name": self.negozio(testo),
            "date": self.data(testo),
            "total": self.totale(testo, righe_ocr),
            "items": self.prodotti(testo) if con_prodotti else [],
        }
