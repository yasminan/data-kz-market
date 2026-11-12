"""Label posts by hand in the terminal: is this post a vacancy?

Usage: uv run python tools/label_posts.py data/samples/filter_test.csv
Saves after every answer, so you can quit (q) and continue later.
"""
import csv
import sys

GUIDE = """
Label = 1 (vacancy) if the post offers at least one specific job, internship or trainee position
        that people can apply to: any field, any country, even if it is just a title + link.
Label = 0 for everything else: events, courses, grants, scholarships, hackathons, advice,
        news, channel ads, job SEEKERS ("ищу работу"), thank-you notes.
Keys: 1 = vacancy, 0 = not, s = skip for now, q = save and quit
"""


def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())

    def save() -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    print(GUIDE)
    todo = [r for r in rows if r["label"] == ""]
    for i, row in enumerate(todo, 1):
        print("=" * 80)
        print(f"[{i}/{len(todo)}] {row['channel_username']} #{row['message_id']} ({row['posted']})")
        print("-" * 80)
        print(row["text"][:2500])
        print("-" * 80)
        while True:
            answer = input("vacancy? [1/0/s/q]: ").strip().lower()
            if answer in ("1", "0"):
                row["label"] = answer
                save()
                break
            if answer == "s":
                break
            if answer == "q":
                save()
                print("Saved. Run again to continue.")
                return
    save()
    done = sum(r["label"] != "" for r in rows)
    print(f"Done: {done}/{len(rows)} labeled.")


if __name__ == "__main__":
    main(sys.argv[1])
