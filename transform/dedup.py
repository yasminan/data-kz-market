"""Mark reposted vacancies so each real opening is counted once.

Two postings are the same vacancy when they have the same normalised company and title
(or, without a company or with a generic title like "Intern", also the same start of the post
text), and were posted
within REPOST_WINDOW_DAYS of the previous posting in the chain. A repost after a longer gap
counts as a new hiring round. The earliest posting in each cluster is the primary one.
Run after transform.build_vacancies.
"""
import hashlib
import re
from collections import Counter, defaultdict
from datetime import timedelta

import psycopg

from collector.config import DATABASE_URL
from transform.roles import classify_role

REPOST_WINDOW_DAYS = 90
LEGAL_FORMS = re.compile(
    r"\b(тоо|ао|ооо|ип|нао|ргп|пвх|чк|дб|jsc|llp|llc|ltd|inc|corp|group|груп\w*|bank|банк\w*|"
    r"kazakhstan|казахстан\w*|kz)\b", re.IGNORECASE)


def norm(text: str | None) -> str:
    t = (text or "").lower().replace("ё", "е")
    t = re.sub(r"[«»\"'“”„]", "", t)
    return re.sub(r"[^\w+#]+", " ", t).strip()


def norm_company(company: str | None) -> str:
    return re.sub(r"\s+", " ", LEGAL_FORMS.sub(" ", norm(company))).strip()


def dedup_key(company: str | None, title: str | None, post_text: str) -> str | None:
    t = norm(title)
    if not t:
        return None
    c = norm_company(company)
    c = c.replace(" ", "")  # "Bank Center Credit" and "Bank CenterCredit" are the same company
    generic = classify_role(title)[0] == "unknown"  # "Intern", "Стажер": a company can have many
    if c and not generic:
        basis = f"c:{c}|t:{t}"
    else:
        basis = f"c:{c}|t:{t}|x:{norm(post_text)[:200]}"
    return hashlib.md5(basis.encode()).hexdigest()[:12]


def main() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """SELECT v.channel_username, v.message_id, v.vacancy_idx, v.posted_at, v.company,
                      v.title, p.text_clean
               FROM clean.vacancies v JOIN clean.posts p USING (channel_username, message_id)
               ORDER BY v.posted_at, v.channel_username, v.message_id, v.vacancy_idx"""
        ).fetchall()

        groups: dict[str, list] = defaultdict(list)
        updates = []
        for channel, message_id, idx, posted_at, company, title, text in rows:
            key = dedup_key(company, title, text)
            if key is None:  # no title: can't match it to anything, keep as its own vacancy
                updates.append((f"single-{channel}-{message_id}-{idx}", True, channel, message_id, idx))
                continue
            groups[key].append((posted_at, channel, message_id, idx))

        clusters = 0
        cross_channel = 0
        dupes_by_channel = Counter()
        for key, postings in groups.items():
            cluster, last_date, n = None, None, 0
            members: list[list] = []
            for posted_at, channel, message_id, idx in postings:  # already sorted by date
                if last_date is None or posted_at - last_date > timedelta(days=REPOST_WINDOW_DAYS):
                    n += 1
                    cluster = f"{key}-{n}"
                    members.append([])
                members[-1].append((cluster, channel, message_id, idx))
                last_date = posted_at
            for member_list in members:
                clusters += 1
                channels = {m[1] for m in member_list}
                cross_channel += len(channels) > 1
                for i, (cluster, channel, message_id, idx) in enumerate(member_list):
                    updates.append((cluster, i == 0, channel, message_id, idx))
                    if i > 0:
                        dupes_by_channel[channel] += 1

        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE clean.vacancies SET cluster_id = %s, is_primary = %s "
                "WHERE channel_username = %s AND message_id = %s AND vacancy_idx = %s", updates)
        conn.commit()

    total = len(rows)
    primary = sum(1 for u in updates if u[1])
    print(f"{total:,} vacancy postings -> {primary:,} unique vacancies "
          f"({total - primary:,} reposts, {(total - primary) / total:.1%})")
    print(f"Clusters posted in more than one channel: {cross_channel:,}")
    print("Reposts by channel: " + ", ".join(f"{c} {n:,}" for c, n in dupes_by_channel.most_common()))


if __name__ == "__main__":
    main()
