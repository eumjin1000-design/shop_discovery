"""Spark-native Amazon search URL helpers.

Builds URLs in the exact shape the Spark scraper (per the 11/24 user guide)
expects on its "수집 링크 추가" tab:

    https://www.amazon.com/s?keywords=Multivitamins
        &rh=n%3A3774861%2Cp_n_has_afn_offer%3A1%2Cp_85%3A2470955011
        &c=ts&s=review-count-rank

One such URL = one Spark task that paginates through hundreds-to-thousands
of category products. Far more efficient than the per-ASIN brand-title
searches we previously emitted (which yielded only ~5 products per URL).

Public surface
--------------
* :data:`HF_TO_BROWSE_NODE` — HF dataset category → Amazon browse node id.
* :data:`HF_BROAD_KEYWORDS` — broad keyword seeds per HF category.
* :func:`build_search_url` — replaces :py:meth:`modules.sourcing.SourcingRow.search_url`.
"""
from __future__ import annotations

import re
import urllib.parse

# Amazon filter tokens (from the Spark guide reference URL).
PRIME_FILTER = "p_85%3A2470955011"          # Prime Eligible
AFN_FILTER = "p_n_has_afn_offer%3A1"        # Amazon Fulfilled (FBA)
_NODE_NONE = "1000"                          # sentinel for "no real node"

# Stop words for fallback keyword extraction (duplicated from sourcing.py to
# avoid a circular import — small constant, low duplication cost).
_GENERIC_WORDS = {"home", "sport", "best", "new", "top", "kit", "set",
                  "pro", "mini", "portable", "premium", "compact", "plus",
                  "product"}

# HF dataset category → Amazon top-level browse node id (US).
HF_TO_BROWSE_NODE: dict[str, str] = {
    "All_Beauty": "3760911",
    "Arts_Crafts_and_Sewing": "2617941011",
    "Baby_Products": "165796011",
    "Beauty_and_Personal_Care": "3760911",
    "Cell_Phones_and_Accessories": "2335752011",
    "Electronics": "172282",
    "Gift_Cards": "2238192011",
    "Handmade_Products": "11260432011",
    "Health_and_Household": "3760901",
    "Home_and_Kitchen": "1055398",
    "Industrial_and_Scientific": "16310091",
    "Musical_Instruments": "11091801",
    "Office_Products": "1069242",
    "Pet_Supplies": "2619533011",
    "Sports_and_Outdoors": "3375251",
    "Toys_and_Games": "165793011",
}

