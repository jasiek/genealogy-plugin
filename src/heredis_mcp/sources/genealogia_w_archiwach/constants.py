"""Constants for Genealogia w Archiwach."""

BASE_URL = "https://www.genealogiawarchiwach.pl"
APP_PATH = "/archiwum-front"
UIDL_PATH = "/UIDL/"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
DEFAULT_MIN_INTERVAL_SECONDS = 5.0

SEARCH_SCOPE_KEYS = {
    "all": "1",
    "units": "2",
    "indexes": "3",
    "people": "4",
    "pradziad": "5",
}

PERSON_ROLE_KEYS = {
    "deceased": "1",
    "child": "2",
    "mother": "3",
    "father": "4",
    "bride": "5",
    "groom": "6",
    "all": "7",
}

ACT_TYPE_KEYS = {
    "birth": "1",
    "death": "2",
    "marriage": "3",
}
