"""Tests of xraygen.openai_api against a fake local server; no network. Run: python -m xraygen.test_openai_api"""
import http.server
import json
import os
import threading
import unittest

from .openai_api import OpenAI, OpenAIError, parse_json

SCHEMA = {"type": "object", "properties": {"x": {"type": "integer"}}}


def serve(handler):
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:%d/v1" % server.server_port


def handler_for(respond):
    """A handler class whose answers come from respond(request body, count, headers) -> (status, body, headers)."""
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, body, dict(self.headers)))
            status, reply, extra = respond(body, len(seen))
            data = (reply if isinstance(reply, str) else json.dumps(reply)).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            for name, value in extra.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass
    Handler.seen = seen
    return Handler


def chat(text, usage=True):
    reply = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
    if usage:
        reply["usage"] = {"prompt_tokens": 11, "completion_tokens": 7}
    return reply


class Tests(unittest.TestCase):
    def run_against(self, respond, **options):
        handler = handler_for(respond)
        server, url = serve(handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return OpenAI(url, "m", pauses=(0, 0, 0), **options), handler.seen

    def test_plain(self):
        client, seen = self.run_against(lambda body, n: (200, chat('{"x": 1}'), {}))
        self.assertEqual(client.ask("s", "u", SCHEMA), {"x": 1})
        self.assertEqual(seen[0][0], "/v1/chat/completions")
        self.assertEqual(seen[0][1]["response_format"]["type"], "json_schema")
        self.assertEqual((client.calls, client.input_tokens, client.output_tokens), (1, 11, 7))

    def test_schema_rejected_falls_back_and_is_remembered(self):
        def respond(body, n):
            if body.get("response_format", {}).get("type") == "json_schema":
                return 400, "no json_schema here", {}
            return 200, chat('{"x": 2}'), {}
        client, seen = self.run_against(respond)
        self.assertEqual(client.ask("s", "u", SCHEMA), {"x": 2})
        self.assertEqual(seen[1][1]["response_format"], {"type": "json_object"})
        self.assertIn("one JSON object", seen[1][1]["messages"][1]["content"])
        self.assertIn('"properties"', seen[1][1]["messages"][1]["content"])
        client.ask("s", "u", SCHEMA)
        self.assertEqual(seen[2][1]["response_format"], {"type": "json_object"})   # no new probing

    def test_both_rejected_goes_without_format(self):
        def respond(body, n):
            return (422, "no", {}) if "response_format" in body else (200, chat('{"x": 3}'), {})
        client, seen = self.run_against(respond)
        self.assertEqual(client.ask("s", "u", SCHEMA), {"x": 3})
        self.assertNotIn("response_format", seen[-1][1])
        self.assertEqual(client.mode, "none")

    def test_fenced_and_surrounded_answers(self):
        self.assertEqual(parse_json('```json\n{"x": 1}\n```'), {"x": 1})
        self.assertEqual(parse_json('Here you go: {"x": {"y": 2}} Done.'), {"x": {"y": 2}})
        client, _ = self.run_against(lambda body, n: (200, chat('```json\n{"x": 4}\n```'), {}))
        self.assertEqual(client.ask("s", "u", SCHEMA), {"x": 4})

    def test_429_is_retried_with_retry_after(self):
        client, seen = self.run_against(
            lambda body, n: (429, "slow down", {"Retry-After": "0"}) if n == 1 else (200, chat('{"x": 5}'), {}))
        self.assertEqual(client.ask("s", "u", SCHEMA), {"x": 5})
        self.assertEqual(len(seen), 2)

    def test_5xx_gives_up_after_three_retries(self):
        client, seen = self.run_against(lambda body, n: (503, "down", {}))
        with self.assertRaises(OpenAIError):
            client.ask("s", "u", SCHEMA)
        self.assertEqual(len(seen), 4)

    def test_bad_answer_retried_colder(self):
        client, seen = self.run_against(lambda body, n: (200, chat("nope" if n == 1 else '{"x": 6}'), {}))
        self.assertEqual(client.ask("s", "u", SCHEMA, temperature=0.5), {"x": 6})
        self.assertEqual((seen[0][1]["temperature"], seen[1][1]["temperature"]), (0.5, 0.0))

    def test_max_completion_tokens_switch(self):
        def respond(body, n):
            if "max_tokens" in body:
                return 400, "Unsupported parameter: use max_completion_tokens instead", {}
            return 200, chat('{"x": 7}', usage=False), {}
        client, seen = self.run_against(respond)
        self.assertEqual(client.ask("s", "u", SCHEMA, max_tokens=99), {"x": 7})
        self.assertEqual(seen[-1][1]["max_completion_tokens"], 99)
        self.assertEqual(seen[-1][1]["response_format"]["type"], "json_schema")   # the mode was not given up
        self.assertEqual(client.input_tokens, 0)

    def test_key_only_from_environment(self):
        os.environ["XRAYGEN_TEST_KEY"] = "secret-123"
        os.environ["XRAYGEN_TEST_EMPTY"] = ""
        client, seen = self.run_against(lambda body, n: (200, chat('{"x": 1}'), {}), api_key_env="XRAYGEN_TEST_KEY")
        client.ask("s", "u", SCHEMA)
        self.assertEqual(seen[0][2]["Authorization"], "Bearer secret-123")
        self.assertNotIn("secret-123", client.cache_id)
        client, seen = self.run_against(lambda body, n: (200, chat('{"x": 1}'), {}), api_key_env="XRAYGEN_TEST_EMPTY")
        client.ask("s", "u", SCHEMA)
        self.assertNotIn("Authorization", seen[0][2])


if __name__ == "__main__":
    unittest.main()