# Broad keyword seeds per category — list length is proportional to dataset
# depth (big categories get ~20-25 seeds, small ones get 1-5). Each seed
# becomes one Spark URL, so a category with 921K products in the dataset
# (Home_and_Kitchen) gets far more search URLs than Gift_Cards (1K).
HF_BROAD_KEYWORDS: dict[str, list[str]] = {
    # --- LARGE (300K+ products) ---
    "Home_and_Kitchen": [
        "kitchen", "cookware", "bakeware", "small appliances",
        "coffee maker", "blender", "air fryer", "knife set",
        "storage container", "cutting board", "kitchen utensil",
        "kitchen towel", "bedding", "comforter", "pillow",
        "bath towel", "bath mat", "home decor", "wall art",
        "rug", "lighting", "lamp", "curtain", "vacuum",
        "cleaning supplies", "trash can",
    ],
    "Beauty_and_Personal_Care": [
        "skincare", "moisturizer", "serum", "sunscreen",
        "face mask", "cleanser", "toner", "makeup",
        "foundation", "lipstick", "mascara", "eyeliner",
        "blush", "concealer", "hair care", "shampoo",
        "conditioner", "hair dryer", "hair straightener",
        "fragrance", "perfume",
    ],
    "Sports_and_Outdoors": [
        "fitness", "yoga", "yoga mat", "dumbbell",
        "resistance band", "foam roller", "treadmill",
        "exercise bike", "camping tent", "sleeping bag",
        "hiking backpack", "fishing rod", "fishing reel",
        "golf club", "tennis racket", "basketball",
        "soccer ball", "kayak", "bike helmet", "water bottle",
        "running shoes",
    ],
    "Health_and_Household": [
        "vitamins", "multivitamin", "supplements", "protein powder",
        "probiotic", "collagen", "fish oil", "vitamin d",
        "pain relief", "first aid", "bandage", "thermometer",
        "toilet paper", "paper towel", "laundry detergent",
        "dish soap", "disinfectant", "cleaning wipes",
        "toothbrush", "toothpaste", "deodorant", "razor",
    ],
    "Pet_Supplies": [
        "dog supplies", "dog food", "dog treats", "dog toys",
        "dog bed", "dog harness", "dog leash", "dog crate",
        "cat supplies", "cat food", "cat litter", "cat tree",
        "cat toys", "aquarium", "fish tank", "bird supplies",
    ],
    "Office_Products": [
        "office supplies", "desk", "desk organizer", "office chair",
        "stationery", "notebook", "planner", "ballpoint pen",
        "marker", "sticky note", "filing", "printer paper",
        "calculator", "envelope",
    ],
    # --- MEDIUM (100~300K products) ---
    "Industrial_and_Scientific": [
        "lab equipment", "safety glasses", "industrial tools",
        "hardware", "lab supplies", "measuring tools",
        "work gloves", "respirator",
    ],
    "Arts_Crafts_and_Sewing": [
        "art supplies", "acrylic paint", "watercolor", "drawing",
        "sketchbook", "markers", "crafts", "sewing",
        "yarn", "knitting needles", "scrapbook", "beads",
    ],
    "Cell_Phones_and_Accessories": [
        "phone case", "iphone case", "samsung case",
        "phone charger", "wireless charger", "phone holder",
        "phone stand", "screen protector", "phone grip",
        "phone cable", "phone mount",
    ],
    "Toys_and_Games": [
        "toys", "kids toys", "educational toys", "board games",
        "puzzles", "lego", "dolls", "action figures",
        "stuffed animals", "outdoor toys", "card games",
        "building blocks",
    ],
    "Electronics": [
        "wireless earbuds", "bluetooth speaker", "smart home",
        "security camera", "smart watch", "laptop",
        "tablet", "monitor", "soundbar", "charger",
        "power bank", "usb cable", "hdmi cable", "router",
        "keyboard", "mouse",
    ],
    "All_Beauty": ["beauty essentials", "cosmetics", "skincare"],
    "Musical_Instruments": [
        "acoustic guitar", "electric guitar", "drums",
        "keyboard piano", "microphone", "headphones for music",
        "guitar accessories", "music stand",
    ],
    "Handmade_Products": ["handmade jewelry", "handmade home",
                           "handmade accessories", "handmade bags"],
    "Baby_Products": [
        "baby essentials", "diapers", "baby wipes", "baby food",
        "baby formula", "baby bottle", "stroller", "car seat",
        "crib", "baby monitor", "pacifier", "baby clothes",
    ],
    # --- TINY ---
    "Gift_Cards": ["gift cards"],
}


def build_search_url(keyword: str, brand: str = "", base_product: str = "",
                     node_id: str = "") -> str:
    """Amazon search URL — Spark-native when ``node_id`` is set.

    Logic:
      1. Strip ``(annotation)`` parenthetical content from keyword (CURATED
         category names like ``"Car accessories (organizer, phone mount)"``
         break Amazon search if left literal).
      2. If ``keyword`` is empty/short, synthesise one from ``brand`` + the
         first three meaningful words of ``base_product``.
      3. When ``node_id`` is a real node, emit a guide-format URL
         (``keywords=...&rh=n%3A...,AFN,Prime&c=ts``).
      4. Otherwise fall back to a basic ``s?k=...`` keyword search.
    """
    kw = re.sub(r"\s*\([^)]*\)", "", keyword or "").strip()
    if len(kw) < 4:
        bw = set((brand or "").lower().split())
        ws = [w for w in re.findall(r"[a-zA-Z]{3,}",
                                    (base_product or "").lower())
              if w not in _GENERIC_WORDS and w not in bw][:3]
        kw = " ".join(([brand.strip()] if brand else []) + ws) or "amazon"
    q = urllib.parse.quote_plus(kw)
    n = (node_id or "").strip()
    if n and n != _NODE_NONE:
        rh = f"n%3A{n}%2C{AFN_FILTER}%2C{PRIME_FILTER}"
        return (f"https://www.amazon.com/s?keywords={q}&rh={rh}"
                "&c=ts&s=review-count-rank")
    return f"https://www.amazon.com/s?k={q}&s=review-count-rank"
