"""Modèle commun : une offre d'emploi, quelle que soit sa source."""
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Offer:
    # --- Informations données par la source ---
    title: str
    company: str
    url: str = ""
    location: str = ""            # texte brut du lieu, tel qu'écrit dans l'offre
    city: str = ""
    country: str = ""
    published: Optional[str] = None    # date de publication, format "2026-10-13"
    start_date: Optional[str] = None   # date de début, format "2027-04-01"
    deadline: Optional[str] = None     # date limite de candidature
    contract: str = ""            # "stage", "VIE", "graduate" ou "autre"
    salary: str = ""
    description: str = ""
    source: str = ""              # nom de la source (ex : "business_france")

    # --- Champs remplis plus tard par matching.py et storage.py ---
    score: int = 0
    score_details: list = field(default_factory=list)   # pourquoi ce score
    badges: list = field(default_factory=list)
    is_new: bool = False

    @property
    def uid(self) -> str:
        """Identifiant stable : sert à reconnaître une offre déjà vue."""
        base = self.url.strip().lower()
        if not base:
            base = f"{self.title}|{self.company}|{self.location}".lower()
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["uid"] = self.uid
        return data
