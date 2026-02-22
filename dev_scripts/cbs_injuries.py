import pandas as pd
import requests
from bs4 import BeautifulSoup


def scrape_daily_injuries():
    url = "https://www.cbssports.com/nba/injuries/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    team_injuries = soup.find_all("div", class_="TableBaseWrapper")
    team_data = []
    for team in team_injuries:
        team_name = team.find("div", class_="TeamLogoNameLockup-name").get_text(
            strip=True
        )
        players = team.find_all("tr", class_="TableBase-bodyTr")
        for player in players:
            player_td = player.find_all("td", class_="TableBase-bodyTd")
            player_data = {
                "Team": team_name,
                "Name": player.find("span", class_="CellPlayerName--long").get_text(
                    strip=True
                ),
                "Updated": player.find("span", class_="CellGameDate").get_text(
                    strip=True
                ),
                "Injury": player_td[3].get_text(strip=True),
                "Status": player_td[4].get_text(strip=True),
            }
            team_data.append(player_data)

    return pd.DataFrame(team_data).sort_values("Team")


df = scrape_daily_injuries()
print(df.to_string(index=False))
