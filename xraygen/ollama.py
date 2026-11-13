"""A small client for a local Ollama server: one chat call that must return JSON of a given schema."""
import json
import time
import urllib.error
import urllib.request

from .errors import ModelError


class OllamaError(ModelError):
    pass


class Ollama:
    def __init__(self, host, model, num_ctx=16384, timeout=1800):
        self.host = host.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.calls = 0
        self.seconds = 0.0
        self.output_tokens = 0
        self._thinking = None

    def _post(self, path, payload):
        request = urllib.request.Request(self.host + path, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise OllamaError("%s answered %s: %s" % (self.host, error.code, error.read().decode("utf-8", "replace")[:300]))
        except (urllib.error.URLError, OSError) as error:
            raise OllamaError("cannot reach Ollama at %s: %s" % (self.host, error))

    def thinks(self):
        """Whether the model has a thinking mode, which is switched off: it eats the output budget."""
        if self._thinking is None:
            self._thinking = "thinking" in self._post("/api/show", {"model": self.model}).get("capabilities", [])
        return self._thinking

    def ask(self, system, user, schema, max_tokens=6000, temperature=0.2):
        """The model's answer as a parsed JSON object. One retry, colder, when the answer does not parse."""
        last = None
        for attempt in range(2):
            body = {
                "model": self.model, "stream": False, "format": schema,
                "options": {"num_ctx": self.num_ctx, "temperature": temperature if attempt == 0 else 0.0,
                            "num_predict": max_tokens},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }
            if self.thinks():
                body["think"] = False
            started = time.time()
            reply = self._post("/api/chat", body)
            self.calls += 1
            self.seconds += time.time() - started
            self.output_tokens += reply.get("eval_count", 0)
            try:
                return json.loads(reply["message"]["content"])
            except (KeyError, ValueError) as error:
                last = "%s (stopped: %s)" % (error, reply.get("done_reason"))
        raise OllamaError("the model's answer was not valid JSON twice: %s" % last)
