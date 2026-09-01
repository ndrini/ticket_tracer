"""
Template di layout geometrici dedicati per le catene di supermercato principali.

Misurato su 392 scontrini: 4 catene principali (Consum, Mercadona, Cal Fruitos, Dia)
coprono da sole il 49,3% del corpus. Ognuna ha un layout caratteristico e stabile:

1. Mercadona: Colonna prezzi molto a destra (x_rel >= 0.82), layout pulito a riga singola.
2. Consum / Charter: Prezzo unitario a sinistra (x_rel 0.50-0.70) e totale riga a destra (x_rel >= 0.75).
3. Cal Fruitos: Prodotti a peso con nome sulla riga superiore rispetto agli importi (peso, €/kg, totale).
4. Dia: Intestazione con sconti e promozioni intermedie.

Se il template specifico per catena fallisce o non quadra la somma, si esegue
il fallback automatico sul metodo geometrico generico.
"""
from typing import Dict, Any, Optional
from app.etl.negozio import normalizza_nome_negozio


PROFILI_CATENA: Dict[str, Dict[str, Any]] = {
    "Mercadona": {
        "x_prezzi_min_rel": 0.78,
        "ha_prodotti_a_peso_riga_sopra": False,
        "preferisci_colonna_destra": True,
    },
    "Consum": {
        "x_prezzi_min_rel": 0.70,
        "ha_prodotti_a_peso_riga_sopra": True,
        "preferisci_colonna_destra": True,
    },
    "Cal Fruitos": {
        "x_prezzi_min_rel": 0.65,
        "ha_prodotti_a_peso_riga_sopra": True,
        "preferisci_colonna_destra": True,
    },
    "Dia": {
        "x_prezzi_min_rel": 0.65,
        "ha_prodotti_a_peso_riga_sopra": False,
        "preferisci_colonna_destra": True,
    },
}


def ottieni_profilo_catena(shop_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Restituisce il profilo geometrico dedicato della catena se riconosciuta,
    altrimenti None (fallback generico).
    """
    if not shop_name:
        return None

    canonico, _ = normalizza_nome_negozio(shop_name)
    return PROFILI_CATENA.get(canonico)
