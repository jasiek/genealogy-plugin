"""Heredis sentinel values and code-to-label mappings.

The schema reference is in SCHEMA.md.
"""

DATE_TRI_NONE = 100_000_000_000.0
COORD_NONE = 2_000_000.0

SEX_FROM_CODE = {109: "M", 102: "F", 63: "U"}
SEX_TO_CODE = {v: k for k, v in SEX_FROM_CODE.items()}

# Event-type sets baked into Heredis triggers (SCHEMA.md §Triggers).
BIRTH_EVENT_TYPES = (4, 8)
DEATH_EVENT_TYPES = (12, 6)
MARRIAGE_EVENT_TYPES = (59, 61, 68, 69)

# Best-effort labels for event types observed in the wild. Heredis does not
# expose the full enum; users should fall back to the numeric code when the
# label is "Unknown".
EVENT_TYPE_LABELS = {
    1: "Generic",
    4: "Birth",
    6: "Death",
    8: "Baptism",
    12: "Burial",
    13: "Cremation",
    15: "Christening",
    16: "Confirmation",
    17: "Bar/Bat Mitzvah",
    18: "Adult Christening",
    21: "Adoption",
    23: "Naturalization",
    26: "Emigration",
    27: "Immigration",
    30: "Residence",
    54: "Custom",
    57: "Custom",
    59: "Engagement",
    61: "Marriage",
    68: "Religious Marriage",
    69: "Civil Marriage",
    90: "Custom",
    97: "Custom",
    99: "Custom",
}

UNION_TYPE_LABELS = {
    0: "Marriage",
    1: "Annulment",
    2: "Separation",
    3: "Divorce",
    4: "Engagement",
    5: "Cohabitation",
}
