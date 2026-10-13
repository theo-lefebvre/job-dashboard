"""Source : pages carrières d'entreprises (Greenhouse, Lever, Ashby).

Ces trois outils de recrutement fournissent une interface publique pour lire
les offres d'une entreprise. Les entreprises à suivre sont listées dans
config.yaml (section sites_carrieres_liste).
Seules les offres dont l'intitulé correspond à tes métiers sont gardées.
"""
import html
import re
from datetime import datetime, timezone

import requests

from jobfinder import matching
from jobfinder.models import Offer

NAME = "sites_carrieres"   # même nom que dans config.yaml (section sources)
TIMEOUT = 30
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; job-dashboard personnel)",
}


def _clean(text):
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:1500]


def _relevant(title, cfg):
    """Garde seulement les intitulés qui ressemblent à mes métiers."""
    metiers = cfg.get("metiers") or {}
    terms = (metiers.get("prioritaires") or []) + (metiers.get("acceptables") or [])
    return bool(matching.find_terms(matching.norm(title), terms))


def _get_json(url, params=None):
    response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def _greenhouse(company, ident):
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{ident}/jobs",
                     {"content": "true"})
    for job in data.get("jobs", []):
        published = str(job.get("first_published") or job.get("updated_at") or "")[:10]
        yield Offer(
            title=job.get("title", ""), company=company,
            url=job.get("absolute_url", ""),
            location=(job.get("location") or {}).get("name", ""),
            published=published or None,
            description=_clean(job.get("content")), source=NAME,
        )


def _lever(company, ident, host="api.lever.co"):
    data = _get_json(f"https://{host}/v0/postings/{ident}", {"mode": "json"})
    for job in data:
        cats = job.get("categories") or {}
        published = None
        if job.get("createdAt"):
            published = datetime.fromtimestamp(job["createdAt"] / 1000, tz=timezone.utc).date().isoformat()
        yield Offer(
            title=job.get("text", ""), company=company,
            url=job.get("hostedUrl", ""), location=cats.get("location", "") or "",
            contract=cats.get("commitment", "") or "", published=published,
            description=_clean(job.get("descriptionPlain")), source=NAME,
        )


def _ashby(company, ident):
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{ident}")
    for job in data.get("jobs", []):
        yield Offer(
            title=job.get("title", ""), company=company,
            url=job.get("jobUrl", ""), location=job.get("location", "") or "",
            contract=job.get("employmentType", "") or "",
            published=str(job.get("publishedAt") or "")[:10] or None,
            description=_clean(job.get("descriptionPlain")), source=NAME,
        )


def fetch(cfg):
    boards = cfg.get("sites_carrieres_liste") or []
    offers, errors = [], []
    for board in boards:
        company = board.get("entreprise", "?")
        kind = matching.norm(board.get("type"))
        ident = board.get("identifiant", "")
        try:
            if kind == "greenhouse":
                found = _greenhouse(company, ident)
            elif kind == "lever":
                found = _lever(company, ident)
            elif kind == "lever_eu":
                found = _lever(company, ident, host="api.eu.lever.co")
            elif kind == "ashby":
                found = _ashby(company, ident)
            else:
                raise ValueError(f"type inconnu : {kind}")
            kept = [o for o in found if o.title and _relevant(o.title, cfg)]
            print(f"[{NAME}] {company} : {len(kept)} offre(s) pertinente(s)")
            offers.extend(kept)
        except Exception as exc:
            errors.append(f"{company} : {type(exc).__name__} {str(exc)[:80]}")
            print(f"[{NAME}] {company} : ERREUR {exc}")
    if errors and not offers:
        raise RuntimeError(" | ".join(errors)[:300])
    return offers
