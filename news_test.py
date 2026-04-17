import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("NEWS_API_KEY")
base_url = os.getenv("NEWS_BASE_URL", "https://api.marketaux.com/v1/news/all")
country = os.getenv("NEWS_COUNTRY", "in")
language = os.getenv("NEWS_LANGUAGE", "en")
search = os.getenv("NEWS_SEARCH", "nifty OR sensex OR stocks OR trading OR RBI")
symbols = os.getenv("NEWS_SYMBOLS", "")
limit = os.getenv("NEWS_LIMIT", "10")

if not api_key:
    raise ValueError("NEWS_API_KEY is missing in .env")

params = {
    "api_token": api_key,
    "countries": country,
    "language": language,
    "search": search,
    "limit": limit,
}

if symbols:
    params["symbols"] = symbols

print("Request URL:", base_url)
print("Params:", params)

try:
    response = requests.get(base_url, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()

    articles = data.get("data", [])
    print("Status Code:", response.status_code)

    if not articles:
        print("No articles found.")
    else:
        print(f"Found {len(articles)} articles\n")
        for i, article in enumerate(articles[:5], 1):
            print(f"{i}. {article.get('title')}")
            print("   Source:", article.get("source"))
            print("   URL:", article.get("url"))
            print("   Published:", article.get("published_at"))
            print()

except requests.exceptions.RequestException as e:
    print("Request failed:", e)
