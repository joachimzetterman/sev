"""A simple bag-of-words control. No neural weights or pickle deserialization."""

import math
import re
from collections import Counter
from pathlib import Path

from .contracts import digest, dumps, loads, validate_dataset
from .taxonomy import EVALS, STATES, VERSION


def tokens(value):
    return Counter(re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[^\w\s]", dumps(value).lower()))


def fit(rows):
    validate_dataset(rows)
    if any(row["split"] != "train" for row in rows):
        raise ValueError("classifier fitting accepts train records only; never smoke/dev/calibration/test")
    counts = {name: {s: Counter() for s in STATES} for name in EVALS}
    examples = {name: Counter() for name in EVALS}
    vocabulary = set()
    for row in rows:
        terms = tokens(row["input"])
        vocabulary.update(terms)
        for name, gold in row["judgments"].items():
            state = gold["state"]
            counts[name][state].update(terms)
            examples[name][state] += 1
    return {"format": "sev-naive-bayes-0.1", "taxonomy_version": VERSION,
            "training_hash": digest(rows), "training_projects": sorted({r["source"]["project"] for r in rows}),
            "training_groups": sorted({r["group_id"] for r in rows}),
            "training_inputs": sorted({digest(r["input"]) for r in rows}),
            "vocabulary": sorted(vocabulary),
            "counts": {n: {s: dict(c) for s, c in states.items()} for n, states in counts.items()},
            "examples": {n: {s: examples[n][s] for s in STATES} for n in EVALS}}


class NaiveBayes:
    def __init__(self, path):
        self.artifact = loads(Path(path).read_text())
        data = self.artifact
        if data.get("format") != "sev-naive-bayes-0.1" or data.get("taxonomy_version") != VERSION:
            raise ValueError("unsupported classifier artifact")
        try:
            if set(data["counts"]) != set(EVALS) or set(data["examples"]) != set(EVALS):
                raise ValueError("invalid classifier evals")
            self.vocabulary = set(data["vocabulary"])
            if not self.vocabulary or not all(isinstance(t, str) for t in self.vocabulary):
                raise ValueError("invalid vocabulary")
            for name in EVALS:
                if set(data["counts"][name]) != set(STATES) or set(data["examples"][name]) != set(STATES):
                    raise ValueError("invalid classifier states")
                for state in STATES:
                    numbers = [data["examples"][name][state], *data["counts"][name][state].values()]
                    if any(type(n) is not int or n < 0 for n in numbers):
                        raise ValueError("invalid classifier counts")
            for field in ("training_projects", "training_groups", "training_inputs"):
                if not isinstance(data[field], list) or not all(isinstance(v, str) for v in data[field]):
                    raise ValueError("invalid training provenance")
        except (KeyError, TypeError, AttributeError):
            raise ValueError("invalid classifier artifact") from None
        self.metadata = {"backend": "nb", "model": "bag-of-words-naive-bayes-0.1", "revision": digest(data),
                         "training_hash": data["training_hash"], "probability_kind": "naive_bayes_posterior", "calibrated": False}
        self.training_projects = set(data["training_projects"])
        self.training_groups = set(data["training_groups"])
        self.training_inputs = set(data["training_inputs"])
        self.parameters = {}
        for name in EVALS:
            examples = data["examples"][name]
            total = sum(examples.values())
            if not total:
                continue
            self.parameters[name] = []
            for state in STATES:
                counts = data["counts"][name][state]
                denominator = sum(counts.values()) + len(self.vocabulary)
                prior = math.log((examples[state] + 1) / (total + len(STATES)))
                likelihoods = {term: math.log((count + 1) / denominator)
                               for term, count in counts.items() if term in self.vocabulary}
                self.parameters[name].append((prior, likelihoods, math.log(1 / denominator)))

    def check_evaluation(self, rows):
        for row in rows:
            if (row["source"]["project"] in self.training_projects
                    or row["group_id"] in self.training_groups
                    or digest(row["input"]) in self.training_inputs):
                raise ValueError("classifier evaluation overlaps training provenance")

    def predict(self, value, names):
        terms, result = tokens(value), {}
        known = [(term, count) for term, count in terms.items() if term in self.vocabulary]
        for name in names:
            parameters = self.parameters.get(name)
            if parameters is None:
                result[name] = {"probabilities": None}
                continue
            logits = [prior + sum(count * likelihoods.get(term, unseen) for term, count in known)
                      for prior, likelihoods, unseen in parameters]
            maximum = max(logits)
            weights = [math.exp(score - maximum) for score in logits]
            total = sum(weights)
            result[name] = {"probabilities": {state: weight / total for state, weight in zip(STATES, weights)}}
        return result, {"input_tokens": sum(terms.values()), "output_tokens": 0, "cost_usd": None}
