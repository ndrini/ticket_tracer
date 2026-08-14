"""
Controlli di verosimiglianza sui prezzi estratti.

Idea dell'utente: uno yogurt non puo' costare 15 euro ne' 0,05. Un prezzo fuori
scala e' quasi sempre una cifra letta male dall'OCR — una virgola persa
(1,50 -> 150), uno zero di troppo, due importi saldati insieme.

Serve perche' la verifica sul totale, da sola, non basta: dice SE lo scontrino
quadra, non QUALE riga e' sbagliata. Questi controlli indicano dove guardare.

Le soglie vengono da 615 prezzi misurati su 84 scontrini che quadrano al
centesimo, quindi da righe che sono provatamente prodotti:

    mediana        2,00 EUR
    meta' dei casi 1,42 .. 2,95
    95%            sotto 6,48
    oltre 30 EUR   0,7% (IKEA, Decathlon, campeggio)

I supermercati alimentari sono ancora piu' compatti — Mercadona non supera 5,48
euro, Consum 5,82 — ma le soglie qui restano larghe di proposito: segnalare un
prezzo giusto come sospetto costa una verifica inutile, mentre lasciar passare
un errore lo fa entrare nei report.

I valori NEGATIVI sono leciti e non vengono segnalati: sono resi e sconti
(il piu' grande misurato e' -29,88, un reso IKEA).
"""

# Sotto questa cifra un prezzo di prodotto non e' credibile: nemmeno le buste
# della spesa costano meno. Misurato: solo l'1,5% dei prezzi veri sta sotto.
PREZZO_MINIMO = 0.10

# Sopra questa cifra il prezzo e' possibile ma raro (0,7% dei casi), e in un
# alimentare praticamente assente. Vale una verifica.
PREZZO_SOSPETTO = 30.00

# Nessun singolo articolo di questi scontrini supera questa cifra: oltre, si
# tratta quasi certamente di un totale scambiato per prodotto.
PREZZO_IMPOSSIBILE = 200.00


def controlla_prezzo(prezzo):
    """
    Giudica un singolo prezzo. Restituisce None se e' plausibile, altrimenti il
    motivo del sospetto.
    """
    if prezzo is None:
        return "prezzo mancante"
    if prezzo < 0:
        return None  # reso o sconto: legittimo
    if prezzo == 0:
        return "prezzo nullo"
    if prezzo < PREZZO_MINIMO:
        return f"prezzo troppo basso ({prezzo:.2f}), forse una virgola di troppo"
    if prezzo > PREZZO_IMPOSSIBILE:
        return f"prezzo fuori scala ({prezzo:.2f}), forse un totale letto come prodotto"
    if prezzo > PREZZO_SOSPETTO:
        return f"prezzo insolito ({prezzo:.2f}) per un articolo di spesa"
    return None


def controlla_scontrino(prodotti, totale=None):
    """
    Controlla i prezzi di uno scontrino intero.

    `prodotti` e' una lista di dizionari con almeno `price`, e facoltativamente
    `name` (usato solo per rendere leggibile la segnalazione).

    Restituisce la lista dei problemi trovati, vuota se e' tutto plausibile.
    """
    problemi = []

    for i, prodotto in enumerate(prodotti or []):
        prezzo = prodotto.get("price")
        motivo = controlla_prezzo(prezzo)
        if motivo:
            problemi.append({
                "indice": i,
                "nome": prodotto.get("name", ""),
                "prezzo": prezzo,
                "motivo": motivo,
            })

    # Un prodotto non puo' costare piu' dell'intero scontrino: se accade, o il
    # prezzo o il totale e' stato letto male, e in entrambi i casi va guardato.
    if totale is not None and totale > 0:
        for i, prodotto in enumerate(prodotti or []):
            prezzo = prodotto.get("price")
            if prezzo is not None and prezzo > totale + 0.01:
                problemi.append({
                    "indice": i,
                    "nome": prodotto.get("name", ""),
                    "prezzo": prezzo,
                    "motivo": f"prezzo maggiore del totale dello scontrino ({totale:.2f})",
                })

    return problemi
