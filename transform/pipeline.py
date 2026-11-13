"""Rebuild everything after the raw data changes (no API calls; LLM answers are reused):

    uv run python -m transform.pipeline

Order matters: posts -> vacancies -> skills -> duplicates.
New posts that still need LLM extraction or roles: run transform.llm_batch / transform.llm_roles first.
"""
from transform import build_posts, build_skills, build_vacancies, dedup


def main() -> None:
    for step in (build_posts, build_vacancies, build_skills, dedup):
        print(f"\n=== {step.__name__.split('.')[-1]} ===")
        step.main()


if __name__ == "__main__":
    main()
