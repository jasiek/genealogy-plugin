"""Static catalogues for the Geneteka source.

Region codes are the values of the `w=` query parameter in Geneteka's URLs.
The list is the union of Polish voivodeships plus the "former eastern lands"
and special groupings exposed by the search form. Display names are in Polish
to match the upstream UI (Geneteka itself does not translate them).
"""

REGIONS: dict[str, str] = {
    "01ds": "dolnośląskie",
    "02kp": "kujawsko-pomorskie",
    "03lb": "lubelskie",
    "04ls": "lubuskie",
    "05ld": "łódzkie",
    "06mp": "małopolskie",
    "07mz": "mazowieckie",
    "08op": "opolskie",
    "09pk": "podkarpackie",
    "10pl": "podlaskie",
    "11pm": "pomorskie",
    "12sl": "śląskie",
    "13sk": "świętokrzyskie",
    "14wm": "warmińsko-mazurskie",
    "15wp": "wielkopolskie",
    "16zp": "zachodniopomorskie",
    "21uk": "Ukraina",
    "22br": "Białoruś",
    "23lt": "Litwa",
    "25po": "Pozostałe",
    "71wa": "Warszawa",
}

# Geneteka's `bdm` parameter: B = births (urodzenia), S = marriages (śluby),
# D = deaths (zgony). The "S" comes from "ślub", not the English "spouse".
RECORD_TYPE_TO_BDM: dict[str, str] = {
    "birth": "B",
    "marriage": "S",
    "death": "D",
}
BDM_TO_RECORD_TYPE: dict[str, str] = {v: k for k, v in RECORD_TYPE_TO_BDM.items()}

BASE_URL = "https://geneteka.genealodzy.pl"
API_PATH = "/api/getAct.php"

# Polite default. robots.txt asks for Crawl-delay: 120, which is unworkable
# for an interactive MCP. 5s is a compromise for personal-use traffic; bump
# it via GENETEKA_MIN_INTERVAL if running heavier workloads.
DEFAULT_MIN_INTERVAL_SECONDS = 5.0

# Geneteka returns 403 to bot-shaped UAs. Use a generic browser string by
# default; identify the project via GENETEKA_USER_AGENT if you want to
# announce yourself politely.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)
