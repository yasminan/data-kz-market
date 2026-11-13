"""Find skills in every vacancy and store them in clean.vacancy_skills.

Run after transform.build_vacancies (which rebuilds clean.vacancies from scratch).
Single-vacancy posts: skills from the whole post. Digests: only the part of the post between
this vacancy's title and the next one, so skills aren't credited to the wrong vacancy; if the
title can't be found, only the title itself is searched.
"""
from collections import Counter, defaultdict

import psycopg

from collector.config import DATABASE_URL
from transform.skills import find_skills, vacancy_segment

CORE_ROLES = ["data_analyst", "product_analyst", "bi", "business_analyst", "systems_analyst",
              "data_engineer", "data_scientist", "ml_engineer"]


def main() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        vacancies = conn.execute(
            """SELECT v.channel_username, v.message_id, v.vacancy_idx, v.title, v.role,
                      v.role_group, p.text_clean
               FROM clean.vacancies v JOIN clean.posts p USING (channel_username, message_id)
               ORDER BY 1, 2, 3"""
        ).fetchall()

        posts: dict[tuple[str, int], list] = defaultdict(list)
        for v in vacancies:
            posts[(v[0], v[1])].append(v)

        skill_rows, scope_rows = [], []
        scopes, with_skills, totals = Counter(), Counter(), Counter()
        per_role: dict[str, Counter] = defaultdict(Counter)
        for (channel, message_id), items in posts.items():
            titles = [it[3] for it in items]
            for channel, message_id, idx, title, role, group, text in items:
                if len(items) == 1:
                    scope, search = "full_post", f"{title or ''}\n{text}"
                else:
                    segment = vacancy_segment(text, titles, idx)
                    scope, search = ("segment", segment) if segment else ("title_only", title or "")
                found = find_skills(search)
                scopes[scope] += 1
                totals[group] += 1
                with_skills[group] += bool(found)
                per_role[role].update(name for name, _ in found)
                per_role[f"_{role}_n"]["n"] += 1
                scope_rows.append((scope, channel, message_id, idx))
                skill_rows.extend((channel, message_id, idx, name, cat) for name, cat in found)

        conn.execute("DELETE FROM clean.vacancy_skills")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO clean.vacancy_skills VALUES (%s, %s, %s, %s, %s)", skill_rows)
            cur.executemany("UPDATE clean.vacancies SET skills_scope = %s "
                            "WHERE channel_username = %s AND message_id = %s AND vacancy_idx = %s",
                            scope_rows)
        conn.commit()

    print(f"{len(skill_rows):,} skill mentions in {sum(totals.values()):,} vacancies")
    print("Text searched: " + ", ".join(f"{k} {v:,}" for k, v in scopes.most_common()))
    print("Vacancies with at least one skill: " + ", ".join(
        f"{g} {with_skills[g] / totals[g]:.0%}" for g in sorted(totals)))
    for role in CORE_ROLES:
        n = per_role[f"_{role}_n"]["n"]
        if not n:
            continue
        top = ", ".join(f"{s} {c / n:.0%}" for s, c in per_role[role].most_common(10))
        print(f"\n{role} ({n}): {top}")


if __name__ == "__main__":
    main()
