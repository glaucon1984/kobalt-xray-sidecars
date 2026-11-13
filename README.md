# X-Ray sidecars for Kobalt

Ready-made sidecar files for the **X-Ray** plugin of the [Kobalt](https://github.com/nicoverbruggen/kobalt) e-reader, and the tools to make more.

X-Ray is a Lua plugin by Dave Allie ([daveallie/kobalt-plugins](https://github.com/daveallie/kobalt-plugins)). Hold a name or a term while reading and it shows a card: who the character is, their relationships and where they were last seen, limited to what you have read so far. It gets all of that from a *sidecar*, a JSON file that sits beside the book. This repository holds sidecars and nothing of the plugin itself.

## Books

| Book | Edition the percentages were built from | Chapters | Entries |
| --- | --- | --- | --- |
| William Gibson, *Neuromancer* | Gollancz/Orion ebook (S.F. Masterworks), 2016 | 24 | 180 |
| William Gibson, *Count Zero* | Gollancz/Orion ebook, 2016 | 36 | 247 |
| William Gibson, *Mona Lisa Overdrive* | Gollancz/Orion ebook, 2016 | 45 | 225 |
| Liu Cixin, *El problema de los tres cuerpos* (in Spanish) | Spanish translation (Nova), ebook | 35 | 262 |
| Liu Cixin, *El bosque oscuro* (in Spanish) | Spanish translation (Nova), ebook | 45 parts | 321 |
| Liu Cixin, *El fin de la muerte* (in Spanish) | Spanish translation (Nova), ebook | 91 parts | 392 |

The three Gibson files were reviewed for spoiler timing and tried on an e-reader. The three Liu Cixin files have cards in Spanish and are not reviewed: a model wrote them and only a sample of cards was read against the books (see [How these files were made](#how-these-files-were-made)). The last two of those books have no numbered chapters, so their long sections are cut into parts of about 4,500 words, and facts are placed by part.

Entries are people, AIs and other named entities, plus the invented vocabulary, places and organisations of the setting. The files are in [`sidecars/`](sidecars/), each as a pair:

- `<book>.xray.json` — the sidecar, ready to use.
- `<book>.source.json` — what it was built from, written by chapter (see below).

## Using a sidecar

1. Install a Kobalt build with plugin support and the X-Ray plugin, as its [README](https://github.com/daveallie/kobalt-plugins#x-ray) describes. (On PocketBook: [glaucon1984/kobalt](https://github.com/glaucon1984/kobalt/releases), 0.10.0 or later.)
2. Copy the `.xray.json` file beside the book and **rename it after the book file**, without the book's last extension: `Count Zero - William Gibson.epub` takes `Count Zero - William Gibson.xray.json`.
3. Open the book and hold a name.

The `book` block inside the file (title, author, series) is only information; X-Ray does not compare it with the open book. What has to fit is the file name and the edition.

## Spoilers

Every fact carries the place in the book from which it may be shown.

- A person or term can be looked up from the first page of the chapter that introduces them, and that first card says only who they are at first sight.
- Whatever a chapter reveals shows from that chapter's last page on.
- What earlier books of a series told is available from the start, but is never attached to a character who appears under another name until the book makes the link.
- A secret identity is kept as two entries, or behind a name that only starts to match at the reveal.

The plugin itself knows only percentages of the book by word count. A long press usually selects one word, so cards also answer ordinary words that happen to be a name ("Case", "Count", "Deck"); the dictionary still opens first and X-Ray only offers its card.

## Another edition of the same book

The percentages in a `.xray.json` belong to the edition it was built from: front matter, an afterword or a preview chapter moves all of them. With a different edition a fact may show a little early or late. To fix that, rebuild the sidecar from the source file and your own EPUB:

```sh
python tools/make_sidecar.py "My Book.epub" sidecars/william-gibson/neuromancer.source.json -o .
```

The source file names chapters ("from the end of chapter 14"), and the tool works out the percentages from the EPUB at hand, the way Kobalt computes the reading position: the words before a chapter plus the share of the chapter read, over all the words of the book. It needs Python 3.8 or later and nothing else. `--chapters` lists the chapters it finds and their percentages.

## Making a sidecar for another book

- [`docs/WRITING.md`](docs/WRITING.md) — the conventions: the source format, when a fact may show, and how X-Ray matches names (which decides how entries must be named).
- [`tools/make_sidecar.py`](tools/make_sidecar.py) — builds the sidecar and checks it: unknown ids, names that never occur in the book, names that would answer every "the" or "of".
- [`tools/try_sidecar.lua`](tools/try_sidecar.lua) with [`tools/to_lua.py`](tools/to_lua.py) — look words up at a given position with the real plugin and a stock Lua 5.4, without an e-reader.
- [`docs/sprawl-glossary.md`](docs/sprawl-glossary.md) — reworded glossary notes for the Sprawl trilogy.

## Generating one with a model (experimental)

`xraygen` writes a source and a sidecar for a book with a model served by [Ollama](https://ollama.com) on your own machine, or with any hosted model that has an OpenAI-compatible API:

```sh
python -m xraygen "My Book.epub" -o out --host http://localhost:11434 --model qwen3.8:27b
python -m xraygen "My Book.epub" -o out --api openai --base-url https://api.example.com/v1 --model some-model
```

For a hosted model the key is read from the environment variable `OPENAI_API_KEY` (or the one named by `--api-key-env`), never from the command line; that route was tested for the protocol only, against a local OpenAI-compatible endpoint, and with no hosted provider. Other options: `--language es` names the language of the cards (a model does not follow the book's language by itself), `--chapter-pattern` chooses the table-of-contents entries that are chapters when they are not numbered, and `--chapter-split 4500` cuts long sections into parts. `python -m xraygen --help` lists them all.

It reads the book one chapter at a time, so a fact can only be dated to the chapter it came from; names, dates and checks are done by code, and the cards are written in the book's language. Every answer is cached in the output folder, so a run can be stopped and resumed. A novel takes roughly half an hour on a 24 GB graphics card.

The result is clearly rougher than the reviewed files in `sidecars/`: expect some wrong statements and missing turns of the plot. Treat it as a draft: the `.source.json` it writes can be corrected by hand and rebuilt with `tools/make_sidecar.py`.

## How these files were made

They were written with an AI assistant (Claude), not by hand and not from memory of the novels. For each Gibson book, readers went through every chapter in full and logged who appears, under which names, and what the chapter reveals; a writer then composed the entries from those logs, placing each fact at the chapter whose text states it; the result was reviewed for spoiler timing and tried with the real plugin at several positions. Mistakes are still possible: corrections are welcome as issues or pull requests against the `.source.json` files.

The Liu Cixin files were made a cheaper way: `xraygen` with a local model wrote the notes on each chapter, and one writer (Claude Sonnet 5.5) composed the entries from those notes and from the book, and ran a set of checks on its own file. I checked the builds and read the main characters' cards at several points and at the end against the books, and had the faults I found corrected; nobody has reviewed every card. The first book's file was made before the checks on relationship wording, so some of its relationships may read stale late in the book.

## Licences and credits

- The sidecars and their sources (`sidecars/`) and the documents (`docs/`) are under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). They are original descriptions and summaries; they contain no text of the novels beyond a few words in quotation marks.
- The tools (`tools/` and `xraygen/`) are under the [MIT licence](LICENSE).
- The novels belong to their authors and publishers. This is an unofficial reader's aid, not affiliated with them.
- The X-Ray plugin and Kobalt's plugin system are by Dave Allie; Kobalt is by Nico Verbruggen. The sidecar format, `kobalt-xray/1`, is defined in the plugin's repository.
- Glossary sources for the Sprawl trilogy, reworded: the Sprawl glossary of the *William Gibson aleph* site (antonraubenweiss.com/gibson/sprawlgloss.html) and the post "Neuromancer Terms and Definitions" in r/Neuromancer.
