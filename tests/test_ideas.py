"""Mocked Meta responses for idea suggestions; these are not model results."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from sparkbench.ideas import IdeaError, suggest_ideas, validate_ideas
from sparkbench.meta import Config

STEPS = [{"red": True, "green": False, "text": "STOP"}, {"red": False, "green": True, "text": "GO"}]
GOOD = {"title": "Tiny traffic light", "idea": "Show STOP with the red LED, then GO with the green LED. Three seconds each.", "steps": STEPS}


def reply(ideas, status=200, finish="stop"):
    return Mock(status_code=status, json=Mock(return_value={"choices": [{"finish_reason": finish, "message": {"content": json.dumps({"ideas": ideas})}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}))


class IdeaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.out = Path(self.temp.name) / "out"
        self.config = Config("private-key", "muse-spark-1.3-contributor")
    def tearDown(self): self.temp.cleanup()
    def run_with(self, ideas, body=None, **kwargs):
        post = Mock(return_value=reply(ideas, **kwargs))
        return post, suggest_ideas(body or {"avoid": []}, self.out, config=self.config, post=post)

    def test_one_request_saves_its_record_without_the_key(self):
        post, result = self.run_with([GOOD])
        post.assert_called_once()
        self.assertEqual(result["ideas"], [{"title": GOOD["title"], "idea": GOOD["idea"]}])
        for name in ("request.json", "response.json", "result.json"):
            self.assertNotIn("private-key", (self.out / name).read_text())
        saved = json.loads((self.out / "result.json").read_text())
        self.assertEqual((saved["status"], saved["api_requests"], saved["advisory"], saved["ideas_returned"]), ("suggested", 1, True, 1))
        self.assertTrue(post.call_args.kwargs["json"]["response_format"]["json_schema"]["strict"])

    def test_an_idea_the_bench_cannot_run_is_dropped(self):
        lower = {**GOOD, "title": "Lowercase", "steps": [{"red": True, "green": False, "text": "stop"}]}
        too_long = {**GOOD, "title": "Too long", "steps": STEPS * 5}
        empty = {**GOOD, "title": "No steps", "steps": []}
        self.assertEqual(validate_ideas({"ideas": [lower, too_long, empty]}), [])

    def test_only_the_first_three_are_considered_and_bad_ones_do_not_hide_good_ones(self):
        bad = {**GOOD, "title": "Bad", "steps": []}
        kept = validate_ideas({"ideas": [bad, GOOD, {**GOOD, "title": "Second"}, {**GOOD, "title": "Fourth"}]})
        self.assertEqual([i["title"] for i in kept], [GOOD["title"], "Second"])

    def test_a_sentence_promising_more_than_the_bench_is_dropped(self):
        for word in ("Press the button to start.", "A buzzer sounds at GO.", "Repeat forever.", "Use the temperature sensor.", "Fade the red LED."):
            self.assertEqual(validate_ideas({"ideas": [{**GOOD, "idea": word}]}), [])

    def test_titles_already_shown_are_not_repeated(self):
        self.assertEqual(validate_ideas({"ideas": [GOOD]}, [GOOD["title"].upper()]), [])
        _, result = self.run_with([GOOD, {**GOOD, "title": "Fresh one"}], {"avoid": [GOOD["title"]]})
        self.assertEqual([i["title"] for i in result["ideas"]], ["Fresh one"])

    def test_nothing_usable_raises_a_message_and_makes_no_second_request(self):
        post = Mock(return_value=reply([{**GOOD, "steps": []}]))
        with self.assertRaisesRegex(IdeaError, "fit this bench"):
            suggest_ideas({"avoid": []}, self.out, config=self.config, post=post)
        post.assert_called_once()
        self.assertEqual(json.loads((self.out / "result.json").read_text())["status"], "no_ideas")

    def test_provider_failures_never_leak_and_never_retry(self):
        for index, kwargs in enumerate(({"status": 500}, {"finish": "length"})):
            post = Mock(return_value=reply([GOOD], **kwargs))
            with self.assertRaises(IdeaError) as caught:
                suggest_ideas({"avoid": []}, self.out / str(index), config=self.config, post=post)
            post.assert_called_once()
            self.assertNotIn("private-key", str(caught.exception))

    def test_bad_requests_never_reach_meta(self):
        post = Mock()
        for body in ({}, {"avoid": "x"}, {"avoid": ["x"] * 13}, {"avoid": ["x" * 41]}, {"avoid": [], "extra": 1}):
            with self.assertRaises(ValueError):
                suggest_ideas(body, self.out, config=self.config, post=post)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
