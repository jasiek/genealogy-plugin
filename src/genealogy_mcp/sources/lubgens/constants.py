"""Static config for the Lubgens regional index source.

The Lubelskie Korzenie society publishes its regional vital-record index
("Baza indeksów Lubelszczyzny") at https://regestry.lubgens.eu. The
search form on ``news.php`` POSTs to ``viewpage.php?page_id=1057`` and
returns a full HTML page with up to three result tables (births,
marriages, deaths). The upstream caps each table at 500 rows per query.
"""

DEFAULT_BASE_URL = "https://regestry.lubgens.eu"
SEARCH_PATH = "/viewpage.php?page_id=1057"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_MIN_INTERVAL_SECONDS = 5.0

# wildmode dropdown values from the upstream form.
WILDMODE_TO_INT: dict[str, int] = {
    "prefix": 1,  # "Dopasuj poczatek wyrazu" — default
    "exact": 2,  # "Szukaj dokladnie"
    "substring": 3,  # "Szukaj tez w srodku wyrazu"
}

RECORD_TYPE_TO_FIELD: dict[str, str] = {
    "birth": "urodz",
    "marriage": "sluby",
    "death": "zgony",
}
