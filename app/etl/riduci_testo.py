"""
Riduce il testo OCR a cio' che serve all'LLM per estrarre prodotti e totale.

Perche' e' la leva giusta, misurato: su CPU senza GPU il costo dominante non e'
generare la risposta ma LEGGERE il prompt. Su uno scontrino reale,
qwen2.5:3b-instruct impiega 40.7s per i 400 token di input contro 30.7s per 200
token di output — il 57% del tempo prima ancora di scrivere un carattere.

Ridurre l'input e' quindi piu' efficace che ridurre l'output. Su una prova
diretta: 50 righe -> 14 righe, e il tempo per scontrino da 55s a 33s.

Cosa si butta, e non e' poco. Gli scontrini reali contengono in gran parte testo
che non riguarda la spesa:

  - regolamenti e avvisi legali (uno scontrino di camping aveva 20 righe di
    "REGLAMENTO DE RÉGIMEN INTERNO", piu' della meta' del documento)
  - dati di pagamento (numeri carta, autorizzazioni, codici terminale)
  - intestazioni con partita IVA, telefono, indirizzo
  - ringraziamenti e messaggi promozionali

Il criterio e' conservativo: nel dubbio la riga si tiene. Buttare una riga di
prodotto costa un dato perso, tenerne una inutile costa qualche decimo di
secondo.
"""
import re

# Una riga che contiene un importo va sempre tenuta: e' un prodotto, uno sconto,
# un subtotale o il totale, e all'LLM servono tutti per far quadrare i conti.
IMPORTO = re.compile(r"\d+[.,]\d{2}")

# Righe di prosa: articoli di regolamento, avvisi, ringraziamenti. Riconosciute
# dalla lunghezza e dalla presenza di parole comuni del discorso, che negli
# elenchi di prodotti non compaiono.
PROSA = re.compile(
    r"\b(que|para|por|con|los|las|des|del|una|uno|sera|sean|puedan|cualquier|"
    r"prohibi|obligad|recomienda|responsab|derecho|articulo|art|reglamento|"
    r"condicion|gracias|gracies|visita|siguenos|gastos|gener|ley|llei|rd-ley)\b",
    re.IGNORECASE)

# Dati di pagamento e identificativi: nessun valore per l'estrazione.
TECNICA = re.compile(
    r"\b(aut|autoriz|aid|arc|tar|tarj|targeta|visa|mastercard|contactless|"
    r"terminal|ter|com|codaut|numop|cuenta|iban|nif|cif|n\.i\.f|telefon|"
    r"tlf|tel|www|http|@|op:|ref:|lbl|a1d|caja|cajero|dependent)\b",
    re.IGNORECASE)

# Intestazioni: indirizzo, citta', tipo di documento. Compaiono in cima a ogni
# scontrino e non dicono nulla su cosa sia stato comprato. Il nome del negozio
# NON e' qui: serve, e viene riconosciuto perche' e' la prima riga del testo.
INTESTAZIONE = re.compile(
    r"\b(barcelona|badalona|sabadell|madrid|espana|españa|"
    r"c/\s*\w|carrer|calle|avinguda|avenida|av\.|plaza|pla[cç]a|"
    r"factura\s+simplificada|ticket\s+simplificat|"
    r"codigo\s+postal|cp\s*\d{5}|\d{5}\s+[A-Z])\b", re.IGNORECASE)

# Sotto questa lunghezza una riga senza importo non porta informazione utile
# (frammenti come "3", "€", "kg" isolati).
MIN_CARATTERI = 3

# Oltre questa lunghezza, una riga senza importo e' quasi certamente prosa.
MAX_CARATTERI_SENZA_IMPORTO = 45


def riga_utile(testo):
    """Serve questa riga a capire cosa e' stato comprato e quanto e' costato?"""
    t = testo.strip()
    if len(t) < MIN_CARATTERI:
        return False

    # Un importo e' sempre rilevante, anche dentro una riga tecnica: potrebbe
    # essere il totale pagato con la carta.
    if IMPORTO.search(t):
        return not TECNICA.search(t)

    # Senza importo, la riga vale solo se puo' essere un nome di prodotto.
    if len(t) > MAX_CARATTERI_SENZA_IMPORTO:
        return False
    if PROSA.search(t) or TECNICA.search(t) or INTESTAZIONE.search(t):
        return False

    # Etichetta senza valore accanto ("Numero :", "Fecha :"): il campo che
    # annunciava e' finito in un altro frammento, quindi da sola non serve.
    if t.rstrip().endswith((":", ".-", "-")):
        return False

    # Deve contenere lettere: i codici numerici puri non sono nomi di prodotto.
    return bool(re.search(r"[A-Za-zÀ-ÿ]{3}", t))


def riduci(righe_ocr):
    """Il testo da passare all'LLM, una riga per frammento utile."""
    return "\n".join(r["testo"].strip() for r in righe_ocr
                     if riga_utile(r["testo"]))
