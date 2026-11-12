"""Evaluate the vacancy filter on a hand-labeled sample stratified by channel and prediction.

The sample has equal numbers of accepted and rejected posts per channel, so results are
weighted by each stratum's real size in clean.posts. Run this right after exporting the
sample, before changing the rules, so the database counts match the 'predicted' column.

Usage: uv run python -m tools.evaluate_filter data/samples/filter_test2.csv
"""
import csv
import sys
from collections import defaultdict

import psycopg

from collector.config import DATABASE_URL


def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["label"] in ("0", "1")]

    with psycopg.connect(DATABASE_URL) as conn:
        sizes = {
            (channel, candidate): n
            for channel, candidate, n in conn.execute(
                "SELECT channel_username, is_vacancy_candidate, COUNT(*) FROM clean.posts GROUP BY 1, 2"
            )
        }

    cells = defaultdict(lambda: [0, 0])  # (channel, predicted) -> [labeled posts, real vacancies]
    errors = []
    for r in rows:
        predicted = r["predicted"].lower() in ("t", "true", "1")
        label = r["label"] == "1"
        cells[(r["channel_username"], predicted)][0] += 1
        cells[(r["channel_username"], predicted)][1] += label
        if predicted != label:
            errors.append(("FP" if predicted else "FN", r))

    total_tp = total_fp = total_fn = 0.0
    print(f"{'channel':<17} {'precision':>9} {'recall':>7}   sample: accepted / rejected (real vacancies)")
    for channel in sorted({c for c, _ in cells}):
        n_acc, vac_acc = cells[(channel, True)]
        n_rej, vac_rej = cells[(channel, False)]
        accepted = sizes.get((channel, True), 0)
        rejected = sizes.get((channel, False), 0)
        precision = vac_acc / n_acc if n_acc else float("nan")
        missed_rate = vac_rej / n_rej if n_rej else 0.0
        tp = accepted * precision
        fp = accepted - tp
        fn = rejected * missed_rate
        recall = tp / (tp + fn) if tp + fn else float("nan")
        total_tp, total_fp, total_fn = total_tp + tp, total_fp + fp, total_fn + fn
        print(f"{channel:<17} {precision:>9.0%} {recall:>7.0%}   {vac_acc}/{n_acc} and {vac_rej}/{n_rej}")

    precision = total_tp / (total_tp + total_fp)
    recall = total_tp / (total_tp + total_fn)
    f1 = 2 * precision * recall / (precision + recall)
    print(f"\nOVERALL (weighted): precision {precision:.1%}, recall {recall:.1%}, F1 {f1:.1%}")
    print(f"Estimated real vacancies in the database: {total_tp + total_fn:,.0f}")
    print(f"Note: {len(rows)} labeled posts; per-channel figures rest on ~8 posts each, so treat them as rough.")

    print(f"\nErrors ({len(errors)}):")
    for kind, r in errors:
        text = r["text"][:110].replace("\n", " | ")
        print(f"  {kind} {r['channel_username']} #{r['message_id']} [{r['filter_reasons']}] {text}")


if __name__ == "__main__":
    main(sys.argv[1])
