"""
Normalizzazione e risoluzione dei nomi dei negozi (Commercianti/Merchants).

Consente di mappare le varianti dell'OCR e i nomi difformi dello stesso negozio
verso un nome canonico (es. MERCADUNA -> Mercadona, RUME SUPERMETCATS -> Consum).

Misurato su 392 scontrini: 4 catene principali (Consum, Mercadona, Cal Fruitos, Dia)
rappresentano il 49,3% del totale corpus.
"""
import re
from typing import Optional, Tuple

# Mappatura esplicita dei pattern di testo/alias verso la catena canonica.
REGOLENIZIO = [
    (re.compile(r"\b(MERCADONA|MERCADUNA|MERCADO)\b", re.I), "Mercadona"),
    (re.compile(r"\b(CONSUM|CHARTER|JUNTOS ES COOPERATIVA|RUME SUPERM?ETCATS)\b", re.I), "Consum"),
    (re.compile(r"\b(CAL\s*FRUIT|FRUITOS|FRUITÓS|^\s*CAL\s*$)\b", re.I), "Cal Fruitos"),
    (re.compile(r"\b(GRUPO?\s*DIA|GRUPU?\s*DIA)\b", re.I), "Dia"),
    (re.compile(r"\b(IKEA)\b", re.I), "IKEA"),
    (re.compile(r"\b(DECATHLON)\b", re.I), "Decathlon"),
    (re.compile(r"\b(ALCAMPO)\b", re.I), "Alcampo"),
    (re.compile(r"\b(KIABI)\b", re.I), "Kiabi"),
    (re.compile(r"\b(LIDL)\b", re.I), "Lidl"),
    (re.compile(r"\b(BONPREU|BON\s*PREU|ESCLAT)\b", re.I), "Bonpreu"),
    (re.compile(r"\b(CARREFOUR)\b", re.I), "Carrefour"),
    (re.compile(r"\b(VERITAS|ECOVERITAS)\b", re.I), "Veritas"),
]


def normalizza_nome_negozio(nome_grezzo: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Restituisce una tupla `(nome_canonico, nome_originale)`.

    Se il nome grezzo corrisponde a una catena notata (anche storpiata dall'OCR),
    restituisce il nome canonico e conserva il nome grezzo come alias originario.
    Se non e' nota, restituisce il nome pulito.
    """
    if not nome_grezzo or not nome_grezzo.strip():
        return ("Sconosciuto", None)

    grezzo = nome_grezzo.strip()

    for pattern, canonico in REGOLENIZIO:
        if pattern.search(grezzo):
            return (canonico, grezzo)

    # Se non c'e' match su regole note, restituiamo il nome formattato in Title Case se tutto maiuscolo
    nome_pulito = grezzo.title() if grezzo.isupper() else grezzo
    return (nome_pulito, grezzo if nome_pulito != grezzo else None)
