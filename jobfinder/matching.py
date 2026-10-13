"""matching.py : filtres + score sur 100.

Ce fichier lit tes préférences dans config.yaml. Tu n'as normalement pas besoin
de le modifier : tout se règle dans config.yaml.
"""
import re
import unicodedata
from datetime import date, datetime, timedelta

# --- Réglages internes ---
PENALITE_MOTS_A_EVITER = 40        # points retirés si le titre contient un mot à pénaliser
TOLERANCE_AVANT_FENETRE_JOURS = 30  # stage commençant trop tôt avant ta fenêtre
TOLERANCE_APRES_FENETRE_JOURS = 60  # stage commençant trop tard après ta fenêtre

# Libellés affichés dans l'onglet « Sources »
REASON_LABELS = {
    "doublon": "Doublons",
    "entreprise_exclue": "Entreprise exclue",
    "titre_exclu": "Mot exclu dans le titre",
    "contrat_refuse": "Contrat refusé (CDI, alternance, volontariat…)",
    "poste_senior": "Poste senior ou manager",
    "experience": "Trop d'années d'expérience exigées",
    "secteur_exclu": "Secteur exclu",
    "pays": "Pays hors de ma liste",
    "date_limite_depassee": "Date limite dépassée",
    "date_debut": "Début de stage hors de ma fenêtre",
}

SENIOR_WORDS = [
    "senior", "confirme", "experimente", "experienced", "director", "directeur",
    "directrice", "head of", "principal", "vice president", "vp", "partner",
    "associe", "manager", "lead", "responsable",
]

COUNTRY_ALIASES = {
    "france": "france", "united kingdom": "royaume-uni", "uk": "royaume-uni",
    "england": "royaume-uni", "great britain": "royaume-uni", "royaume-uni": "royaume-uni",
    "switzerland": "suisse", "suisse": "suisse", "belgium": "belgique",
    "belgique": "belgique", "luxembourg": "luxembourg", "netherlands": "pays-bas",
    "the netherlands": "pays-bas", "pays-bas": "pays-bas", "germany": "allemagne",
    "allemagne": "allemagne", "spain": "espagne", "espagne": "espagne",
    "italy": "italie", "italie": "italie", "ireland": "irlande", "irlande": "irlande",
    "portugal": "portugal", "united arab emirates": "emirats arabes unis",
    "uae": "emirats arabes unis", "emirats arabes unis": "emirats arabes unis",
    "saudi arabia": "arabie saoudite", "arabie saoudite": "arabie saoudite",
    "qatar": "qatar", "canada": "canada", "australia": "australie",
    "australie": "australie", "brazil": "bresil", "brasil": "bresil", "bresil": "bresil",
}

ISO_CODES = {
    "fr": "france", "gb": "royaume-uni", "uk": "royaume-uni", "ch": "suisse",
    "be": "belgique", "lu": "luxembourg", "nl": "pays-bas", "de": "allemagne",
    "es": "espagne", "it": "italie", "ie": "irlande", "pt": "portugal",
    "ae": "emirats arabes unis", "sa": "arabie saoudite", "qa": "qatar",
    "ca": "canada", "au": "australie", "br": "bresil",
}

COUNTRY_DISPLAY = {
    "france": "France", "royaume-uni": "Royaume-Uni", "suisse": "Suisse",
    "belgique": "Belgique", "luxembourg": "Luxembourg", "pays-bas": "Pays-Bas",
    "allemagne": "Allemagne", "espagne": "Espagne", "italie": "Italie",
    "irlande": "Irlande", "portugal": "Portugal",
    "emirats arabes unis": "Émirats arabes unis", "arabie saoudite": "Arabie saoudite",
    "qatar": "Qatar", "canada": "Canada", "australie": "Australie", "bresil": "Brésil",
}

