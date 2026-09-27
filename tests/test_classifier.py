import copy
import json
import tempfile
import unittest
from pathlib import Path

from sev.classifier import NaiveBayes, fit
from sev.contracts import read_jsonl, validate_prediction

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


if __name__ == "__main__":
    unittest.main()
