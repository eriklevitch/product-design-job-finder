"""Question-and-answer setup. Double-click "Set Up.command" to run it.

Creates (or updates) your settings in config.yaml, your keys in .env and
a starter portfolio_notes.md. Safe to run again any time: your current
answers are shown as defaults, so pressing Return keeps them.
"""
import json
import re
import shutil
import subprocess
import sys

import yaml

from settings import CONFIG_PATH, ROOT, env, load_env, save_env

EXAMPLE_CONFIG = ROOT / "config.example.yaml"
NOTES = ROOT / "portfolio_notes.md"
NOTES_EXAMPLE = ROOT / "portfolio_notes.example.md"

IC_LEVELS = ["senior", "sr.", "sr ", "staff", "principal", "lead", "founding"]
LEAD_LEVELS = ["manager", "director", "head of", "vp"]
LEVEL_CHOICES = [
    ("Senior and above (Senior, Staff, Principal, Lead)", IC_LEVELS),
    ("Leadership (Manager, Director, Head of Design, VP)", LEAD_LEVELS),
    ("Both of the above", IC_LEVELS + LEAD_LEVELS),
    ("Any level", []),
]


# ── Small input helpers ─────────────────────────────────────────────

def say(text: str = "") -> None:
    print(text)


def ask(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{hint}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def ask_yes(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        answer = ask(f"{question} ({hint})").lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        say("  Please type y or n.")


def ask_choice(question: str, options: list[str], default: int = 1) -> int:
    say(question)
    for i, label in enumerate(options, 1):
        say(f"  {i}. {label}")
    while True:
        answer = ask("Type a number", str(default))
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer)
        say(f"  Please type a number from 1 to {len(options)}.")


def heading(text: str) -> None:
    say()
    say(f"── {text} " + "─" * max(0, 56 - len(text)))


def parse_money(text: str) -> int | None:
    """'150k', '$150,000' and '150000' all become 150000."""
    t = text.lower().replace("$", "").replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(k?)", t)
    if not m:
        return None
    value = float(m.group(1)) * (1000 if m.group(2) else 1)
    return int(value)


def split_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


# ── Writing config.yaml ─────────────────────────────────────────────

def set_key(text: str, key: str, value) -> str:
    """Replaces a top-level `key: ...` line (and any indented list lines
    under it) with `key: <value>`, keeping every comment and other
    setting in the file. Adds the key if it isn't there."""
    rendered = f"{key}: {json.dumps(value, ensure_ascii=False)}"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}\s*:", line):
            end = i + 1
            while end < len(lines) and lines[end].startswith((" ", "\t")):
                end += 1
            return "\n".join(lines[:i] + [rendered] + lines[end:]) + "\n"
    marker = "# ════ ADVANCED"
    for i, line in enumerate(lines):
        if line.startswith(marker):
            return "\n".join(lines[:i] + [rendered, ""] + lines[i:]) + "\n"
    return text.rstrip("\n") + "\n" + rendered + "\n"


def current_settings() -> dict:
    if CONFIG_PATH.exists():
        return yaml.safe_load(CONFIG_PATH.read_text()) or {}
    return yaml.safe_load(EXAMPLE_CONFIG.read_text()) or {}


# ── Questions ───────────────────────────────────────────────────────

def ask_level(cfg: dict) -> tuple[list[str], str]:
    heading("1 of 5 · Level")
    current = cfg.get("seniority_keywords")
    default = 3
    for i, (_, levels) in enumerate(LEVEL_CHOICES, 1):
        if current is not None and sorted(current) == sorted(levels):
            default = i
    n = ask_choice("Which roles should it look for?", [c[0] for c in LEVEL_CHOICES], default)
    role_default = (CONFIG_PATH.exists() and cfg.get("your_role")) or {
        1: "senior product designer", 2: "design leader",
        3: "senior product designer", 4: "product designer"}[n]
    role = ask("In a few words, how should drafts describe you?", role_default)
    return LEVEL_CHOICES[n - 1][1], role