# ville (sans accent) -> (nom affiché, pays)
CITIES = {
    "paris": ("Paris", "france"), "lyon": ("Lyon", "france"),
    "marseille": ("Marseille", "france"), "toulouse": ("Toulouse", "france"),
    "lille": ("Lille", "france"), "bordeaux": ("Bordeaux", "france"),
    "nantes": ("Nantes", "france"), "strasbourg": ("Strasbourg", "france"),
    "brussels": ("Bruxelles", "belgique"), "bruxelles": ("Bruxelles", "belgique"),
    "london": ("Londres", "royaume-uni"), "londres": ("Londres", "royaume-uni"),
    "zurich": ("Zurich", "suisse"), "geneva": ("Genève", "suisse"),
    "geneve": ("Genève", "suisse"), "luxembourg": ("Luxembourg", "luxembourg"),
    "amsterdam": ("Amsterdam", "pays-bas"), "dubai": ("Dubaï", "emirats arabes unis"),
    "abu dhabi": ("Abu Dhabi", "emirats arabes unis"),
    "riyadh": ("Riyad", "arabie saoudite"), "riyad": ("Riyad", "arabie saoudite"),
    "doha": ("Doha", "qatar"), "toronto": ("Toronto", "canada"),
    "montreal": ("Montréal", "canada"), "vancouver": ("Vancouver", "canada"),
    "sydney": ("Sydney", "australie"), "melbourne": ("Melbourne", "australie"),
    "sao paulo": ("São Paulo", "bresil"), "rio de janeiro": ("Rio de Janeiro", "bresil"),
    "madrid": ("Madrid", "espagne"), "barcelona": ("Barcelone", "espagne"),
    "barcelone": ("Barcelone", "espagne"), "milan": ("Milan", "italie"),
    "rome": ("Rome", "italie"), "berlin": ("Berlin", "allemagne"),
    "munich": ("Munich", "allemagne"), "frankfurt": ("Francfort", "allemagne"),
    "francfort": ("Francfort", "allemagne"), "dublin": ("Dublin", "irlande"),
    "lisbon": ("Lisbonne", "portugal"), "lisbonne": ("Lisbonne", "portugal"),
}

LANG_EN = {
    "portugais": "portuguese", "allemand": "german", "arabe": "arabic",
    "espagnol": "spanish", "francais": "french", "anglais": "english",
    "italien": "italian", "neerlandais": "dutch",
}
LEVEL_WORDS = (r"(?:courant|fluent|fluency|bilingue|bilingual|native|natif|maitrise|"
               r"mother tongue|proficien\w*|c1|c2)")

EXP_PATTERNS = [
    re.compile(r"(?:(\d{1,2})\s*(?:-|a|to|et)\s*)?(\d{1,2})\s*\+?\s*(?:ans|an|years|year|yrs|yr)"
               r"\s+(?:d'|d\s|of\s|de\s)?(?:(?:professional|relevant|work|prior|solid|significant|proven)\s+)?experience"),
    re.compile(r"(?:minimum|at least|au moins|min\.?)\s+(?:de\s+)?()(\d{1,2})\s*\+?\s*(?:ans|years|yrs)"),
    re.compile(r"experience\s+(?:professionnelle\s+)?(?:de\s+|d')?(?:minimum\s+)?()(\d{1,2})\s*\+?\s*(?:ans|years)"),
]


# ---------------------------------------------------------------------
# Petites fonctions utilitaires
# ---------------------------------------------------------------------
def norm(text):
    """Minuscules et sans accents, pour comparer facilement."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower().replace("’", "'")


def has_term(text_norm, term):
    t = norm(term).strip()
    if not t:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(t) + r"s?(?![a-z0-9])"
    return re.search(pattern, text_norm) is not None


def find_terms(text_norm, terms):
    return [t for t in (terms or []) if has_term(text_norm, t)]


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def canon_country(raw):
    n = norm(raw).strip()
    if n in ISO_CODES:
        return ISO_CODES[n]
    return COUNTRY_ALIASES.get(n, n)


def infer_location(offer):
    """Complète ville et pays quand c'est possible. Renvoie le pays (clé interne) ou ''."""
    country = canon_country(offer.country) if offer.country else ""
    text = norm(f"{offer.location} {offer.city}")
    city_display = ""
    for key, (display, ctry) in CITIES.items():
        if has_term(text, key):
            city_display = display
            if not country:
                country = ctry
            break
    if not country:
        for alias, ctry in COUNTRY_ALIASES.items():
            if has_term(text, alias):
                country = ctry
                break
    if country:
        offer.country = COUNTRY_DISPLAY.get(country, country.title())
    if not offer.city and city_display:
        offer.city = city_display
    return country


