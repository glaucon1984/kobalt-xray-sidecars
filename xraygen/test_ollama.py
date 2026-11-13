"""Tests of xraygen.ollama against a fake local server; no network. Run: python -m xraygen.test_ollama"""
import unittest

from .ollama import Ollama, OllamaError
from .test_openai_api import SCHEMA, handler_for, serve


def chat(text, stopped="stop"):
    return {"message": {"content": text}, "done_reason": stopped, "eval_count": 5}


class Tests(unittest.TestCase):
    def run_against(self, answer):
        """A client whose /api/chat answers come from answer(count of chat calls)."""
        def respond(body, n):
            if "messages" not in body:
                return 200, {"capabilities": ["completion", "thinking"]}, {}
            return 200, answer(sum(1 for path, _, _ in handler.seen if path == "/api/chat")), {}
        handler = handler_for(respond)
        server, url = serve(handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return Ollama(url.replace("/v1", ""), "m"), handler.seen

    def chats(self, seen):
        return [body for path, body, _ in seen if path == "/api/chat"]

    def test_plain(self):
        client, seen = self.run_against(lambda n: chat('{"x": 1}'))
        self.assertEqual(client.ask("s", "u", SCHEMA), {"x": 1})
        self.assertIs(self.chats(seen)[0]["think"], False)

    def test_bad_answer_retried_colder(self):
        client, seen = self.run_against(lambda n: chat("nope" if n == 1 else '{"x": 2}'))
        self.assertEqual(client.ask("s", "u", SCHEMA, temperature=0.5), {"x": 2})
        self.assertEqual([b["options"]["temperature"] for b in self.chats(seen)], [0.5, 0.0])

    def test_cut_off_answer_retried_warmer_with_more_room(self):
        client, seen = self.run_against(lambda n: chat('{"x": [1, 1', "length") if n < 3 else chat('{"x": 3}'))
        self.assertEqual(client.ask("s", "u", SCHEMA, max_tokens=100, temperature=0.2), {"x": 3})
        self.assertEqual([(b["options"]["temperature"], b["options"]["num_predict"]) for b in self.chats(seen)],
                         [(0.2, 100), (0.5, 200), (0.7, 200)])

    def test_gives_up_after_three_tries(self):
        client, seen = self.run_against(lambda n: chat('{"x": [1', "length"))
        with self.assertRaises(OllamaError):
            client.ask("s", "u", SCHEMA)
        self.assertEqual(len(self.chats(seen)), 3)


if __name__ == "__main__":
    unittest.main()
