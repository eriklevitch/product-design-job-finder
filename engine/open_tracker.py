"""Opens your tracker: the spreadsheet, or Notion in your browser.
Double-click "Open Tracker.command" to run it."""
import subprocess
import sys
import webbrowser

from settings import env, load_config, load_env, resolve_path


def open_file(path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform.startswith("win"):
        import os
        os.startfile(str(path))  # noqa: only exists on Windows
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    load_env()
    config = load_config()
    if (config.get("tracker") or "spreadsheet").lower() == "notion":
        db = env((config.get("notion") or {}).get("database_id_env", "NOTION_DATABASE_ID"))
        if db:
            webbrowser.open(f"https://www.notion.so/{db.replace('-', '')}")
            print("Opened your Notion tracker in the browser.")
            return 0
        print("Notion isn't set up yet, so opening the spreadsheet instead.")
    path = resolve_path(config.get("spreadsheet_path", "applications.csv"))
    if not path.exists():
        print("No jobs saved yet. Double-click 'Find Jobs.command' first.")
        return 1
    open_file(path)
    print(f"Opened {path.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
