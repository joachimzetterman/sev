"""Per-eval metrics with explicit abstentions, denominators and uncertainty classes."""

import math
from collections import Counter

from .contracts import decision
from .taxonomy import STATES


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def summarize(rows, calibration=True):
    """Rows = (gold state, probability dict or None). Null is algorithmic abstention."""
    n = len(rows)
    answered = [(gold, ps) for gold, ps in rows if ps is not None]
    counts = Counter((gold, decision(ps) if ps is not None else "ABSTAIN") for gold, ps in rows)
    gold_counts = Counter(gold for gold, _ in rows)
    classes = {}
    for state in STATES:
        tp = counts[state, state]
        predicted = sum(counts[g, state] for g in STATES)
        precision, recall = ratio(tp, predicted), ratio(tp, gold_counts[state])
        # F1=0 when a supported class is never predicted; undefined without support.
        f1 = ratio(2 * tp, predicted + gold_counts[state]) if gold_counts[state] else None
        classes[state] = {"support": gold_counts[state], "predicted": predicted,
                          "precision": precision, "recall": recall, "f1": f1}
    tp, fp = counts["YES", "YES"], counts["NO", "YES"]
    fn, tn = counts["YES", "NO"], counts["NO", "NO"]
    missed = gold_counts["YES"] - tp
    binary = {"tp": tp, "fp": fp, "tn": tn, "fn_explicit_no": fn,
              "positive_support": gold_counts["YES"], "negative_support": gold_counts["NO"],
              "precision": ratio(tp, tp + fp), "recall": ratio(tp, gold_counts["YES"]),
              "f1": ratio(2 * tp, 2 * tp + fp + missed),
              "false_positive_rate": ratio(fp, gold_counts["NO"]),
              "false_negative_rate": ratio(fn, gold_counts["YES"]),
              "missed_positive_rate_including_abstentions": ratio(missed, gold_counts["YES"])}
    result = {"n": n, "answered": len(answered), "coverage": ratio(len(answered), n),
              "accuracy_including_abstentions": ratio(sum(counts[s, s] for s in STATES), n),
              "accuracy_answered": ratio(sum(counts[s, s] for s in STATES), len(answered)),
              "classes": classes, "resolved_binary": binary,
              "confusion": {s: {p: counts[s, p] for p in (*STATES, "ABSTAIN")} for s in STATES},
              "calibration": None}
    if answered and calibration:
        brier = sum(sum((ps[s] - (s == gold)) ** 2 for s in STATES) for gold, ps in answered) / len(answered)
        nll = -sum(math.log(max(ps[gold], 1e-15)) for gold, ps in answered) / len(answered)
        bins = []
        for index in range(10):
            selected = [(gold, ps) for gold, ps in answered if min(int(max(ps.values()) * 10), 9) == index]
            if selected:
                bins.append({"lower": index / 10, "upper": (index + 1) / 10, "n": len(selected),
                             "confidence": sum(max(ps.values()) for _, ps in selected) / len(selected),
                             "accuracy": sum(decision(ps) == gold for gold, ps in selected) / len(selected)})
        ece = sum(b["n"] * abs(b["confidence"] - b["accuracy"]) for b in bins) / len(answered)
        result["calibration"] = {"n": len(answered), "multiclass_brier": brier, "nll": nll,
                                 "top_label_ece_10_bins": ece, "reliability_bins": bins}
    return result


def agreement(left, right):
    """Two independent annotations. No missing annotation is imputed as NO."""
    r = {row["id"]: row for row in right}
    observations = {}
    for row in left:
        if row["id"] not in r:
            continue
        other = r[row["id"]]
        if row["input"] != other["input"]:
            raise ValueError("raters must receive identical input")
        for name in row["judgments"].keys() & other["judgments"].keys():
            observations.setdefault(name, []).append((row["judgments"][name]["state"], other["judgments"][name]["state"]))
    report = {}
    for name, pairs in observations.items():
        n = len(pairs)
        observed = sum(a == b for a, b in pairs) / n
        a, b = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
        expected = sum(a[s] * b[s] for s in STATES) / n ** 2
        report[name] = {"n": n, "raw_agreement": observed,
                        "cohen_kappa": (observed - expected) / (1 - expected) if expected < 1 else None,
                        "disagreements": n - sum(a == b for a, b in pairs)}
    return report
