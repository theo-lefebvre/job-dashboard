"""storage.py : mémoire des offres déjà vues (seen_offers.json).

Sert à afficher le badge NOUVEAU et à repérer les offres vraiment nouvelles
du jour (pour les alertes e-mail).
"""
import json
from datetime import datetime

NEW_BADGE_DAYS = 3         # une offre reste "NOUVELLE" pendant 3 jours
FORGET_AFTER_DAYS = 60     # on oublie une offre non revue depuis 60 jours


def _parse(value):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def load_seen(path="seen_offers.json"):
    """Lit la mémoire. Si le fichier n'existe pas encore, on part de zéro."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(seen, path="seen_offers.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=1, sort_keys=True)


def update_seen(offers, seen, today):
    """Met à jour la mémoire et le badge NOUVEAU.

    Renvoie la liste des offres vues pour la toute première fois aujourd'hui.
    """
    today_s = today.isoformat()
    new_this_run = []
    for offer in offers:
        entry = seen.get(offer.uid)
        if entry is None:
            seen[offer.uid] = {
                "first_seen": today_s,
                "last_seen": today_s,
                "title": offer.title,
                "company": offer.company,
            }
            new_this_run.append(offer)
            first = today
        else:
            entry["last_seen"] = today_s
            first = _parse(entry.get("first_seen")) or today
        offer.is_new = (today - first).days <= NEW_BADGE_DAYS
        if offer.is_new:
            offer.badges = ["NOUVEAU"] + [b for b in offer.badges if b != "NOUVEAU"]

    # On oublie les offres qu'on n'a plus revues depuis longtemps
    for uid in list(seen):
        last = _parse(seen[uid].get("last_seen"))
        if last and (today - last).days > FORGET_AFTER_DAYS:
            del seen[uid]
    return new_this_run
