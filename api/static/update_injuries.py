import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

CBS_INJURIES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "cbs_injuries.json"
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def scrape_cbs_injuries():
    """Scrape CBS Sports and save to JSON file"""
    url = "https://www.cbssports.com/nba/injuries/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    response = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            break
        except requests.RequestException as e:
            logger.warning(
                "CBS injuries request failed (attempt %d/%d): %s",
                attempt + 1,
                MAX_RETRIES,
                e,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                logger.error("All %d CBS injuries request attempts failed", MAX_RETRIES)
                raise

    soup = BeautifulSoup(response.text, "lxml")
    team_sections = soup.find_all("div", class_="TableBaseWrapper")

    if not team_sections:
        raise RuntimeError(
            "No team sections found — CBS HTML structure may have changed"
        )

    injuries_by_team = []

    for team_section in team_sections:
        team_name_el = team_section.find("div", class_="TeamLogoNameLockup-name")
        if not team_name_el:
            logger.warning("Missing team name element in section, skipping")
            continue

        team_name = team_name_el.get_text(strip=True)
        players = []

        rows = team_section.find_all("tr", class_="TableBase-bodyTr")
        for row in rows:
            cells = row.find_all("td", class_="TableBase-bodyTd")
            name_el = row.find("span", class_="CellPlayerName--long")
            date_el = row.find("span", class_="CellGameDate")

            if name_el and len(cells) >= 5:
                players.append(
                    {
                        "name": name_el.get_text(strip=True),
                        "updated": date_el.get_text(strip=True) if date_el else "",
                        "injury": (
                            cells[3].get_text(strip=True) if len(cells) > 3 else ""
                        ),
                        "status": (
                            cells[4].get_text(strip=True) if len(cells) > 4 else ""
                        ),
                    }
                )

        if players:
            injuries_by_team.append({"team": team_name, "players": players})

    if not injuries_by_team:
        raise RuntimeError(
            "Parsed 0 teams with injuries — CBS HTML structure may have changed"
        )

    result = {
        "injuries": injuries_by_team,
        "source": "CBS Sports",
        "lastUpdated": datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC"),
    }
    dir_name = os.path.dirname(CBS_INJURIES_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CBS_INJURIES_FILE)
    except BaseException:
        os.unlink(tmp_path)
        raise

    logger.info("Updated CBS injuries: %d teams", len(injuries_by_team))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scrape_cbs_injuries()