def ask_location(cfg: dict) -> tuple[list[str], str]:
    heading("2 of 5 · Location")
    locations = [l for l in (cfg.get("locations") or [])]
    cities_now = ", ".join(l for l in locations if l != "remote")
    say("Type the cities or areas that work for you, separated by commas,")
    say("as they'd appear in a job listing (e.g. New York, Brooklyn).")
    cities = split_list(ask("Cities (press Return for none)", cities_now))
    remote = ask_yes("Include remote jobs in the US?", "remote" in locations or not locations)
    new_locations = [c.lower() for c in cities] + (["remote"] if remote else [])
    if not new_locations:
        say("  No cities and no remote: jobs from anywhere will count.")
    search_location = cities[0] if cities else "United States"
    return new_locations, search_location


def ask_salary(cfg: dict) -> int:
    heading("3 of 5 · Pay")
    say("Jobs whose posted pay tops out below this are skipped. Jobs that")
    say("don't list pay are always kept, so you can check them yourself.")
    current = cfg.get("min_salary") or 0
    while True:
        answer = ask("Minimum yearly pay in US dollars, e.g. 150k (0 for none)",
                     f"{current // 1000}k" if current else "0")
        value = parse_money(answer)
        if value is not None:
            return value
        say("  Please type a number like 150k or 150000.")


def ask_companies(cfg: dict) -> dict:
    heading("4 of 5 · Companies")
    lists = {k: list(cfg.get(k) or []) for k in
             ("greenhouse_companies", "lever_companies", "ashby_companies")}
    total = sum(len(v) for v in lists.values())
    say("Name companies you'd love to work at and it will check their")
    say("careers pages directly, every run. Indeed is searched either way.")
    if total:
        say(f"You're checking {total} companies now. Names you add here are added to that list.")
    names = split_list(ask("Company names, separated by commas (Return to skip)"))
    if not names:
        return lists
    from check_boards import resolve
    say("Looking them up...")
    key_for = {"greenhouse": "greenhouse_companies", "lever": "lever_companies",
               "ashby": "ashby_companies"}
    not_found = []
    for name in names:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        # resolve() checks Greenhouse, then Lever and Ashby, plus common
        # name variations ("acme" -> "acmehq", "acmeai"...).
        r = resolve("greenhouse", slug)
        if r["status"] in ("ok", "moved"):
            target = key_for[r["ats"]]
            if r["slug"] not in lists[target]:
                lists[target].append(r["slug"])
            say(f"  ✓ {name}: found ({r.get('jobs', 0)} open jobs)")
        elif r["status"] == "error":
            not_found.append(name)
            say(f"  ? {name}: couldn't check right now (internet hiccup). Try again later.")
        else:
            not_found.append(name)
            say(f"  ✗ {name}: not found")
    if not_found:
        say("Companies not found use a different careers system. Indeed may still")
        say("list their jobs. The README explains how to add one by hand.")
    return lists


def ask_addons(cfg: dict) -> str:
    heading("5 of 5 · Optional extras (press Return to skip any of them)")

    # Drafts
    has_key = bool(env("ANTHROPIC_API_KEY"))
    say("Tailored drafts: for every new job, write 3 resume bullets and a")
    say("cover letter opening from your own notes. Needs an Anthropic API key")
    say("(about 1-2 cents per job). Get one at https://console.anthropic.com")
    say("→ API Keys → Create Key.")
    if has_key:
        say("  Your key is already saved.")
    key = ask("Paste your Anthropic key (Return to " + ("keep it)" if has_key else "skip)"))
    if key:
        if not key.startswith("sk-ant-"):
            say("  That doesn't look like an Anthropic key (they start with sk-ant-). Skipped.")
        else:
            save_env({"ANTHROPIC_API_KEY": key})
            say("  Saved.")

    # Adzuna
    say()
    say("More listings: Adzuna is a free job search service. Sign up at")
    say("https://developer.adzuna.com to get an App ID and App Key.")
    if env("ADZUNA_APP_ID"):
        say("  Your Adzuna keys are already saved.")
    app_id = ask("Adzuna App ID (Return to skip)")
    if app_id:
        app_key = ask("Adzuna App Key")
        if app_key:
            save_env({"ADZUNA_APP_ID": app_id, "ADZUNA_APP_KEY": app_key})
            say("  Saved.")

    # Tracker
    say()
    current = (cfg.get("tracker") or "spreadsheet").lower()
    n = ask_choice("Where should new jobs go?", [
        "A spreadsheet in this folder (applications.csv). Nothing to set up.",
        "Notion (needs a free Notion account and about 3 minutes)",
    ], 2 if current == "notion" else 1)
    if n == 1:
        return "spreadsheet"
    if env("NOTION_TOKEN") and env("NOTION_DATABASE_ID"):
        if not ask_yes("Notion is already connected. Set it up again?", False):
            return "notion"
    return "notion" if setup_notion() else "spreadsheet"


