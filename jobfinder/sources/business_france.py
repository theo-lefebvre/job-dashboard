"""Source : Business France (Mon Volontariat International), offres de VIE / VIA.

ATTENTION : ce site n'a pas d'API officielle. Cette source utilise l'interface
interne du site, qui peut changer sans prévenir. Si elle casse, l'erreur
s'affiche dans l'onglet « Sources » du dashboard et le reste continue de marcher.
"""
import time

import requests

from jobfinder.models import Offer

NAME = "business_france"   # même nom que dans config.yaml (section sources)
API_URL = "https://civiweb-api-prd.azurewebsites.net/api/Offers/search"
SITE_URL = "https://mon-vie-via.businessfrance.fr"
PAGE_SIZE = 100       # offres demandées par appel
MAX_OFFERS = 3000     # plafond de sécurité
PAUSE = 0.5           # pause entre deux appels (on reste poli avec le site)
TIMEOUT = 30

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": SITE_URL,
    "Referer": SITE_URL + "/",
    "User-Agent": "Mozilla/5.0 (compatible; job-dashboard personnel)",
}


def _first(item, *keys):
    """Premier champ non vide parmi plusieurs noms possibles."""
    for key in keys:
        value = item.get(key)
        if value not in (None, "", []):
            return value
    return ""


def _day(value):
    return str(value)[:10] if value else None


def _body(skip):
    return {
        "limit": PAGE_SIZE, "skip": skip, "query": None,
        "activitySectorId": [], "missionsTypesIds": [], "missionsDurations": [],
        "gerographicZones": [], "countriesIds": [], "studiesLevelId": [],
        "companiesSizes": [], "specializationsIds": [], "entreprisesIds": [0],
        "missionStartDate": None,
    }


def _to_offer(item):
    title = _first(item, "missionTitle", "title")
    if not title:
        return None
    offer_id = _first(item, "id", "offerId")
    mission_type = str(_first(item, "missionType", "type") or "VIE").upper()
    parts = [f"Mission {mission_type}"]
    duration = _first(item, "missionDuration", "duration")
    if duration:
        parts.append(f"Durée : {duration} mois")
    for key in ("missionDescription", "missionProfile", "organizationPresentation"):
        text = _first(item, key)
        if text:
            parts.append(str(text))
    salary = ""
    amount = _first(item, "indemnite", "indemnityAmount")
    try:
        salary = f"{round(float(amount))} €/mois" if amount else ""
    except (TypeError, ValueError):
        salary = ""
    return Offer(
        title=str(title),
        company=str(_first(item, "organizationName", "companyName") or "Entreprise non précisée"),
        url=f"{SITE_URL}/offres/{offer_id}" if offer_id else SITE_URL,
        city=str(_first(item, "cityName", "cityNameEn")),
        country=str(_first(item, "countryName", "countryNameEn")),
        published=_day(_first(item, "startBroadcastDate", "creationDate")),
        start_date=_day(_first(item, "missionStartDate")),
        deadline=_day(_first(item, "endBroadcastDate")),
        contract="VIE",   # VIE et VIA sont traités ensemble
        salary=salary,
        description="\n".join(parts),
        source=NAME,
    )


def fetch(cfg):
    """Récupère toutes les offres de VIE/VIA actuellement en ligne."""
    offers, skip, total = [], 0, None
    session = requests.Session()
    session.headers.update(HEADERS)
    while len(offers) < MAX_OFFERS:
        try:
            response = session.post(API_URL, json=_body(skip), timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except Exception:
            if skip == 0:
                raise      # échec dès le début : l'erreur sera affichée dans « Sources »
            break          # échec plus tard : on garde ce qu'on a déjà
        items = data.get("result") if isinstance(data, dict) else data
        if not items:
            if skip == 0:
                keys = list(data)[:8] if isinstance(data, dict) else type(data).__name__
                raise RuntimeError(f"Réponse vide ou inattendue (clés : {keys})")
            break
        for item in items:
            offer = _to_offer(item)
            if offer:
                offers.append(offer)
        if total is None and isinstance(data, dict):
            total = data.get("count")
        skip += len(items)
        if total is not None and skip >= total:
            break
        time.sleep(PAUSE)
    return offers
