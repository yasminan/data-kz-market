"""Ask the LLM for the role of vacancies the title rules can't decide (role unknown or
analyst_other), using the full post text. Direct calls in parallel: a few hundred vacancies,
a few cents.

    uv run python -m transform.llm_roles                 # classify everything still open
    uv run python -m transform.llm_roles --evaluate data/samples/roles_test.csv
"""
import argparse
import csv
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import anthropic
import psycopg

from collector.config import DATABASE_URL
from transform.llm_extract import MAX_POST_CHARS, MODEL, PRICE_IN, PRICE_OUT

PROMPT_VERSION = "r1"
ROLES = {
    "data_analyst": "analyses business data: SQL, reports, dashboards, metrics (incl. marketing, web, CRM analysts)",
    "product_analyst": "product metrics, funnels, A/B tests for a digital product",
    "bi": "builds BI reports and models in Power BI, Tableau, Qlik",
    "business_analyst": "gathers business requirements, describes and improves business processes",
    "systems_analyst": "writes technical requirements and specifications for developers (APIs, integrations, data models)",
    "data_engineer": "builds data pipelines, ETL, data warehouses",
    "data_scientist": "builds statistical or machine-learning models for business problems (scoring, forecasting)",
    "ml_engineer": "builds and deploys ML/AI systems (computer vision, NLP, LLMs, MLOps)",
    "finance_analyst": "financial, credit, investment or risk analysis",
    "analyst_other": "another kind of analyst (fraud, compliance, market research, etc.)",
    "software_engineer": "writes software (backend, frontend, mobile, 1C, etc.)",
    "qa": "tests software",
    "devops_infra": "DevOps, system administration, monitoring, networks, IT support, databases",
    "security": "information security",
    "design": "UX/UI, product or graphic design",
    "product_project": "product or project management",
    "other_it": "other IT roles (ERP/1C/SAP consulting, implementation, technical writing)",
    "non_it": "not an IT or analytics job (sales, HR, accounting, marketing, legal, operations, etc.)",
    "unknown": "the post does not say what the job is",
}
SYSTEM = (
    "You classify job vacancies from Kazakhstani Telegram channels into one role. "
    "A post may list several vacancies; classify only the one you are asked about, judging by "
    "what the person will actually do, not by buzzwords. Roles:\n"
    + "\n".join(f"- {r}: {d}" for r, d in ROLES.items())
)
TOOL = {
    "name": "record_role",
    "description": "Record the role of the vacancy.",
    "input_schema": {
        "type": "object",
        "properties": {"role": {"type": "string", "enum": list(ROLES)}},
        "required": ["role"],
    },
}

# The enum in the tool schema is a strong hint, not a guarantee: occasionally the model answers
# with a field name instead ("marketing"). Map those to our roles; anything else becomes unknown.
OFF_LIST = {
    "marketing": "non_it", "sales": "non_it", "hr": "non_it", "human_resources": "non_it",
    "recruiting": "non_it", "accounting": "non_it", "legal": "non_it", "operations": "non_it",
    "customer_service": "non_it", "customer_support": "non_it", "finance": "finance_analyst",
    "data_analysis": "data_analyst", "analyst": "analyst_other", "developer": "software_engineer",
    "project_manager": "product_project", "product_manager": "product_project", "designer": "design",
    "support": "devops_infra", "it_support": "devops_infra",
}


def normalize_role(role: str) -> str:
    role = role.strip().lower()
    return role if role in ROLES else OFF_LIST.get(role, "unknown")


TODO = """
SELECT v.channel_username, v.message_id, v.vacancy_idx, v.title, p.text_clean,
       count(*) OVER (PARTITION BY v.channel_username, v.message_id) AS n_in_post
FROM clean.vacancies v
JOIN clean.posts p USING (channel_username, message_id)
WHERE v.role IN ('unknown', 'analyst_other')
  AND NOT EXISTS (SELECT 1 FROM clean.llm_roles r
                  WHERE r.channel_username = v.channel_username AND r.message_id = v.message_id
                    AND r.vacancy_idx = v.vacancy_idx AND r.prompt_version = %s)
"""
SAVE = """
INSERT INTO clean.llm_roles (channel_username, message_id, vacancy_idx, prompt_version, model,
                             title, role, input_tokens, output_tokens)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (channel_username, message_id, vacancy_idx, prompt_version) DO UPDATE SET
    role = EXCLUDED.role, title = EXCLUDED.title, created_at = now()
"""


def classify(client: anthropic.Anthropic, title: str | None, idx: int, n: int, text: str):
    which = f"vacancy {idx + 1} of {n} in this post" if n > 1 else "the vacancy in this post"
    question = f"Classify {which}. Its title: {title or '(no title)'}"
    response = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": TOOL["name"]},
        messages=[{"role": "user",
                   "content": f"<post>\n{text[:MAX_POST_CHARS]}\n</post>\n\n{question}"}],
    )
    block = next(b for b in response.content if b.type == "tool_use")
    return block.input["role"], response.usage


def run() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        todo = conn.execute(TODO, (PROMPT_VERSION,)).fetchall()
    print(f"{len(todo)} vacancies to classify")
    client = anthropic.Anthropic()

    def work(item):
        channel, message_id, idx, title, text, n = item
        role, usage = classify(client, title, idx, n, text)
        return channel, message_id, idx, title, role, usage

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, todo))

    off_list = Counter(role for *_, role, _ in results if role not in ROLES)
    if off_list:
        print(f"Answers outside the role list (mapped by normalize_role): {dict(off_list)}")
    tokens_in = sum(u.input_tokens for *_, u in results)
    tokens_out = sum(u.output_tokens for *_, u in results)
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        for channel, message_id, idx, title, role, usage in results:
            cur.execute(SAVE, (channel, message_id, idx, PROMPT_VERSION, MODEL, title, role,
                               usage.input_tokens, usage.output_tokens))
        conn.commit()
    cost = tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT
    print(f"Saved {len(results)} roles; {tokens_in:,} input + {tokens_out:,} output tokens, ~${cost:.4f}")
    print("Next: uv run python -m transform.build_vacancies")


def evaluate(path: str) -> None:
    """Compare LLM roles with hand labels, for labeled rows the LLM classified."""
    with open(path, encoding="utf-8") as f:
        labels = {(r["channel_username"], int(r["message_id"]), int(r["vacancy_idx"])): (r["title"], r["label"])
                  for r in csv.DictReader(f) if r["label"]}
    with psycopg.connect(DATABASE_URL) as conn:
        llm = {(c, m, i): role for c, m, i, role in conn.execute(
            "SELECT channel_username, message_id, vacancy_idx, role FROM clean.llm_roles "
            "WHERE prompt_version = %s", (PROMPT_VERSION,))}
    both = [(k, labels[k], llm[k]) for k in labels if k in llm]
    both = [(k, lab, normalize_role(role)) for k, lab, role in both]
    right = sum(label == role for _, (_, label), role in both)
    print(f"LLM role matches the hand label in {right}/{len(both)} labeled vacancies")
    for (c, m, i), (title, label), role in both:
        mark = "ok " if label == role else "-- "
        print(f"  {mark}{c} #{m}: {title[:45]!r}  label={label}  llm={role}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate", help="CSV with hand labels (tools/label_roles.py output)")
    args = parser.parse_args()
    evaluate(args.evaluate) if args.evaluate else run()


if __name__ == "__main__":
    main()
