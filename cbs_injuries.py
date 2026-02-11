import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# pd.set_option("display.max_rows", 500)


def scrape_daily_injuries():
    opts = Options()
    opts.add_argument("--headless")

    url = "https://www.cbssports.com/nba/injuries/"

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(options=opts, service=service)
    driver.get(url)

    html = driver.page_source

    soup = BeautifulSoup(html, "html.parser")

    team_injuries = soup.find_all("div", class_="TableBaseWrapper")
    team_data = []
    for team in team_injuries:
        team_name = team.find("div", class_="TeamLogoNameLockup-name").get_text(strip=True)
        players = team.find_all("tr", class_="TableBase-bodyTr")
        for player in players:
            player_td = player.find_all("td", class_="TableBase-bodyTd")
            player_data = {
                "Team": team_name,
                "Name": player.find("span", class_="CellPlayerName--long").get_text(strip=True),
                "Updated": player.find("span", class_="CellGameDate").get_text(strip=True),
                "Injury": player_td[3].get_text(strip=True),
                "Status": player_td[4].get_text(strip=True),
            }
            team_data.append(player_data)
    driver.quit()

    return pd.DataFrame(team_data).sort_values("Team")


df = scrape_daily_injuries()
print(df.to_string(index=False))
# print(df.head(10))
