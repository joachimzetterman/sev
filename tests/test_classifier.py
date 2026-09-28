import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from sev.classifier import NaiveBayes, fit, tokens
from sev.contracts import read_jsonl, validate_prediction
from sev.taxonomy import STATES

DATA = Path(__file__).resolve().parents[1] / "data/smoke.jsonl"


class ClassifierTests(unittest.TestCase):
    def test_smoke_is_never_training(self):
        with self.assertRaisesRegex(ValueError, "train records only"):
            fit(read_jsonl(DATA))

    def test_fit_and_overlap_check(self):
        # Isolated unit fixture, not a published trained baseline.
        row = copy.deepcopy(read_jsonl(DATA)[0])
        row["split"] = "train"
        artifact = fit([row])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_text(json.dumps(artifact))
            model = NaiveBayes(path)
        names = ["PRIVILEGE_INCREASE", "TRUST_BOUNDARY_CHANGE"]
        result, _ = model.predict(row["input"], names)
        validate_prediction(result, names)
        self.assertIsNone(result["TRUST_BOUNDARY_CHANGE"]["probabilities"])
        with self.assertRaisesRegex(ValueError, "overlaps"):
            model.check_evaluation([row])

    def test_cached_scores_match_multinomial_formula(self):
        rows = read_jsonl(DATA)[:2]
        for row in rows:
            row["split"] = "train"
        artifact = fit(rows)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_text(json.dumps(artifact))
            model = NaiveBayes(path)
        name = "PRIVILEGE_INCREASE"
        value = {"diff": "+BUTTON_COLOUR = absent_from_vocabulary\n", "context": []}
        result, _ = model.predict(value, [name])
        examples = artifact["examples"][name]
        logits = []
        for state in STATES:
            counts = artifact["counts"][name][state]
            denominator = sum(counts.values()) + len(artifact["vocabulary"])
            score = math.log((examples[state] + 1) / (sum(examples.values()) + len(STATES)))
            score += sum(frequency * math.log((counts.get(term, 0) + 1) / denominator)
                         for term, frequency in tokens(value).items() if term in artifact["vocabulary"])
            logits.append(score)
        weights = [math.exp(score - max(logits)) for score in logits]
        for state, weight in zip(STATES, weights):
            self.assertAlmostEqual(result[name]["probabilities"][state], weight / sum(weights), places=14)

        separate = copy.deepcopy(rows[0])
        separate["source"]["project"], separate["group_id"], separate["input"] = "new-project", "new-group", value
        model.check_evaluation([separate])
        for field in ("project", "group", "input"):
            other = copy.deepcopy(separate)
            if field == "project":
                other["source"]["project"] = rows[0]["source"]["project"]
            elif field == "group":
                other["group_id"] = rows[0]["group_id"]
            else:
                other["input"] = rows[0]["input"]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "overlaps"):
                model.check_evaluation([other])


if __name__ == "__main__":
    unittest.main()
