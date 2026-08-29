"""
Fase F.2 — Proponi categorie per i prodotti.

Legge i prodotti, usa keyword matching per suggerire una categoria,
ordina per frequenza nelle receipt_lines.

Categorie: Frutta, Verdure, Latticini, Carne, Pane, Bevande, Igiene, Altro.

Uso:
    uv run python scripts/fase_f_2_proponi_categorie.py
"""
import json
import sqlite3
import sys
from pathlib import Path


# Dizionario di keyword per categoria
CATEGORY_KEYWORDS = {
    "Frutta": [
        "mela", "pera", "arancia", "limone", "banana", "kiwi", "uva", "fragola",
        "melone", "cocomero", "mandarina", "pesca", "albicocca", "ciliegia",
        "dattero", "fico", "frutto", "fruta", "mango", "papaia", "ananas",
    ],
    "Verdure": [
        "verdura", "verdure", "insalata", "lattuga", "rucola", "spinaci",
        "carota", "cavolo", "broccoli", "cavolfiore", "zucchina", "melanzana",
        "peperone", "pomodoro", "cipolla", "aglio", "sedano", "patata", "batata",
        "funghi", "champiñón", "champiñones", "champiñon",
    ],
    "Latticini": [
        "latte", "formaggio", "yogurt", "iogurt", "ricotta", "burro", "crema",
        "parmigiano", "mozzarella", "cheddar", "grana", "camembert", "brie",
        "emmental", "gouda", "provolone", "pecorino", "burrata",
    ],
    "Carne": [
        "carne", "pollo", "manzo", "maiale", "vitello", "agnello", "pesce",
        "prosciutto", "mortadella", "salumi", "salsiccia", "jamón", "jamón",
        "truita", "salmone", "trota", "merluzzo", "tonno", "sardine",
    ],
    "Pane": [
        "pane", "pan", "barra", "baguette", "panettone", "biscotti", "crackers",
        "tostada", "tostadas", "pan de", "pan tostado",
    ],
    "Bevande": [
        "acqua", "succo", "zumo", "caffè", "café", "tè", "te", "birra", "vino",
        "champagne", "prosecco", "liquore", "spirito", "cola", "fanta", "sprite",
        "refresco", "bebida", "latte",
    ],
    "Igiene": [
        "igienico", "detergente", "sapone", "shampoo", "deodorante", "carta",
        "scottex", "fazzoletti", "toallitas", "pannolini", "assorbenti",
        "spazzolino", "dentifricio", "bagnoschiuma", "doccia",
    ],
    "Altro": [],  # catch-all
}


def proponi_categoria(nome):
    """
    Propone una categoria per un nome prodotto.
    Restituisce (categoria, confidence: 'high'/'low').
    """
    if not nome:
        return "Altro", "low"

    nome_lower = nome.lower()

    # Cerca match di keyword
    for categoria, keywords in CATEGORY_KEYWORDS.items():
        if categoria == "Altro":
            continue
        for keyword in keywords:
            if keyword in nome_lower:
                return categoria, "high"

    return "Altro", "low"


def main(argv):
    db = "data/spese.db"

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n📥 Fase F.2 — Proponi categorie\n")

    # Leggi i prodotti con frequenza d'uso
    cursor.execute("""
        SELECT p.id, p.name, COUNT(rl.id) as usage_count
        FROM products p
        LEFT JOIN receipt_lines rl ON rl.product_id = p.id
        GROUP BY p.id
        ORDER BY usage_count DESC
    """)

    prodotti = cursor.fetchall()

    proposte = {}

    for prod in prodotti:
        prod_id = prod["id"]
        nome = prod["name"]
        usage = prod["usage_count"] or 0

        categoria, confidence = proponi_categoria(nome)

        proposte[f"prod_{prod_id}"] = {
            "product_id": prod_id,
            "name": nome,
            "usage_count": usage,
            "category": categoria,
            "confidence": confidence,
            "approved": False
        }

    # Salva il report
    output_path = "data/fase_f_2_categorie_proposte.json"
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_products": len(proposte),
                "phase": "F.2 — Proponi categorie"
            },
            "proposte": proposte
        }, f, indent=2)

    print(f"Report salvato: {output_path}\n")

    # Statistiche
    high_conf = sum(1 for p in proposte.values() if p["confidence"] == "high")
    low_conf = sum(1 for p in proposte.values() if p["confidence"] == "low")

    print(f"Proposte generate: {len(proposte)}")
    print(f"  Alta confidenza (keyword match): {high_conf}")
    print(f"  Bassa confidenza (default 'Altro'): {low_conf}\n")

    # Top 20 per frequenza
    print("Top 20 prodotti (per frequenza d'uso):\n")
    sorted_proposte = sorted(proposte.values(), key=lambda p: p["usage_count"], reverse=True)
    for i, prop in enumerate(sorted_proposte[:20]):
        conf = "✓" if prop["confidence"] == "high" else "?"
        print(f"  {i+1:2d}. [{conf}] {prop['name']:40s} ({prop['usage_count']:3d}x) → {prop['category']}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