def setup_notion() -> bool:
    from notion_client import create_database, page_id_from_link
    say()
    say("Three steps in Notion:")
    say("  1. Go to https://www.notion.so/profile/integrations, click 'New integration',")
    say("     name it 'Job search', save, and copy the 'Internal Integration Secret'.")
    say("  2. Open (or create) the Notion page the tracker should live in.")
    say("     Click ••• (top right) → Connections → add 'Job search'.")
    say("  3. On that page, click Share → Copy link.")
    token = ask("Paste the Integration Secret (step 1)")
    link = ask("Paste the page link (step 3)")
    page_id = page_id_from_link(link)
    if not token or not page_id:
        say("  Missing the secret or a valid page link. Using the spreadsheet for now;")
        say("  run Set Up again any time to connect Notion.")
        return False
    try:
        db = create_database(token, page_id)
    except Exception as e:
        say(f"  Notion said: {e}")
        say("  Most often this means step 2 was skipped. Using the spreadsheet for now;")
        say("  run Set Up again to retry.")
        return False
    save_env({"NOTION_TOKEN": token, "NOTION_DATABASE_ID": db["id"]})
    say(f"  ✓ Created a 'Job applications' database: {db['url']}")
    return True


# ── Main ────────────────────────────────────────────────────────────

def main() -> int:
    load_env()
    first_time = not CONFIG_PATH.exists()
    say("Job search setup")
    say("Five short questions. Press Return to accept the answer in [brackets].")
    if not first_time:
        say("Your current settings are shown as the defaults.")

    cfg = current_settings()
    seniority, role = ask_level(cfg)
    locations, search_location = ask_location(cfg)
    min_salary = ask_salary(cfg)
    companies = ask_companies(cfg)
    tracker = ask_addons(cfg)

    text = CONFIG_PATH.read_text() if CONFIG_PATH.exists() else EXAMPLE_CONFIG.read_text()
    for key, value in [
        ("seniority_keywords", seniority), ("your_role", role),
        ("locations", locations), ("search_location", search_location),
        ("min_salary", min_salary), ("tracker", tracker), *companies.items(),
    ]:
        text = set_key(text, key, value)
    yaml.safe_load(text)  # never write a file that can't be read back
    CONFIG_PATH.write_text(text)

    if not NOTES.exists():
        shutil.copy(NOTES_EXAMPLE, NOTES)

    heading("All set")
    say("Saved your settings to config.yaml.")
    if env("ANTHROPIC_API_KEY"):
        say("For good drafts, add your experience to portfolio_notes.md in this")
        say("folder (right-click it → Open With → TextEdit).")
    say()
    say("Every week: double-click 'Find Jobs', then 'Open Tracker'.")
    if ask_yes("\nRun your first search now?", True):
        say()
        python = sys.executable
        subprocess.run([python, str(ROOT / "engine" / "main.py")], cwd=ROOT, check=False)
        subprocess.run([python, str(ROOT / "engine" / "open_tracker.py")], cwd=ROOT, check=False)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nSetup stopped. Your settings weren't changed. Run it again any time.")
        sys.exit(1)
