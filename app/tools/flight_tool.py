"""Live flight lookup via AviationStack.

The API returns live flight *status*, never fares — the tool docstring and the system
prompt both say so, because otherwise the model presents a schedule as a price quote.
"""

import logging
import re

import airportsdata
import pycountry
import requests
from langchain.tools import tool

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.aviationstack.com/v1/flights"

AIRPORTS = airportsdata.load("IATA")


COUNTRY_ALIASES = {
    "usa": "US",
    "u.s.a": "US",
    "u.s.": "US",
    "america": "US",
    "united states": "US",
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "england": "GB",
    "uae": "AE",
    "dubai": "AE",
    "south korea": "KR",
    "korea": "KR",
    "russia": "RU",
    "vietnam": "VN",
    "bangladesh": "BD",
    "india": "IN",
    "japan": "JP",
    "china": "CN",
    "singapore": "SG",
    "malaysia": "MY",
    "thailand": "TH",
    "indonesia": "ID",
    "nepal": "NP",
    "qatar": "QA",
    "saudi arabia": "SA",
    "turkey": "TR",
    "canada": "CA",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "italy": "IT",
    "spain": "ES",
}


COUNTRY_MAIN_AIRPORT = {
    "BD": "DAC",
    "IN": "DEL",
    "JP": "NRT",
    "US": "JFK",
    "GB": "LHR",
    "AE": "DXB",
    "SG": "SIN",
    "MY": "KUL",
    "TH": "BKK",
    "ID": "CGK",
    "CN": "PEK",
    "KR": "ICN",
    "NP": "KTM",
    "QA": "DOH",
    "SA": "JED",
    "TR": "IST",
    "CA": "YYZ",
    "AU": "SYD",
    "DE": "FRA",
    "FR": "CDG",
    "IT": "FCO",
    "ES": "MAD",
}


CITY_MAIN_AIRPORT = {
    "dhaka": "DAC",
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "kolkata": "CCU",
    "chennai": "MAA",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "tokyo": "NRT",
    "osaka": "KIX",
    "kyoto": "KIX",
    "new york": "JFK",
    "london": "LHR",
    "dubai": "DXB",
    "singapore": "SIN",
    "kuala lumpur": "KUL",
    "bangkok": "BKK",
    "doha": "DOH",
    "istanbul": "IST",
    "toronto": "YYZ",
    "sydney": "SYD",
    "paris": "CDG",
    "rome": "FCO",
    "madrid": "MAD",
    "frankfurt": "FRA",
    # Curated because the generic airport-name search picks same-named towns elsewhere:
    # "bali" alone matches Bali, Cameroon (BLC) rather than Denpasar (DPS).
    "bali": "DPS",
    "denpasar": "DPS",
    "phuket": "HKT",
    "maldives": "MLE",
    "male": "MLE",
    "kathmandu": "KTM",
    "colombo": "CMB",
    "hanoi": "HAN",
    "ho chi minh": "SGN",
    "saigon": "SGN",
    "seoul": "ICN",
    "hong kong": "HKG",
    "shanghai": "PVG",
    "beijing": "PEK",
    "abu dhabi": "AUH",
    "jeddah": "JED",
    "riyadh": "RUH",
    "cairo": "CAI",
    "amsterdam": "AMS",
    "barcelona": "BCN",
    "venice": "VCE",
    "milan": "MXP",
    "zurich": "ZRH",
    "athens": "ATH",
    "lisbon": "LIS",
    "los angeles": "LAX",
    "san francisco": "SFO",
    "chicago": "ORD",
    "melbourne": "MEL",
}


def clean_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    stop_words = [
        "flight",
        "flights",
        "ticket",
        "tickets",
        "trip",
        "travel",
        "plan",
        "complete",
        "days",
        "day",
        "including",
        "hotel",
        "hotels",
        "sightseeing",
        "under",
        "budget",
        "info",
        "information",
    ]
    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words).strip()


def country_name_to_code(text: str) -> str | None:
    text = clean_text(text)

    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]

    try:
        return pycountry.countries.lookup(text).alpha_2
    except LookupError:
        pass

    for country in pycountry.countries:
        if country.name.lower() in text:
            return country.alpha_2

    for alias, code in COUNTRY_ALIASES.items():
        if alias in text:
            return code

    return None


