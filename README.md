# nba_stables

NBA Live Stats in Tables

I have a strange habit to listen to NBA live streams on nba.com while doing something else on my laptop. In order to
stay updated with latest results I have to click through all active games in order to check the stats and usually get
lost in sudden burst of numbers and stats. So I decided to make custom NBA Live Stats scripts to get the preferred stats
with only one click (one script execution). This repository is a collection of such live stats scripts all resulting in
drawing a table in terminal with most interesting stats for that evening.

Install required packages with pip:

```
pip install nba_api tabulate2
```

There is an updated players static list with teamID added to each player that has played at least one game this season (
other will have teamID 0). 