"""Label job roles by hand in the terminal (for checking the role classifier).

Usage: uv run python tools/label_roles.py data/samples/roles_test.csv

Each row is ONE vacancy (its TITLE). For digest posts with several vacancies, the tool loads the
full post from the database and shows the part around that title, highlighted.
Saves after every answer; q to quit and continue later. To redo a row, clear its label in the CSV.
"""
import csv
import re
import sys

import psycopg

from collector.config import DATABASE_URL

ROLES = [
    "data_analyst", "product_analyst", "bi", "business_analyst", "systems_analyst",
    "data_engineer", "data_scientist", "ml_engineer", "finance_analyst", "analyst_other",
    "software_engineer", "qa", "devops_infra", "security", "design", "product_project",
    "other_it", "non_it", "unknown",
]
MENU = "  ".join(f"{i}={r}" for i, r in enumerate(ROLES, 1))
GUIDE = """
Label the vacancy named in TITLE, not the whole post.
- devops_infra: sysadmins, monitoring, support, networks, DBAs
- other_it: IT roles not in the list (1C/SAP/ERP consultants, implementation, technical writers)
- non_it: everything outside IT, including IT recruiters, IT sales and marketing
- unknown: neither the title nor the text says what the job is
"""
YELLOW, RESET = "\033[1;33m", "\033[0m"


def context(text: str, title: str, width: int = 350) -> str:
    """The part of the post around the title, with the title highlighted."""
    match = re.search(re.escape(title), text, re.IGNORECASE)
    if not match:  # titles are sometimes rephrased: try the longest word instead
        words = sorted(re.findall(r"\w{5,}", title), key=len, reverse=True)
        match = next((m for w in words if (m := re.search(re.escape(w), text, re.IGNORECASE))), None)
    if not match:
        return text[: 2 * width]
    start, end = max(0, match.start() - width), min(len(text), match.end() + width)
    return ("…" if start else "") + text[start:match.start()] + YELLOW + text[match.start():match.end()] \
        + RESET + text[match.end():end] + ("…" if end < len(text) else "")


def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())

    def save() -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    print(GUIDE)
    todo = [r for r in rows if not r["label"]]
    with psycopg.connect(DATABASE_URL) as conn:
        for i, row in enumerate(todo, 1):
            key = (row["channel_username"], int(row["message_id"]))
            text = conn.execute("SELECT text_clean FROM clean.posts WHERE channel_username = %s "
                                "AND message_id = %s", key).fetchone()[0]
            n = conn.execute("SELECT count(*) FROM clean.vacancies WHERE channel_username = %s "
                             "AND message_id = %s", key).fetchone()[0]
            print("=" * 80)
            print(f"[{i}/{len(todo)}]  TITLE: {YELLOW}{row['title']}{RESET}")
            if n > 1:
                print(f"(this post contains {n} vacancies: label only the highlighted one)")
            print("-" * 80)
            print(context(text, row["title"]))
            print("-" * 80)
            print(MENU)
            while True:
                answer = input("role number (s = skip, q = quit): ").strip().lower()
                if answer.isdigit() and 1 <= int(answer) <= len(ROLES):
                    row["label"] = ROLES[int(answer) - 1]
                    save()
                    break
                if answer == "s":
                    break
                if answer == "q":
                    save()
                    return
    save()
    print(f"Done: {sum(bool(r['label']) for r in rows)}/{len(rows)} labeled.")


if __name__ == "__main__":
    main(sys.argv[1])
