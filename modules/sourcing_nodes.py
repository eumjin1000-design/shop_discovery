"""Amazon browse-node id lookup table — extracted from
:mod:`modules.sourcing` to keep that module under the 300-line hard limit.

Hand-curated mapping from short category phrases to amazon.com browse-node
ids. Used by :func:`modules.sourcing._guess_node` when the LLM does not
supply a node id of its own.
"""
from __future__ import annotations

NODE_DB: dict[str, str] = {
    # Pet Supplies
    "pet supplies": "2619533011", "dog supplies": "2619533011", "cat supplies": "2619533011",
    "fish aquarium": "2619534011", "bird supplies": "3606785011", "small animal": "3606786011",
    # Health & Beauty
    "vitamins supplements": "3774861", "health household": "3760901", "sports nutrition": "6973663011",
    "personal care": "11060451", "skin care": "11060451", "hair care": "11057771", "oral care": "3760931",
    # Kitchen
    "kitchen dining": "284507", "cookware": "289914", "bakeware": "289739", "kitchen tools": "289973",
    "small appliances": "298092", "coffee": "678508011",
    # Home
    "home kitchen": "1055398", "bedding": "3732961", "bath": "3610841", "furniture": "1063306",
    # Bed Pillows (Home & Kitchen > Bedding > Bed Pillows & Positioners > Bed Pillows).
    # "memory foam pillow" (3-word) outranks "pillow" so #1 shop maps precisely.
    "memory foam pillow": "1063252", "pillow": "1063252", "mattress topper": "1063252",
    "storage organization": "3737461", "cleaning supplies": "3760901", "lighting": "495224", "led strip": "495224",
    # Fitness & Sports
    "sports outdoors": "3375251", "exercise fitness": "3407731", "yoga": "3407731",
    "camping hiking": "3375381", "cycling": "3403875", "running": "3375271",
    # Electronics
    "electronics": "172659", "headphones": "745384", "bluetooth speaker": "172659",
    "phone accessories": "2335752011", "laptop accessories": "541966", "smart home": "6563140011",
    "security camera": "172659", "power bank": "172659",
    # Baby
    "baby": "165797011", "baby care": "165797011", "diapering": "165796011",
    "feeding": "166585011", "baby toys": "165793011",
    # Clothing & Fashion
    "clothing": "7141123011", "mens clothing": "1036592", "womens clothing": "1045024",
    "shoes": "672123011",
    # NOTE: "accessories" 단일어 키는 제거 — 너무 일반적이어서 임의의
    # "{category} accessories" 입력을 Clothing 노드로 잘못 라우팅함.
    # 카테고리 특화 compound (phone accessories, car accessories 등)만 유지.
    # Office
    "office products": "1069242", "office supplies": "1069242", "desk accessories": "1069242",
    # Ergonomic / Standing Desk Workspace (Office Products parent로 안전 라우팅)
    "ergonomic": "1069242", "ergonomics": "1069242", "ergonomic chair": "1069242",
    "standing desk": "1069242", "standing desk converter": "1069242",
    "footrest": "1069242", "keyboard tray": "1069242", "monitor stand": "1069242",
    # Computer Peripherals (Electronics 노드 활용)
    "ergonomic keyboard": "541966", "ergonomic mouse": "541966",
    "mechanical keyboard": "541966", "wireless mouse": "541966",
    "monitor arm": "541966", "monitor mount": "541966",
    # Anti-fatigue / Floor Mat (Home & Kitchen 노드)
    "anti fatigue mat": "1055398", "standing mat": "1055398", "floor mat": "1055398",
    # Automotive
    "automotive": "15684181", "car accessories": "15684181", "car electronics": "15684181",
    # Outdoor & Garden
    "garden outdoor": "2972638011", "patio furniture": "3732961", "lawn care": "3238155011", "plants": "3238155011",
    # Toys & Games
    "toys games": "165793011", "board games": "166925011", "puzzles": "166943011", "outdoor play": "165793011",
    # Arts & Crafts
    "arts crafts": "2617942011", "painting": "2617942011", "sewing": "2617942011",
    # Food & Grocery
    "grocery food": "16310101", "snacks": "16310101", "beverages": "16310101", "organic food": "16310101",
}
