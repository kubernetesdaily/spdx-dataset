import csv
import requests
import time

RESULTS_FILENAME = "most-popular-dockerhub-images.csv"
FIELDNAMES = ["image_name", "pull_count", "star_count", "categories"]
TARGET_COUNT = 1000

# Product type filter as exposed on https://hub.docker.com/search (e.g. "image", "extension", "plugin").
PRODUCT_TYPE = "image"

# Category slugs as exposed on https://hub.docker.com/search. Empty list = no category filter.
# Valid slugs: api-management, content-management-system, data-science, databases-and-storage,
# developer-tools, integration-and-delivery, internet-of-things, languages-and-frameworks,
# machine-learning-and-ai, message-queues, monitoring-and-observability, networking,
# operating-systems, security, web-analytics, web-servers
CATEGORIES = [
    "databases-and-storage",
    "languages-and-frameworks",
    "web-servers",
    "operating-systems",
    "developer-tools",
    "message-queues",
    "networking",
    "security",
    "monitoring-and-observability",
    "machine-learning-and-ai",
]

SEARCH_URL = "https://hub.docker.com/api/search/v3/catalog/search"
PAGE_SIZE = 100


def _full_image_name(item):
    """Return a docker-pullable name from a search result item."""
    image_id = item.get("id") or item.get("slug") or item.get("name", "")
    if image_id.startswith("library/"):
        return image_id.split("/", 1)[1]
    return image_id


def _pull_count(item):
    """Pull count is nested under rate_plans[0].repositories[0] as a human string (e.g. "1B+")."""
    for plan in item.get("rate_plans", []) or []:
        for repo in plan.get("repositories", []) or []:
            if "pull_count" in repo:
                return repo["pull_count"]
    return ""


def fetch_category(category, remaining):
    """Fetch up to `remaining` results for a single category (or all if category is None)."""
    collected = []
    offset = 0
    while len(collected) < remaining:
        params = {
            "type": PRODUCT_TYPE,
            "from": offset,
            "size": PAGE_SIZE,
        }
        if category:
            params["categories"] = category

        try:
            response = requests.get(SEARCH_URL, params=params, timeout=30)
        except requests.RequestException as exc:
            print(f"Request error for category={category} offset={offset}: {exc}")
            break

        if response.status_code == 429:
            print("Rate limited. Waiting 5 seconds...")
            time.sleep(5)
            continue
        if not response.ok:
            print(f"Error {response.status_code} for category={category} offset={offset}: {response.text[:200]}")
            break

        data = response.json()
        results = data.get("results") or []
        if not results:
            break

        for item in results:
            name = _full_image_name(item)
            if not name:
                continue
            collected.append({
                "image_name": name,
                "pull_count": _pull_count(item),
                "star_count": item.get("star_count", 0),
                "categories": ";".join(c.get("slug", "") for c in item.get("categories", []) or []),
            })
            if len(collected) >= remaining:
                break

        offset += PAGE_SIZE
        if offset >= data.get("total", 0):
            break
        time.sleep(0.5)

    return collected


def fetch_docker_images():
    print(f"Fetching up to {TARGET_COUNT} Docker Hub images (type={PRODUCT_TYPE}, "
          f"categories={CATEGORIES or 'ALL'})...")

    seen = set()
    collected = []
    categories = CATEGORIES if CATEGORIES else [None]

    for category in categories:
        if len(collected) >= TARGET_COUNT:
            break
        remaining = TARGET_COUNT - len(collected)
        label = category or "ALL"
        print(f"-> category={label} (need {remaining} more)")
        for entry in fetch_category(category, remaining):
            if entry["image_name"] in seen:
                continue
            seen.add(entry["image_name"])
            collected.append(entry)
            if len(collected) >= TARGET_COUNT:
                break
        print(f"   collected total: {len(collected)}/{TARGET_COUNT}")

    return collected[:TARGET_COUNT]


images = fetch_docker_images()

with open(RESULTS_FILENAME, "w", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
    writer.writeheader()
    for entry in images:
        writer.writerow(entry)

print(f"Successfully saved {len(images)} Docker images to '{RESULTS_FILENAME}'.")
