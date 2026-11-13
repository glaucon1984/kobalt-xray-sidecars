"""python -m xraygen BOOK.epub: write BOOK.source.json and BOOK.xray.json with a local Ollama model or a hosted one.

    python -m xraygen "Count Zero.epub" -o out --host http://192.168.1.10:11434 --model qwen3.8:27b
    python -m xraygen "Count Zero.epub" -o out --api openai --base-url https://openrouter.ai/api/v1 --model MODEL

The host and the model also come from the environment (OLLAMA_HOST, XRAYGEN_MODEL). The key of a hosted
model is read from the environment variable OPENAI_API_KEY (or the one named by --api-key-env), never
from the command line. A run that is stopped, or that runs out of --max-minutes, goes on from where it was when started again.
"""
import argparse
import os
import sys

from .generate import Generator, Pause
from .errors import ModelError
from .ollama import Ollama
from .openai_api import OpenAI


def totals(model):
    """One line to price a run by: calls, seconds, and the tokens when the backend reported them."""
    line = "this run: %d calls to the model, %.0f s" % (model.calls, model.seconds)
    if getattr(model, "input_tokens", 0):
        line += ", %d input tokens" % model.input_tokens
    if model.output_tokens:
        line += ", %d output tokens" % model.output_tokens
    return line


def main():
    parser = argparse.ArgumentParser(prog="python -m xraygen", description="Generate a Kobalt X-Ray sidecar with a local model.")
    parser.add_argument("epub")
    parser.add_argument("-o", "--output", default=".", help="folder for the results and the cache (default: here)")
    parser.add_argument("-n", "--name", help="name of the results without extension (default: the EPUB's file name)")
    parser.add_argument("--api", choices=("ollama", "openai"), default="ollama",
                        help="kind of server: ollama, or openai for any OpenAI-compatible chat-completions API")
    parser.add_argument("--host", default=os.environ.get("OLLAMA_HOST") or "http://localhost:11434",
                        help="Ollama server (--api ollama)")
    parser.add_argument("--base-url", help="API root for --api openai, e.g. https://api.openai.com/v1, "
                        "https://openrouter.ai/api/v1 or http://localhost:11434/v1")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY", metavar="NAME",
                        help="environment variable that holds the API key for --api openai (default: %(default)s)")
    parser.add_argument("--model", default=os.environ.get("XRAYGEN_MODEL") or "qwen3.8:27b")
    parser.add_argument("--reasoning-effort", metavar="LEVEL",
                        help="send reasoning_effort (e.g. none, low) with --api openai; a thinking model otherwise "
                        "can use up the output limit on its thoughts")
    parser.add_argument("--language", help="language of the cards, as a code such as en or es (default: the book's)")
    parser.add_argument("--chapter-pattern", default=r"^(\d+)\b",
                        help="regular expression for chapter labels in the table of contents")
    parser.add_argument("--chapter-split", type=int, default=None, metavar="WORDS",
                        help="cut chapters longer than about this many words into parts, and number all from 1")
    parser.add_argument("--context", type=int, default=16384, help="context window to ask Ollama for (ignored by --api openai)")
    parser.add_argument("--max-minutes", type=float, help="stop cleanly after this long; run again to go on")
    arguments = parser.parse_args()
    if arguments.api == "openai":
        if not arguments.base_url:
            parser.error("--api openai needs --base-url, e.g. https://api.openai.com/v1")
        model = OpenAI(arguments.base_url, arguments.model, arguments.api_key_env,
                       reasoning_effort=arguments.reasoning_effort)
    else:
        host = arguments.host if "://" in arguments.host else "http://" + arguments.host
        model = Ollama(host, arguments.model, num_ctx=arguments.context)
    os.makedirs(arguments.output, exist_ok=True)
    try:
        generator = Generator(arguments.epub, arguments.output, model, language=arguments.language,
                              pattern=arguments.chapter_pattern, split=arguments.chapter_split,
                              minutes=arguments.max_minutes,
                              log=lambda line: print(line, flush=True))
        print("%s, %d chapters, cards in %s, model %s" % (
            generator.meta.get("title") or arguments.epub, len(generator.chapters), generator.language, arguments.model), flush=True)
        source, sidecar, problems = generator.run(arguments.name)
    except Pause:
        print("paused: the time allowed is used up. Run again to go on.")
        print(totals(model))
        return 3
    except (ModelError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    for problem in problems:
        print(problem)
    print("%d entries" % len(sidecar["characters"]))
    print(totals(model))
    return 0


if __name__ == "__main__":
    sys.exit(main())
