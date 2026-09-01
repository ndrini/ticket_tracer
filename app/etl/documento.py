"""
Classificazione del tipo di documento estratto.

Distingue uno scontrino d'acquisto (con elenco prodotti) da una ricevuta di
pagamento POS/contactless (senza prodotti, recante solo l'operazione bancaria).

Misurato su 392 scontrini estratti: 14 ricevute sono POS puri (BBVA, Sabadell,
Comercia Global Payments, Kiabi Contactless, ecc.), che altrimenti verrebbero
classificate come SOMMA_IN_DIFETTO o TOTALE_ASSENTE inficiando le metriche.
"""
import re

PAROLE_POS = re.compile(
    r"\b(contactless|operacio\s+contactless|operacion\s+contactless|venda|venta|"
    r"copia\s+client|copia\s+cliente|targeta|tarjeta|merchant|terminal|comercio|"
    r"auth\b|aut\b|aid:|firma\s+no\s+necesaria|aprobada)\b", re.IGNORECASE
)

ETICHETTA_PRODOTTI_O_TOTALE = re.compile(
    r"\b(total|subtotal|suma|importe|import)\b", re.IGNORECASE
)


def tipo_documento(righe_ocr):
    """
    Restituisce 'PAGAMENTO_ELETTRONICO' se il documento e' una ricevuta POS pura,
    altrimenti 'SCONTRINO_SPESA'.

    Una ricevuta POS pura ha:
    1. Almeno 2 marcatori tipici di transazione POS/carta
    2. Al massimo 3 importi in tutto il documento
    3. Assenza di etichette tipiche di totale/somma scontrino spesa
    """
    if not righe_ocr:
        return "SCONTRINO_SPESA"

    testo = " ".join(r.get("testo", "") for r in righe_ocr)
    matches = PAROLE_POS.findall(testo)
    if len(matches) < 2:
        return "SCONTRINO_SPESA"

    has_total_label = bool(ETICHETTA_PRODOTTI_O_TOTALE.search(testo))
    if has_total_label:
        return "SCONTRINO_SPESA"

    importi = re.findall(r"\d+[.,]\d{2}", testo)
    if len(importi) <= 3:
        return "PAGAMENTO_ELETTRONICO"

    return "SCONTRINO_SPESA"