def airport_country_matches(airport: dict, country_code: str) -> bool:
    airport_country = str(airport.get("country", "")).upper().strip()

    if airport_country == country_code:
        return True

    country = pycountry.countries.get(alpha_2=country_code)

    return bool(country) and airport_country.lower() == country.name.lower()


def get_best_airport_for_country(country_code: str) -> str | None:
    preferred = COUNTRY_MAIN_AIRPORT.get(country_code)

    if preferred and preferred in AIRPORTS:
        return preferred

    candidates = []

    for iata, airport in AIRPORTS.items():
        if not iata:
            continue

        if airport_country_matches(airport, country_code):
            name = str(airport.get("name", "")).lower()
            city = str(airport.get("city", "")).lower()

            score = 0

            if "international" in name:
                score += 50
            if "intl" in name:
                score += 40
            if "capital" in name:
                score += 20
            if city:
                score += 5

            candidates.append((score, iata))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def resolve_location_to_iata(location: str) -> str | None:
    """Convert a country, city, airport name or IATA code into an IATA code.

    Bangladesh -> DAC, Japan -> NRT, Dhaka -> DAC, Tokyo -> NRT, DAC -> DAC.
    """

    if not location:
        return None

    raw_location = location.strip()

    if re.fullmatch(r"[A-Za-z]{3}", raw_location):
        code = raw_location.upper()
        if code in AIRPORTS:
            return code

    location_clean = clean_text(raw_location)

    if not location_clean:
        return None

    if location_clean in CITY_MAIN_AIRPORT:
        return CITY_MAIN_AIRPORT[location_clean]

    country_code = country_name_to_code(location_clean)
    if country_code:
        airport = get_best_airport_for_country(country_code)
        if airport:
            return airport

    city_matches = []

    for iata, airport in AIRPORTS.items():
        city = str(airport.get("city", "")).lower().strip()
        name = str(airport.get("name", "")).lower().strip()

        score = 0

        if city == location_clean:
            score += 100
        elif location_clean in city:
            score += 70

        if location_clean in name:
            score += 50

        # A tie-breaker between real matches only: applied unconditionally it would
        # score every international airport, so unknown places stopped returning None.
        if score == 0:
            continue

        if "international" in name:
            score += 10

        city_matches.append((score, iata))

    if city_matches:
        city_matches.sort(reverse=True)
        return city_matches[0][1]

    return None


def format_flight(flight: dict) -> str:
    # AviationStack sends `null` rather than omitting a sub-object, so every lookup needs
    # `or {}` — a plain `.get(key, {})` still yields None.
    airline = (flight.get("airline") or {}).get("name") or "Unknown airline"
    flight_number = (flight.get("flight") or {}).get("iata") or "Unknown flight number"
    status = flight.get("flight_status") or "Unknown"

    dep = flight.get("departure") or {}
    arr = flight.get("arrival") or {}

    dep_airport = dep.get("airport") or "Unknown departure airport"
    dep_iata = dep.get("iata") or "Unknown"
    dep_terminal = dep.get("terminal") or "N/A"
    dep_gate = dep.get("gate") or "N/A"
    dep_scheduled = dep.get("scheduled") or "Unknown"
    dep_delay = dep.get("delay")
    dep_delay_text = f"{dep_delay} minutes" if dep_delay is not None else "N/A"

    arr_airport = arr.get("airport") or "Unknown arrival airport"
    arr_iata = arr.get("iata") or "Unknown"
    arr_terminal = arr.get("terminal") or "N/A"
    arr_gate = arr.get("gate") or "N/A"
    arr_scheduled = arr.get("scheduled") or "Unknown"
    arr_delay = arr.get("delay")
    arr_delay_text = f"{arr_delay} minutes" if arr_delay is not None else "N/A"

    return f"""
Airline: {airline}
Flight: {flight_number}
Status: {status}

Departure:
- Airport: {dep_airport}
- IATA: {dep_iata}
- Terminal: {dep_terminal}
- Gate: {dep_gate}
- Scheduled: {dep_scheduled}
- Delay: {dep_delay_text}

Arrival:
- Airport: {arr_airport}
- IATA: {arr_iata}
- Terminal: {arr_terminal}
- Gate: {arr_gate}
- Scheduled: {arr_scheduled}
- Delay: {arr_delay_text}
""".strip()


