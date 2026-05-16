"""Category routing table for the local HF Amazon-Reviews-2023 index.

Extracted from :mod:`modules.dataset_lookup` so that adding new categories
does not push that module past the 300-line hard limit.

Maps short keyword/phrase to the HuggingFace dataset category that holds
the relevant products. First match wins, so list **multi-word / specific
phrases before single-word fallbacks** to avoid generic words swallowing
specific intent (``"phone case"`` must match before ``"phone"``).
"""
from __future__ import annotations

CATEGORY_MAP: list[tuple[str, str]] = [
    # ------------------------------------------------------------------
    # Multi-word / specific phrases FIRST
    # ------------------------------------------------------------------
    # Niche reading/study/play spaces — route to closest indexed category
    # so the LLM mode doesn't fall through to its "Model 1/2/3" template.
    ("reading nook", "Home_and_Kitchen"),
    ("reading chair", "Home_and_Kitchen"),
    ("reading corner", "Home_and_Kitchen"),
    ("book nook", "Home_and_Kitchen"),
    ("study nook", "Office_Products"),
    ("study desk", "Office_Products"),
    ("kids tent", "Toys_and_Games"),
    ("play tent", "Toys_and_Games"),
    ("play mat", "Toys_and_Games"),
    ("teepee", "Toys_and_Games"),
    ("bean bag", "Home_and_Kitchen"),
    ("floor cushion", "Home_and_Kitchen"),
    ("bookshelf", "Home_and_Kitchen"),
    ("book shelf", "Home_and_Kitchen"),
    ("desk lamp", "Home_and_Kitchen"),
    ("night light", "Home_and_Kitchen"),
    ("diy kit", "Arts_Crafts_and_Sewing"),

    # Pet_Supplies (specific compounds before generic "toy")
    ("dog toy", "Pet_Supplies"), ("cat toy", "Pet_Supplies"),
    ("pet toy", "Pet_Supplies"), ("dog bed", "Pet_Supplies"),
    ("cat bed", "Pet_Supplies"), ("dog food", "Pet_Supplies"),
    ("cat food", "Pet_Supplies"), ("dog treat", "Pet_Supplies"),
    ("cat treat", "Pet_Supplies"), ("dog leash", "Pet_Supplies"),
    ("dog collar", "Pet_Supplies"), ("dog harness", "Pet_Supplies"),
    ("cat litter", "Pet_Supplies"), ("pet carrier", "Pet_Supplies"),
    ("fish tank", "Pet_Supplies"), ("aquarium", "Pet_Supplies"),

    # Health_and_Household (vitamins / OTC / household cleaning)
    ("vitamin", "Health_and_Household"),
    ("supplement", "Health_and_Household"),
    ("protein powder", "Health_and_Household"),
    ("multivitamin", "Health_and_Household"),
    ("probiotic", "Health_and_Household"),
    ("collagen", "Health_and_Household"),
    ("pain relief", "Health_and_Household"),
    ("first aid", "Health_and_Household"),
    ("bandage", "Health_and_Household"),
    ("toilet paper", "Health_and_Household"),
    ("paper towel", "Health_and_Household"),
    ("laundry detergent", "Health_and_Household"),
    ("dish soap", "Health_and_Household"),
    ("disinfectant", "Health_and_Household"),
    ("toothbrush", "Health_and_Household"),
    ("toothpaste", "Health_and_Household"),
    ("deodorant", "Health_and_Household"),
    ("razor", "Health_and_Household"),
    ("shaver", "Health_and_Household"),

    # Home_and_Kitchen
    ("kitchen gadget", "Home_and_Kitchen"),
    ("kitchen tool", "Home_and_Kitchen"),
    ("kitchen utensil", "Home_and_Kitchen"),
    ("cooking", "Home_and_Kitchen"), ("baking", "Home_and_Kitchen"),
    ("cookware", "Home_and_Kitchen"), ("bakeware", "Home_and_Kitchen"),
    ("knife set", "Home_and_Kitchen"), ("frying pan", "Home_and_Kitchen"),
    ("coffee maker", "Home_and_Kitchen"), ("blender", "Home_and_Kitchen"),
    ("air fryer", "Home_and_Kitchen"), ("toaster", "Home_and_Kitchen"),
    ("storage container", "Home_and_Kitchen"),
    ("cutting board", "Home_and_Kitchen"),
    ("bedding", "Home_and_Kitchen"), ("pillow", "Home_and_Kitchen"),
    ("vacuum cleaner", "Home_and_Kitchen"),

    # Baby_Products (before "toy"; before Health razor)
    ("baby bottle", "Baby_Products"), ("baby formula", "Baby_Products"),
    ("baby food", "Baby_Products"), ("baby monitor", "Baby_Products"),
    ("baby carrier", "Baby_Products"), ("baby gate", "Baby_Products"),
    ("car seat", "Baby_Products"), ("crib", "Baby_Products"),
    ("stroller", "Baby_Products"), ("pacifier", "Baby_Products"),
    ("diaper bag", "Baby_Products"), ("diaper", "Baby_Products"),
    ("baby clothes", "Baby_Products"),

    # Sports_and_Outdoors (before "outdoor" generic)
    ("yoga mat", "Sports_and_Outdoors"), ("yoga", "Sports_and_Outdoors"),
    ("dumbbell", "Sports_and_Outdoors"), ("kettlebell", "Sports_and_Outdoors"),
    ("resistance band", "Sports_and_Outdoors"),
    ("foam roller", "Sports_and_Outdoors"),
    ("treadmill", "Sports_and_Outdoors"),
    ("exercise bike", "Sports_and_Outdoors"),
    ("camping tent", "Sports_and_Outdoors"),
    ("sleeping bag", "Sports_and_Outdoors"),
    ("hiking backpack", "Sports_and_Outdoors"),
    ("fishing rod", "Sports_and_Outdoors"),
    ("fishing reel", "Sports_and_Outdoors"),
    ("golf club", "Sports_and_Outdoors"),
    ("tennis racket", "Sports_and_Outdoors"),
    ("basketball", "Sports_and_Outdoors"),
    ("soccer ball", "Sports_and_Outdoors"),
    ("baseball bat", "Sports_and_Outdoors"),
    ("kayak", "Sports_and_Outdoors"), ("paddle board", "Sports_and_Outdoors"),
    ("ski ", "Sports_and_Outdoors"), ("snowboard", "Sports_and_Outdoors"),
    ("bike helmet", "Sports_and_Outdoors"),

    # Office_Products
    ("office chair", "Office_Products"),
    ("office desk", "Office_Products"),
    ("office supplies", "Office_Products"),
    ("desk organizer", "Office_Products"),
    ("file cabinet", "Office_Products"),
    ("file folder", "Office_Products"),
    ("sticky note", "Office_Products"),
    ("ballpoint pen", "Office_Products"),
    ("printer paper", "Office_Products"),
    ("paper shredder", "Office_Products"),
    ("planner", "Office_Products"),
    ("notebook", "Office_Products"),

    # Beauty_and_Personal_Care (broader Beauty — supersedes All_Beauty)
    ("skin care", "Beauty_and_Personal_Care"),
    ("skincare", "Beauty_and_Personal_Care"),
    ("face cream", "Beauty_and_Personal_Care"),
    ("face mask", "Beauty_and_Personal_Care"),
    ("hair care", "Beauty_and_Personal_Care"),
    ("hair dryer", "Beauty_and_Personal_Care"),
    ("hair straightener", "Beauty_and_Personal_Care"),
    ("curling iron", "Beauty_and_Personal_Care"),
    ("makeup brush", "Beauty_and_Personal_Care"),
    ("nail polish", "Beauty_and_Personal_Care"),
    ("eyeliner", "Beauty_and_Personal_Care"),
    ("lipstick", "Beauty_and_Personal_Care"),
    ("mascara", "Beauty_and_Personal_Care"),
    ("foundation", "Beauty_and_Personal_Care"),
    ("shampoo", "Beauty_and_Personal_Care"),
    ("conditioner", "Beauty_and_Personal_Care"),
    ("serum", "Beauty_and_Personal_Care"),

    # Cell_Phones_and_Accessories
    ("cell phone", "Cell_Phones_and_Accessories"),
    ("phone case", "Cell_Phones_and_Accessories"),
    ("phone accessory", "Cell_Phones_and_Accessories"),
    ("phone holder", "Cell_Phones_and_Accessories"),
    ("phone stand", "Cell_Phones_and_Accessories"),
    ("screen protector", "Cell_Phones_and_Accessories"),

    # Toys_and_Games specific
    ("board game", "Toys_and_Games"),

    # ------------------------------------------------------------------
    # Single-word fallbacks
    # ------------------------------------------------------------------
    # Pet_Supplies
    ("pet ", "Pet_Supplies"), ("dog ", "Pet_Supplies"),
    ("cat ", "Pet_Supplies"), ("puppy", "Pet_Supplies"),
    ("kitten", "Pet_Supplies"), ("hamster", "Pet_Supplies"),
    ("bird ", "Pet_Supplies"), ("rabbit", "Pet_Supplies"),

    # Baby_Products
    ("baby", "Baby_Products"), ("infant", "Baby_Products"),
    ("newborn", "Baby_Products"), ("toddler", "Baby_Products"),

    # Beauty_and_Personal_Care (replaces former All_Beauty entries)
    ("skin", "Beauty_and_Personal_Care"),
    ("beauty", "Beauty_and_Personal_Care"),
    ("makeup", "Beauty_and_Personal_Care"),
    ("hair", "Beauty_and_Personal_Care"),
    ("nail", "Beauty_and_Personal_Care"),
    ("cosmetic", "Beauty_and_Personal_Care"),
    ("fragrance", "Beauty_and_Personal_Care"),
    ("perfume", "Beauty_and_Personal_Care"),

    # Electronics
    ("earbud", "Electronics"), ("headphone", "Electronics"),
    ("speaker", "Electronics"), ("camera", "Electronics"),
    ("tv", "Electronics"), ("monitor", "Electronics"),
    ("laptop", "Electronics"), ("electronic", "Electronics"),
    ("charger", "Electronics"), ("cable", "Electronics"),
    ("battery", "Electronics"), ("phone", "Electronics"),
    ("tablet", "Electronics"),

    # Toys_and_Games
    ("toy", "Toys_and_Games"), ("game", "Toys_and_Games"),
    ("puzzle", "Toys_and_Games"), ("doll", "Toys_and_Games"),
    ("lego", "Toys_and_Games"), ("children", "Toys_and_Games"),
    ("kids", "Toys_and_Games"),

    # Musical_Instruments
    ("guitar", "Musical_Instruments"), ("music", "Musical_Instruments"),
    ("piano", "Musical_Instruments"), ("drum", "Musical_Instruments"),
    ("microphone", "Musical_Instruments"),
    ("instrument", "Musical_Instruments"),

    # Sports_and_Outdoors
    ("fitness", "Sports_and_Outdoors"), ("exercise", "Sports_and_Outdoors"),
    ("workout", "Sports_and_Outdoors"), ("camping", "Sports_and_Outdoors"),
    ("hiking", "Sports_and_Outdoors"), ("cycling", "Sports_and_Outdoors"),
    ("bicycle", "Sports_and_Outdoors"), ("fishing", "Sports_and_Outdoors"),
    ("golf", "Sports_and_Outdoors"), ("tennis", "Sports_and_Outdoors"),
    ("running shoe", "Sports_and_Outdoors"),
    ("outdoor", "Sports_and_Outdoors"),

    # Office_Products
    ("office", "Office_Products"), ("stationery", "Office_Products"),
    ("calculator", "Office_Products"),

    # Industrial_and_Scientific
    ("industrial", "Industrial_and_Scientific"),
    ("scientific", "Industrial_and_Scientific"),
    ("lab", "Industrial_and_Scientific"),

    # Arts_Crafts_and_Sewing
    ("craft", "Arts_Crafts_and_Sewing"), ("sewing", "Arts_Crafts_and_Sewing"),
    ("paint", "Arts_Crafts_and_Sewing"), ("art ", "Arts_Crafts_and_Sewing"),

    # Handmade_Products
    ("handmade", "Handmade_Products"), ("handcraft", "Handmade_Products"),

    # Home_and_Kitchen
    ("kitchen", "Home_and_Kitchen"), ("home decor", "Home_and_Kitchen"),
]
