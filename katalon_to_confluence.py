import os
import time
import requests

from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

CONFLUENCE_URL = os.getenv("CONFLUENCE_URL", "").rstrip("/")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")

SPACE_KEY = "TRUETEST"
URL_FILE = "urls.txt"

# --------------------------------------------------
# CATEGORY MAPPING
# --------------------------------------------------

ROOT_SECTIONS = {
    "/about-": "About",
    "/get-started/": "User Guides",
    "/administer/": "Administration",
    "/plan/": "Plans",
    "/create-tests/": "Tests",
    "/execute/": "Executions",
    "/analytics/": "Analytics",
    "/analyze/": "Analytics",
    "/integrations/": "Integrations",
    "/troubleshooting/": "Troubleshooting",
    "/project-settings/": "Project Settings",
}

# --------------------------------------------------
# CONFLUENCE HELPERS
# --------------------------------------------------

def find_page(title):

    try:

        response = requests.get(
            f"{CONFLUENCE_URL}/rest/api/content",
            auth=(
                CONFLUENCE_USERNAME,
                CONFLUENCE_API_TOKEN
            ),
            params={
                "spaceKey": SPACE_KEY,
                "title": title
            }
        )

        if response.status_code != 200:
            return None

        data = response.json()

        results = data.get(
            "results",
            []
        )

        if results:
            return results[0]["id"]

        return None

    except Exception:
        return None


def create_page(
    title,
    content="",
    parent_id=None
):

    existing_id = find_page(title)

    if existing_id:

        print(
            f"⏭ Already exists: {title}"
        )

        return existing_id

    payload = {
        "type": "page",
        "title": title,
        "space": {
            "key": SPACE_KEY
        },
        "body": {
            "storage": {
                "value": content,
                "representation": "storage"
            }
        }
    }

    if parent_id:

        payload["ancestors"] = [
            {
                "id": parent_id
            }
        ]

    for attempt in range(3):

        try:

            response = requests.post(
                f"{CONFLUENCE_URL}/rest/api/content",
                auth=(
                    CONFLUENCE_USERNAME,
                    CONFLUENCE_API_TOKEN
                ),
                headers={
                    "Content-Type":
                    "application/json"
                },
                json=payload,
                timeout=30
            )

            if response.status_code in [200, 201]:

                page_id = (
                    response
                    .json()
                    .get("id")
                )

                print(
                    f"✅ Created: {title}"
                )

                return page_id

            print(
                f"⚠ Attempt {attempt+1} failed "
                f"for {title}"
            )

            print(response.status_code)

        except Exception as e:

            print(
                f"⚠ Retry {attempt+1}"
            )

            print(str(e))

        time.sleep(2)

    print(
        f"❌ Failed to create page: {title}"
    )

    return None


# --------------------------------------------------
# URL CATEGORIZATION
# --------------------------------------------------

def determine_category(url):

    for key, value in ROOT_SECTIONS.items():

        if key in url:

            return value

    return "Misc"


# --------------------------------------------------
# DOWNLOAD PAGE
# --------------------------------------------------

def extract_page(url):

    print(
        f"\n📥 Downloading:"
    )

    print(url)

    response = requests.get(
        url,
        headers={
            "User-Agent":
            "Mozilla/5.0"
        },
        timeout=60
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = None

    if soup.title:

        title = (
            soup.title.text
            .replace(
                "| Katalon Docs",
                ""
            )
            .strip()
        )

    selectors = [
        "main",
        "article",
        '[role="main"]',
        ".theme-doc-markdown",
        ".markdown"
    ]

    content = None

    for selector in selectors:

        found = soup.select_one(
            selector
        )

        if found:

            content = found

            break

    if not content:

        content = soup.body

    return (
        title,
        str(content)
    )


# --------------------------------------------------
# IMPORT PAGE
# --------------------------------------------------

def process_url(url):

    try:

        title, html = extract_page(url)

        if not title:

            title = (
                url
                .split("/")[-1]
            )

        category = determine_category(
            url
        )

        print(
            f"📂 Category: {category}"
        )

        category_id = create_page(
            category,
            f"<h1>{category}</h1>"
        )

        if not category_id:

            print(
                f"❌ Cannot create category {category}"
            )

            return

        create_page(
            title=title,
            content=html,
            parent_id=category_id
        )

    except Exception as e:

        print(
            f"❌ Error processing URL:"
        )

        print(url)

        print(str(e))


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    if not os.path.exists(
        URL_FILE
    ):

        print(
            "❌ urls.txt not found"
        )

        return

    with open(
        URL_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        urls = list(
            dict.fromkeys(
                [
                    line.strip()
                    for line in f
                    if line.strip()
                ]
            )
        )

    print(
        "=" * 60
    )

    print(
        f"Found {len(urls)} unique URLs"
    )

    print(
        "=" * 60
    )

    for index, url in enumerate(
        urls,
        start=1
    ):

        print(
            f"\n[{index}/{len(urls)}]"
        )

        process_url(url)

    print(
        "\n🎉 Migration Complete"
    )


if __name__ == "__main__":
    main()