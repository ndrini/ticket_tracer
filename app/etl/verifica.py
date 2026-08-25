"""
Fase B — verifica di uno scontrino confrontando la somma delle righe col totale.

RUOLO DI QUESTO MODULO. La funzione `verifica` e' il giudice della pipeline: dati
gli importi delle righe e il totale, dice se l'estrazione quadra. E' pensata per
giudicare l'output dell'LLM, non per sostituirlo.

`somma_righe` invece ricava gli importi dalla sola geometria, ed e' un
ESTRATTORE DI RIPIEGO. Misurato su 314 scontrini reali: quadra sul 27%
complessivo, che sale al 42% sugli scontrini senza sconti e scende al 12% su
quelli con sconti. Dei 110 falliti senza sconto, 95 sbagliano di oltre 2 euro,
cioe' per errori strutturali e non per una cifra letta male: sono blocchi interi
raccolti per errore, che nessun aggiustamento geometrico locale sistema.

Il limite e' di principio. Le regole geometriche non sanno che uno sconto va
sottratto, che un subtotale non e' un prodotto, che una promozione 3x2 modifica
il conto: sono fatti semantici. L'LLM del progetto li capisce, e questo modulo
esiste per controllarlo con l'unico dato indipendente disponibile — il totale
che lo scontrino stesso dichiara.

Ogni scontrino dichiara il proprio totale. Sommare gli importi delle righe
prodotto e confrontarli con quel numero e' il controllo di qualita' piu' forte
disponibile, e non costa nulla perche' il dato e' gia' sulla carta.

Serve a trasformare una domanda vaga ("l'estrazione funziona bene?") in un
numero: quanti scontrini quadrano al centesimo. Gli scontrini che non quadrano
non vengono buttati, ma marcati, cosi' i report sanno sempre quanta parte del
totale e' affidabile.

Come si trovano le righe prodotto, senza inventare soglie geometriche:

  1. Gli importi (1234,56) vengono raggruppati in COLONNE per coordinata x. Uno
     scontrino ne ha tipicamente due — prezzo unitario e importo di riga — e su
     un caso reale il raggruppamento le separa a x 216..224 e x 296..314. La
     colonna piu' a destra contiene gli importi da sommare.
  2. Il blocco prodotti finisce dove comincia il riepilogo. Le parole che lo
     marcano (suma, total, descompte, iva, entregado...) danno un confine
     oggettivo: sullo stesso scontrino cade a y=758, subito dopo l'ultimo
     prodotto.

Verificato su uno scontrino letto a mano: la somma della colonna destra sopra il
confine da' 37,26, esattamente il subtotale stampato prima dello sconto del 10%.
"""
from app.etl.geometria import (
    INIZIO_RIEPILOGO,
    SOLO_IMPORTO,
    altezza_riga,
    centro_x,
    centro_y,
    colonne,
    confine_riepilogo,
    valore,
)
from app.etl.totale import trova_totale

# Scarto tollerato fra somma e totale: arrotondamenti, sacchetti, bolli.
TOLLERANZA = 0.05

VALIDO = "VALIDO"
SCARTO_ECCESSIVO = "SCARTO_ECCESSIVO"
TOTALE_ASSENTE = "TOTALE_ASSENTE"
RIGHE_ASSENTI = "RIGHE_ASSENTI"


def somma_righe(righe_ocr):
    """Somma degli importi delle righe prodotto, o None se non calcolabile."""
    if not righe_ocr:
        return None

    altezza = altezza_riga(righe_ocr)
    confine = confine_riepilogo(righe_ocr, altezza)

    # Il confine si applica PRIMA di raggruppare, non dopo. La tabella IVA in
    # fondo allo scontrino ha una propria colonna di importi, vicina a quella
    # dei prodotti ma non allineata (misurato: prodotti a x=428, quote IVA a
    # x=388). Raggruppando tutto insieme le due si fondono in una colonna sola,
    # e le quote finiscono nella somma: su uno scontrino Mercadona questo dava
    # 57,28 contro un totale di 27,57.
    importi = [(valore(r["testo"]), centro_x(r["box"]), centro_y(r["box"]))
               for r in righe_ocr if centro_y(r["box"]) < confine]
    importi = [v for v in importi if v[0] is not None]
    if not importi:
        return None

    gruppi = colonne(importi, altezza)
    if not gruppi:
        return None

    # La colonna piu' a destra porta gli importi di riga; quelle a sinistra
    # sono prezzi unitari e quantita', che sommati falserebbero il conto.
    return sum(v for v, _, _ in gruppi[-1])


def verifica(righe_ocr, tolleranza=TOLLERANZA):
    """
    Confronta la somma delle righe col totale dichiarato.

    Restituisce un dizionario con esito, i due valori e il loro scarto. Uno
    scontrino che non quadra resta un dato: viene marcato, non scartato.
    """
    totale = trova_totale(righe_ocr)
    somma = somma_righe(righe_ocr)

    if totale is None:
        esito = TOTALE_ASSENTE
    elif somma is None:
        esito = RIGHE_ASSENTI
    elif abs(somma - totale) <= tolleranza:
        esito = VALIDO
    else:
        esito = SCARTO_ECCESSIVO

    return {
        "esito": esito,
        "totale_dichiarato": totale,
        "somma_righe": round(somma, 2) if somma is not None else None,
        "scarto": round(somma - totale, 2)
        if (somma is not None and totale is not None) else None,
    }
