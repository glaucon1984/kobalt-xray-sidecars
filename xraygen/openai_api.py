"""A small client for any server with an OpenAI-compatible chat-completions API (hosted or local).

Same interface as Ollama in ollama.py. The API key is read from an environment variable only, so that it
never shows up in a command line, a log or the cache."""
import json
import os
import re
import time
import urllib.error
import urllib.request

from .errors import TRIES, ModelError, next_try

PAUSES = (2, 5, 15)            # seconds before each of the three retries
MODES = ("json_schema", "json_object", "none")


class OpenAIError(ModelError):
    pass


def parse_json(text):
    """The JSON object in a model's text: a Markdown fence is stripped, text around the object is dropped."""
    text = (text or "").strip()
    fence = re.match(r"^```[A-Za-z]*\s*\n(.*?)\n?```\s*$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start:end + 1])


class OpenAI:
    def __init__(self, base_url, model, api_key_env="OPENAI_API_KEY", timeout=1800, pauses=PAUSES,
                 reasoning_effort=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = os.environ.get(api_key_env, "") if api_key_env else ""
        self.timeout = timeout
        self.pauses = pauses
        self.reasoning_effort = reasoning_effort   # a thinking model spends the output budget on thoughts
        self.calls = 0
        self.seconds = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.mode = MODES[0]           # the structured-output mode that works, found by trying
        self.limit_name = "max_tokens"
        # What a cached answer is filed under: another server or another model must not share it.
        self.cache_id = "openai\x00%s\x00%s" % (self.base_url, model)

    def _send(self, payload):
        """(status, parsed body or error text) of one POST, with retries for 429, 5xx and network errors."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        data = json.dumps(payload).encode("utf-8")
        for attempt in range(len(self.pauses) + 1):
            request = urllib.request.Request(self.base_url + "/chat/completions", data=data, headers=headers)
            wait = self.pauses[attempt] if attempt < len(self.pauses) else None
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return 200, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                text = error.read().decode("utf-8", "replace")
                if error.code != 429 and error.code < 500:
                    return error.code, text
                problem = "%s answered %s: %s" % (self.base_url, error.code, text[:300])
                after = error.headers.get("Retry-After") if error.headers else None
                if after and after.strip().isdigit():
                    wait = min(int(after), 120) if wait is not None else None
            except (urllib.error.URLError, OSError, ValueError) as error:
                problem = "cannot reach %s: %s" % (self.base_url, error)
            if wait is None:
                raise OpenAIError(problem)
            time.sleep(wait)

    def _body(self, system, user, schema, max_tokens, temperature):
        if self.mode != "json_schema":
            user += ("\n\nAnswer with one JSON object and nothing else, in this JSON schema:\n"
                     + json.dumps(schema, ensure_ascii=False))
        body = {"model": self.model, "temperature": temperature, self.limit_name: max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        if self.mode == "json_schema":
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}}
        elif self.mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    def _call(self, system, user, schema, max_tokens, temperature):
        """The reply of one call, after switching the output-limit name or the structured-output mode if needed."""
        while True:
            started = time.time()
            status, reply = self._send(self._body(system, user, schema, max_tokens, temperature))
            self.calls += 1
            self.seconds += time.time() - started
            if status == 200:
                return reply
            if status in (400, 422):
                if "max_completion_tokens" in reply and self.limit_name == "max_tokens":
                    self.limit_name = "max_completion_tokens"
                    continue
                if self.mode != "none":
                    self.mode = MODES[MODES.index(self.mode) + 1]
                    continue
            raise OpenAIError("%s answered %s: %s" % (self.base_url, status, reply[:300]))

    def ask(self, system, user, schema, max_tokens=6000, temperature=0.2):
        """The model's answer as a parsed JSON object, asked again when it does not parse (see errors.next_try)."""
        last = None
        for attempt in range(TRIES):
            reply = self._call(system, user, schema, max_tokens, temperature)
            usage = reply.get("usage") or {}
            self.input_tokens += usage.get("prompt_tokens") or 0
            self.output_tokens += usage.get("completion_tokens") or 0
            stopped = None
            try:
                choice = reply["choices"][0]
                stopped = choice.get("finish_reason")
                answer = parse_json(choice["message"]["content"])
                if isinstance(answer, dict):
                    return answer
                last = "not a JSON object"
            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
                last = "%s (stopped: %s)" % (error, stopped)
            temperature, max_tokens = next_try(attempt, temperature, max_tokens, stopped == "length")
        raise OpenAIError("the model's answer was not valid JSON in %d tries: %s" % (TRIES, last))