def detect_contract(offer):
    """Renvoie : stage, VIE, graduate, alternance, cdi, volontariat ou inconnu."""
    raw = norm(offer.contract)
    if raw in ("stage", "internship"):
        return "stage"
    if raw == "vie":
        return "VIE"
    if raw == "graduate":
        return "graduate"
    text = f"{norm(offer.title)} {raw}"
    if re.search(r"(?<![a-z])vie(?![a-z])|volontariat international", text):
        return "VIE"
    if re.search(r"graduate program|graduate scheme|management trainee|rotational|jeune diplome", text):
        return "graduate"
    if re.search(r"stage|stagiaire|intern(?:ship)?(?![a-z])|summer analyst", text):
        return "stage"
    if re.search(r"alternance|apprentissage|apprenti|work.?study|apprenticeship", text):
        return "alternance"
    if "volontariat" in text:
        return "volontariat"
    if re.search(r"(?<![a-z])cdi(?![a-z])|permanent", norm(offer.title)):
        return "cdi"
    return "inconnu"


def required_experience(text_norm):
    """Années d'expérience exigées (borne basse), ou None si rien n'est indiqué."""
    best = None
    for pattern in EXP_PATTERNS:
        for m in pattern.finditer(text_norm):
            before = text_norm[max(0, m.start() - 14):m.start()]
            if re.search(r"over|plus de|more than|since|depuis", before):
                continue  # ex : « plus de 50 ans d'expérience » = l'entreprise, pas le poste
            low, high = m.group(1), m.group(2)
            value = int(low) if low else int(high)
            if value > 15:
                continue
            best = value if best is None else max(best, value)
    return best


def language_requirements(desc_n, cfg):
    """Langues exigées à un niveau courant, parmi celles de config.yaml."""
    found = []
    for entry in (cfg.get("langues", {}) or {}).get("penaliser_si_exigee") or []:
        words = norm(entry).split()
        if not words:
            continue
        lang = words[0]
        for name in {lang, LANG_EN.get(lang, lang)}:
            name = re.escape(name)
            p1 = r"(?<![a-z])" + name + r"\W+(?:\w+\W+){0,4}?" + LEVEL_WORDS
            p2 = r"(?<![a-z])" + LEVEL_WORDS + r"\W+(?:\w+\W+){0,4}?" + name + r"(?![a-z])"
            if re.search(p1, desc_n) or re.search(p2, desc_n):
                found.append(lang)
                break
    return found


