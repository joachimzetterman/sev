import io
import json
import unittest
from unittest.mock import MagicMock, patch

from sev.backends import HTTP
from sev.contracts import one_hot


class HTTPTests(unittest.TestCase):
    def request(self, response, kev=False):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        with patch("urllib.request.build_opener", return_value=opener):
            return HTTP("http://127.0.0.1:8000", "model", "revision", kev=kev).predict(
                {"diff": "-x=1\n+x=2\n", "context": []}, ["PRIVILEGE_INCREASE"])

    def test_valid_chat_distribution(self):
        prediction = {"PRIVILEGE_INCREASE": one_hot("NO")}
        result, stats = self.request({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(prediction)}}],
                                      "usage": {"prompt_tokens": 500, "completion_tokens": 60}})
        self.assertEqual(result, prediction)
        self.assertEqual(stats["input_tokens"], 500)

    def test_incomplete_response_fails(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.request({"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]})

    def test_no_prose_repair_or_missing_eval_imputation(self):
        for content in ("Everything is safe", "{}", "```json\n{}\n```"):
            with self.assertRaises(ValueError):
                self.request({"choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    def test_kev_rounding_is_normalized_only_within_tolerance(self):
        answer = {"answers": {"PRIVILEGE_INCREASE": {"probabilities": {
            "YES": .3333, "NO": .3333, "UNKNOWN": .3333, "INSUFFICIENT_CONTEXT": 0}}}}
        result, stats = self.request(answer, kev=True)
        self.assertAlmostEqual(sum(result["PRIVILEGE_INCREASE"]["probabilities"].values()), 1)
        self.assertEqual(stats["output_tokens"], 0)
        answer["answers"]["PRIVILEGE_INCREASE"]["probabilities"]["YES"] = .8
        with self.assertRaises(ValueError):
            self.request(answer, kev=True)


if __name__ == "__main__":
    unittest.main()
