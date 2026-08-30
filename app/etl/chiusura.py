"""Quando uno scontrino e' FINITO, e quando vale la pena riprovarci.

Un solo posto per questa definizione: la usano il vaglio (che archivia), la
pagina di ingestione (che decide se rielaborare) e l'ispezione delle cartelle
(che decide se una foto gia' vista meriti un secondo giro). Duplicarla
significherebbe che un domani i tre divergono in silenzio.

## Il criterio

CHIUSO = la somma delle righe quadra col totale stampato (entro 2 centesimi)
         E ogni riga ha un nome.

Non "tutti i prodotti che stanno sulla carta": quello non e' verificabile senza
rileggere lo scontrino a mano. Se i conti tornano, cio' che si ha e' coerente e
si puo' mettere via.
"""
from __future__ import annotations

# Due centesimi: assorbe l'arrotondamento, non un prodotto mancante.
TOLLERANZA = 0.02


def somma_righe(dati) -> float:
    return round(sum(float(i.get("price") or 0) for i in (dati.get("items") or [])), 2)


def esamina(dati):
    """(stato, motivo), dove stato e' "chiuso" o "da_ripassare"."""
    totale = dati.get("total")
    items = dati.get("items") or []

    if not items:
        return "da_ripassare", "nessun_prodotto"
    if totale is None:
        return "da_ripassare", "totale_illeggibile"

    scarto = somma_righe(dati) - totale
    if abs(scarto) > TOLLERANZA:
        # Il verso dello scarto dice cose diverse: mancano righe, oppure ne sono
        # entrate di troppo (uno sconto sommato invece che sottratto, il totale
        # di un altro scontrino finito nello stesso ritaglio).
        return "da_ripassare", ("somma_in_difetto" if scarto < 0
                                else "somma_in_eccesso")

    if any(not (i.get("name") or "").strip() for i in items):
        # I conti tornano ma non so COME si chiama tutto: il totale e' usabile,
        # il dettaglio per categoria no.
        return "da_ripassare", "nomi_mancanti"

    return "chiuso", "quadra e ha tutti i nomi"


def e_chiuso(dati) -> bool:
    return esamina(dati)[0] == "chiuso"


def punteggio(dati) -> tuple:
    """Quanto e' buona questa estrazione. Ordinabile: piu' alto e' meglio.

    Serve a decidere se una RIELABORAZIONE vada tenuta o buttata. L'ordine dei
    criteri non e' arbitrario:

    1. chiuso batte non chiuso, sempre;
    2. a parita', vince chi ha piu' righe CON NOME — un nome in piu' e' spesa
       che diventa classificabile;
    3. poi chi ha lo scarto minore dal totale stampato;
    4. infine chi ha piu' righe.

    Il numero di righe viene per ultimo di proposito: un'estrazione che ne
    produce tante ma senza nome non e' migliore di una piu' scarna e pulita.
    """
    stato, _ = esamina(dati)
    items = dati.get("items") or []
    con_nome = sum(1 for i in items if (i.get("name") or "").strip())
    totale = dati.get("total")
    scarto = abs(somma_righe(dati) - totale) if totale is not None else 9999.0
    return (1 if stato == "chiuso" else 0, con_nome, -scarto, len(items))


def meglio(nuovo, vecchio) -> bool:
    """Il nuovo risultato va tenuto al posto del vecchio?

    A parita' esatta si tiene il VECCHIO: rielaborare non deve cambiare i dati
    quando non li migliora, altrimenti ogni passata sporca la storia senza
    aggiungere niente.
    """
    if vecchio is None:
        return True
    return punteggio(nuovo) > punteggio(vecchio)