# ---------------------------------------------------------------------
# Analyse d'une offre : filtres, puis score
# ---------------------------------------------------------------------
def analyse(offer, cfg, today=None):
    """Renvoie la raison du retrait (texte) ou None si l'offre est gardée."""
    today = today or date.today()
    w = cfg.get("poids", {}) or {}
    contrats = cfg.get("contrats", {}) or {}
    metiers = cfg.get("metiers", {}) or {}
    lieux = cfg.get("lieux", {}) or {}

    title_n = norm(offer.title)
    company_n = norm(offer.company)
    desc_n = norm(offer.description)[:8000]

    # ---------- FILTRES (l'offre disparaît) ----------
    for name in cfg.get("entreprises_exclues") or []:
        if has_term(company_n, name):
            return "entreprise_exclue"

    for term in cfg.get("exclure_si_titre_contient") or []:
        if has_term(title_n, term):
            return "titre_exclu"

    contract = detect_contract(offer)
    refused = {norm(c) for c in contrats.get("refuses") or []}
    accepted = {norm(c) for c in contrats.get("acceptes") or []}
    if contract != "inconnu":
        if norm(contract) in refused or (accepted and norm(contract) not in accepted):
            return "contrat_refuse"
        offer.contract = contract

    if contract not in ("stage", "VIE", "graduate"):
        for term in SENIOR_WORDS:
            if has_term(title_n, term):
                return "poste_senior"

    exp = required_experience(f"{title_n} {desc_n}")
    exp_max = (cfg.get("experience", {}) or {}).get("annees_max", 2)
    if exp is not None and exp > exp_max:
        return "experience"

    for term in cfg.get("secteurs_exclus") or []:
        if has_term(title_n, term) or has_term(company_n, term):
            return "secteur_exclu"

    country_key = infer_location(offer)
    ok_countries = {canon_country(c) for c in lieux.get("pays_acceptes") or []}
    if country_key and ok_countries and country_key not in ok_countries:
        return "pays"

    deadline = parse_date(offer.deadline)
    if deadline and deadline < today:
        return "date_limite_depassee"

    start = parse_date(offer.start_date)
    cal = (cfg.get("calendrier", {}) or {}).get("stage", {}) or {}
    win_start = parse_date(cal.get("debut_au_plus_tot"))
    win_end = parse_date(cal.get("debut_au_plus_tard"))
    if contract == "stage" and start and win_start and win_end:
        if (start < win_start - timedelta(days=TOLERANCE_AVANT_FENETRE_JOURS)
                or start > win_end + timedelta(days=TOLERANCE_APRES_FENETRE_JOURS)):
            return "date_debut"

    # ---------- SCORE SUR 100 ----------
    score = 0.0
    details = []

    def add(label, key, default, ratio, why=""):
        nonlocal score
        weight = w.get(key, default)
        pts = weight * ratio
        score += pts
        text = f"{label} : {round(pts)}/{weight}"
        if why:
            text += f" ({why})"
        details.append(text)

    # 1. Métier
    prio = find_terms(title_n, metiers.get("prioritaires"))
    if prio:
        add("Intitulé", "metier", 30, 1.0, f"« {prio[0]} » dans le titre")
    else:
        acc = find_terms(title_n, metiers.get("acceptables"))
        if acc:
            add("Intitulé", "metier", 30, 0.5, f"rôle accepté : « {acc[0]} »")
        else:
            in_desc = find_terms(desc_n, metiers.get("prioritaires"))
            if in_desc:
                add("Intitulé", "metier", 30, 0.25, f"« {in_desc[0]} » seulement dans la description")
            else:
                add("Intitulé", "metier", 30, 0.0, "aucun intitulé ciblé")

    # 2. Employeur et secteur
    company_hit = [c for c in cfg.get("entreprises_prioritaires") or [] if has_term(company_n, c)]
    sector_text = f"{title_n} {company_n} {desc_n[:1500]}"
    if company_hit:
        add("Employeur", "employeur_secteur", 20, 1.0, f"entreprise prioritaire : {company_hit[0]}")
    else:
        sect = find_terms(sector_text, cfg.get("secteurs_prioritaires"))
        soft = find_terms(sector_text, cfg.get("secteurs_acceptes_si_mission_strategique"))
        if sect:
            add("Employeur", "employeur_secteur", 20, 0.6, f"secteur prioritaire : {sect[0]}")
        elif soft:
            add("Employeur", "employeur_secteur", 20, 0.4, f"secteur ouvert : {soft[0]}")
        else:
            add("Employeur", "employeur_secteur", 20, 0.0, "ni entreprise ni secteur prioritaire")

    # 3. Contrat et calendrier
    if contract == "inconnu":
        add("Contrat et dates", "contrat_calendrier", 10, 0.5, "type de contrat non précisé")
    elif contract in ("VIE", "graduate"):
        add("Contrat et dates", "contrat_calendrier", 10, 1.0, f"{contract} : pas de contrainte de date")
    elif start and win_start and win_end:
        if win_start <= start <= win_end:
            add("Contrat et dates", "contrat_calendrier", 10, 1.0, "début dans ma fenêtre")
        else:
            add("Contrat et dates", "contrat_calendrier", 10, 0.4, "début proche de ma fenêtre")
    else:
        add("Contrat et dates", "contrat_calendrier", 10, 0.6, "date de début non précisée")

    # 4. Lieu
    favorites = {norm(c) for c in lieux.get("villes_favorites") or []}
    if norm(offer.city) in favorites:
        add("Lieu", "lieu", 10, 1.0, f"ville favorite : {offer.city}")
    elif country_key:
        add("Lieu", "lieu", 10, 0.7, f"pays accepté : {offer.country}")
    else:
        add("Lieu", "lieu", 10, 0.4, "lieu non précisé")

    # 5. Accessibilité (niveau, langues)
    ratio = 1.0
    notes = []
    if exp is not None and exp >= 1:
        ratio *= 0.7
        notes.append(f"{exp} an(s) d'expérience demandé(s)")
    langs = language_requirements(desc_n, cfg)
    if langs:
        ratio *= 0.4
        notes.append("langue exigée : " + ", ".join(langs))
    add("Accessibilité", "accessibilite", 10, ratio, "; ".join(notes) if notes else "rien de bloquant")

    # 6. Fraîcheur
    published = parse_date(offer.published)
    if published:
        age = (today - published).days
        for limit, r in ((3, 1.0), (7, 0.8), (14, 0.6), (30, 0.4), (60, 0.2)):
            if age <= limit:
                add("Fraîcheur", "fraicheur", 10, r, f"publiée il y a {max(age, 0)} j")
                break
        else:
            add("Fraîcheur", "fraicheur", 10, 0.0, f"publiée il y a {age} j")
    else:
        add("Fraîcheur", "fraicheur", 10, 0.4, "date de publication inconnue")

    # 7. Mots bonus
    bonus = find_terms(f"{title_n} {desc_n}", cfg.get("mots_bonus"))
    add("Mots bonus", "mots_bonus", 8, min(len(bonus), 3) / 3,
        ", ".join(bonus[:3]) if bonus else "aucun")

    # 8. Salaire affiché
    add("Salaire affiché", "salaire", 2, 1.0 if str(offer.salary).strip() else 0.0,
        offer.salary if str(offer.salary).strip() else "non indiqué")

    # Pénalité : mots à éviter dans le titre
    pen = find_terms(title_n, cfg.get("penaliser_si_titre_contient"))
    if pen:
        score -= PENALITE_MOTS_A_EVITER
        details.append(f"Pénalité : -{PENALITE_MOTS_A_EVITER} (« {pen[0]} » dans le titre)")

    offer.score = int(round(max(0, min(100, score))))
    offer.score_details = details

    # ---------- BADGES ----------
    badges = [{"stage": "STAGE", "VIE": "VIE", "graduate": "GRADUATE"}.get(contract, "CONTRAT ?")]
    if offer.city and offer.country:
        badges.append(f"{offer.city}, {offer.country}")
    elif offer.country:
        badges.append(offer.country)
    elif offer.location:
        badges.append(offer.location[:40])
    else:
        badges.append("LIEU ?")
    visa_countries = {canon_country(c) for c in lieux.get("pays_avec_badge_visa") or []}
    if country_key and country_key in visa_countries:
        badges.append("VISA")
    if not start:
        badges.append("DATE ?")
    if deadline:
        days_left = (deadline - today).days
        urgent_days = (cfg.get("notifications", {}) or {}).get("alerte_date_limite_jours_avant", 14)
        if days_left <= urgent_days:
            badges.append(f"URGENT : limite dans {days_left} j")
    for lang in langs:
        badges.append(f"LANGUE : {lang}")
    offer.badges = badges
    return None


def process(offers, cfg, today=None):
    """Filtre et note toutes les offres. Renvoie (offres gardées triées, statistiques par source)."""
    today = today or date.today()
    kept, seen, stats = [], set(), {}
    for offer in offers:
        s = stats.setdefault(offer.source or "inconnue", {"trouvees": 0, "gardees": 0, "retirees": {}})
        s["trouvees"] += 1
        key1 = offer.uid
        key2 = norm(f"{offer.title}|{offer.company}|{offer.city or offer.location}")
        if key1 in seen or key2 in seen:
            reason = "doublon"
        else:
            reason = analyse(offer, cfg, today)
        if reason:
            s["retirees"][reason] = s["retirees"].get(reason, 0) + 1
            continue
        seen.add(key1)
        seen.add(key2)
        kept.append(offer)
        s["gardees"] += 1
    kept.sort(key=lambda o: (-o.score, norm(o.company), norm(o.title)))
    return kept, stats