def _describe_route(dep_iata: str | None, arr_iata: str | None) -> str:
    if dep_iata and arr_iata:
        return f"from {dep_iata} to {arr_iata}"
    if dep_iata:
        return f"from {dep_iata}"
    return f"to {arr_iata}"


def _fetch_flights(dep_iata: str | None, arr_iata: str | None, limit: int) -> str:
    """Call AviationStack for a resolved route and format the result for the LLM.

    Always returns a string — never raises. A raised exception would abort the whole
    graph run; a returned error string lets the model apologise and carry on.
    """
    if not settings.aviationstack_api_key:
        return (
            "Flight API error: AVIATIONSTACK_API_KEY is missing.\n"
            "Please add this in your .env file:\n"
            "AVIATIONSTACK_API_KEY=your_api_key_here"
        )

    params = {
        "access_key": settings.aviationstack_api_key,
        "limit": limit,
    }

    if dep_iata:
        params["dep_iata"] = dep_iata

    if arr_iata:
        params["arr_iata"] = arr_iata

    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
    except requests.exceptions.RequestException as exc:
        # Never interpolate the exception: its message carries the request URL, and the
        # URL carries the API key.
        logger.warning("aviationstack request failed: %s", exc)
        return "Flight API request failed. Live flight data is unavailable right now."
    except ValueError:
        return "Flight API returned invalid JSON."

    if not isinstance(data, dict):
        return "Flight API returned an unexpected response."

    if error := data.get("error"):
        logger.warning("aviationstack error response: %s", error)
        detail = error if isinstance(error, str) else error.get("message", "unknown")
        return f"Flight API error: {detail}"

    flight_data = data.get("data") or []

    route = _describe_route(dep_iata, arr_iata)

    if not flight_data:
        return (
            f"No live flight data found {route}. This tool only reports flights currently "
            "in the live schedule, so a valid route can still come back empty. Use "
            "web_search for which airlines serve the route and for fare estimates."
        )

    formatted_flights = [format_flight(flight) for flight in flight_data[:limit]]

    return f"Live flights {route}\n\n" + "\n\n---\n\n".join(formatted_flights)


@tool("search_flights")
def search_flights(
    origin: str | None = None,
    destination: str | None = None,
    limit: int = 10,
) -> str:
    """Look up LIVE flight status and schedules between two places.

    Accepts city names, country names, or IATA codes — "Dhaka", "Japan", and "NRT" all
    work. Give both for a specific route, destination alone to see arriving flights, or
    origin alone to see departures. At least one of the two is required.

    Returns airline, flight number, current status, terminal, gate, scheduled times and
    delays for flights currently in the system.

    IMPORTANT: this returns live operational flight data ONLY. It does NOT return ticket
    prices, fares, or bookable future itineraries. Never quote a price from this tool's
    output. For fare estimates, use the web_search tool instead and label the figure as
    an estimate.

    Args:
        origin: Departure city, country, or IATA code.
        destination: Arrival city, country, or IATA code.
        limit: Maximum number of flights to return (1-100). Defaults to 10.
    """
    if not origin and not destination:
        return "Specify at least an origin or a destination, e.g. origin='Dhaka'."

    dep_iata = resolve_location_to_iata(origin) if origin else None
    arr_iata = resolve_location_to_iata(destination) if destination else None

    # Report resolution failures back to the model rather than silently widening the
    # search — a global flight dump is worse than an actionable error.
    if origin and not dep_iata:
        return (
            f"Could not resolve '{origin}' to an airport. "
            "Try a major city name (e.g. 'Dhaka') or a 3-letter IATA code (e.g. 'DAC')."
        )

    if destination and not arr_iata:
        return (
            f"Could not resolve '{destination}' to an airport. "
            "Try a major city name (e.g. 'Tokyo') or a 3-letter IATA code (e.g. 'NRT')."
        )

    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 10

    return _fetch_flights(dep_iata, arr_iata, limit)
