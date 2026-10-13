"""main.py : lance toutes les sources, filtre, note, génère la page et prépare les alertes.

Commande de lancement (depuis la racine du dépôt) :  python -m jobfinder.main
"""
import importlib
import os
import pkgutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

import jobfinder.sources as sources_pkg
from jobfinder import matching, report, storage

CONFIG_PATH = "config.yaml"
SEEN_PATH = "seen_offers.json"
PAGE_PATH = "docs/index.html"
ALERT_DIR = "alerts"
MAX_PER_SECTION = 15
MIN_SCORE_SECONDARY = 50   # score minimum pour le récapitulatif et les dates limites

WEEKDAYS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
            "vendredi": 4, "samedi": 5, "dimanche": 6}


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_sources(cfg):
    """Lance chaque source activée. Une source en panne ne bloque jamais les autres."""
    offers, names, errors = [], [], {}
    enabled = cfg.get("sources") or {}
    for info in sorted(pkgutil.iter_modules(sources_pkg.__path__), key=lambda i: i.name):
        name = info.name
        try:
            module = importlib.import_module(f"jobfinder.sources.{name}")
        except Exception as exc:  # fichier source cassé
            names.append(name)
            errors[name] = f"Erreur de chargement : {str(exc)[:150]}"
            continue
        name = getattr(module, "NAME", name)
        if not enabled.get(name, True):
            print(f"[{name}] désactivée dans config.yaml")
            continue
        names.append(name)
        try:
            found = list(module.fetch(cfg) or [])
        except Exception as exc:
            errors[name] = f"{type(exc).__name__} : {str(exc)[:150]}"
            found = []
        for offer in found:
            offer.source = offer.source or name
        print(f"[{name}] {len(found)} offre(s)" + (f" — ERREUR : {errors[name]}" if name in errors else ""))
        offers.extend(found)
    return offers, names, errors


def _line(o, extra=""):
    where = ", ".join(x for x in (o.city, o.country) if x) or o.location or "lieu non précisé"
    link = f"[Voir l'offre]({o.url})" if o.url else "lien non disponible"
    return (f"- **{o.title}** · {o.company} · {where} · {o.contract or 'contrat non précisé'} "
            f"· début : {o.start_date or 'non précisé'} · salaire : {o.salary or 'non précisé'} "
            f"· score {o.score}/100{extra} · {link}")


def _section(title, offers, extra_fn=None):
    lines = [f"## {title}", ""]
    for o in offers[:MAX_PER_SECTION]:
        lines.append(_line(o, extra_fn(o) if extra_fn else ""))
    if len(offers) > MAX_PER_SECTION:
        lines.append(f"- … et {len(offers) - MAX_PER_SECTION} autre(s) à voir sur le dashboard.")
    return "\n".join(lines)


def build_alerts(kept, new_offers, seen, cfg, today):
    """Prépare le texte de l'issue GitHub (donc de l'e-mail). Renvoie (titre, corps) ou None."""
    notif = cfg.get("notifications") or {}
    threshold = notif.get("alerte_immediate_si_score_superieur_a", 80)
    days_before = notif.get("alerte_date_limite_jours_avant", 14)
    sections, total = [], 0

    # 1. Nouvelles offres très pertinentes (alerte immédiate)
    immediate = sorted([o for o in new_offers if o.score >= threshold], key=lambda o: -o.score)
    for o in immediate:
        seen[o.uid]["alerted"] = True
    if immediate:
        sections.append(_section("🔥 Nouvelles offres très pertinentes", immediate))
        total += len(immediate)

    # 2. Dates limites qui approchent (une seule alerte par offre)
    deadline_offers = []
    for o in kept:
        d = matching.parse_date(o.deadline)
        entry = seen[o.uid]
        if d and 0 <= (d - today).days <= days_before and o.score >= MIN_SCORE_SECONDARY \
                and not entry.get("deadline_alerted"):
            deadline_offers.append(o)
            entry["deadline_alerted"] = True
    deadline_offers.sort(key=lambda o: o.deadline)
    manual_lines = []
    for item in cfg.get("dates_limites_manuelles") or []:
        d = matching.parse_date(item.get("date_limite"))
        key = f"manuel|{item.get('entreprise')}|{item.get('poste')}|{item.get('date_limite')}"
        if d and 0 <= (d - today).days <= days_before and not seen.get(key, {}).get("deadline_alerted"):
            manual_lines.append(f"- **{item.get('entreprise')}** · {item.get('poste')} · "
                                f"**date limite : {item.get('date_limite')}** (dans {(d - today).days} j)")
            seen[key] = {"deadline_alerted": True}
    if deadline_offers or manual_lines:
        block = _section("⏰ Dates limites qui approchent", deadline_offers,
                         lambda o: f" · **date limite : {o.deadline}**") if deadline_offers else "## ⏰ Dates limites qui approchent\n"
        if manual_lines:
            block += "\n" + "\n".join(manual_lines)
        sections.append(block)
        total += len(deadline_offers) + len(manual_lines)

    # 3. Récapitulatif hebdomadaire
    weekday = WEEKDAYS.get(matching.norm(notif.get("jour_du_recapitulatif", "lundi")), 0)
    if notif.get("recapitulatif_hebdomadaire", True) and today.weekday() == weekday:
        cutoff = today - timedelta(days=7)
        digest = []
        for o in kept:
            entry = seen[o.uid]
            first = matching.parse_date(entry.get("first_seen"))
            if first and first >= cutoff and o.score >= MIN_SCORE_SECONDARY and not entry.get("alerted"):
                digest.append(o)
        digest.sort(key=lambda o: -o.score)
        if digest:
            sections.append(_section("📋 Récapitulatif de la semaine", digest))
            total += len(digest)

    if not sections:
        return None
    title = f"🔔 Dashboard d'offres : {total} élément(s) à voir – {today.strftime('%d/%m/%Y')}"
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    header = ""
    if "/" in repo:
        owner, name = repo.split("/", 1)
        header = f"Ouvre ton dashboard : https://{owner}.github.io/{name}/\n\n"
    return title, header + "\n\n".join(sections) + "\n"


def main():
    cfg = load_config()
    tz = ZoneInfo(cfg.get("fuseau_horaire", "Europe/Paris"))
    today = datetime.now(tz).date()

    all_offers, source_names, errors = run_sources(cfg)
    kept, stats = matching.process(all_offers, cfg, today)

    # Les sources à 0 offre ou en erreur doivent apparaître dans l'onglet « Sources »
    for name in source_names:
        stats.setdefault(name, {"trouvees": 0, "gardees": 0, "retirees": {}})
    for name, err in errors.items():
        stats[name]["erreur"] = err

    seen = storage.load_seen(SEEN_PATH)
    new_offers = storage.update_seen(kept, seen, today)
    alerts = build_alerts(kept, new_offers, seen, cfg, today)
    storage.save_seen(seen, SEEN_PATH)

    report.generate(kept, stats, matching.REASON_LABELS, cfg.get("fuseau_horaire", "Europe/Paris"), PAGE_PATH)

    if alerts:
        os.makedirs(ALERT_DIR, exist_ok=True)
        with open(f"{ALERT_DIR}/issue_title.txt", "w", encoding="utf-8") as f:
            f.write(alerts[0])
        with open(f"{ALERT_DIR}/issue_body.md", "w", encoding="utf-8") as f:
            f.write(alerts[1])

    print(f"Terminé : {len(all_offers)} offre(s) trouvée(s), {len(kept)} gardée(s), "
          f"{len(new_offers)} nouvelle(s), alerte : {'oui' if alerts else 'non'}.")


if __name__ == "__main__":
    main()
