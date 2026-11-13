# Writing an X-Ray source file (conventions)

The X-Ray plugin for the Kobalt e-reader shows a card when the reader long-presses a word in a book: who a character is, their relationships and where they were last seen, limited to what the reader has read so far. Glossary terms are entries too (a summary only). You write a *source* file by chapter; `make_sidecar.py` turns it into the sidecar with percentages.

Read first:
- `tools/make_sidecar.py` — its docstring defines the source format.
- `sidecars/william-gibson/neuromancer.source.json` — a finished example. Match its style, density and tone.

## Format rules

- JSON, UTF-8, no `null` anywhere. Top level: `book`, `notes`, `entries`. If the book's table of contents labels are bare numbers ("1", "2"), nothing special is needed.
- Each entry: `id` (unique, lowercase), `name`, optional `aliases`, `summary` (at least one), optional `relationships`, optional `seen`.
- `when` is `0`, `"sN"` or `"eN"`:
  - `0` — known before the book starts: world vocabulary, and for a later book in the series what the earlier books told (keep these free of this book's plot).
  - `"sN"` — from the first page of chapter N. Use for the *introduction* of a person or term first met in chapter N, and say only what the first pages of that chapter show (who they are on first sight). No later facts.
  - `"eN"` — from the last page of chapter N. Use for everything chapter N *reveals*.
- Each later summary is the **whole picture at that point** in one or two sentences (it replaces the earlier one), never a change note like "Now he is dead".
- Never reveal anything before the chapter whose text states it. Use the chapter notes to place each fact; where the notes say "hinted", do not state it as fact at that point.
- `name` and plain string aliases are visible as soon as the entry is known, and `name` shows in other entries' relationships, so they must never give a secret away. A secret identity is either a separate entry until the reveal, or an alias object `{ "text": "...", "when": "eN" }` that only matches from the reveal on.
- `relationships`: `{ "when", "with": "<other id>", "text": "short phrase" }`, a few per main character, updated with a later entry when they change. `with` must be an existing id.
- `seen`: chapter numbers where the entry appears **in person** (not mere mentions). Main and secondary characters only.
- Texts: short, plain, no markup, in the language and spelling of the book (British spelling for the Gibson editions here). Write in your own words; do not copy sentences from the novel or from any glossary.

## How matching works (important)

The plugin matches the pressed word, ignoring case, edge punctuation and a trailing 's, against: the full `name`, **every single word of `name`**, and each alias **as a whole**. An alias beginning with "the " also matches without "the".

- So `name` must not contain a common word: "New Yen" would answer every "new". Name the entry "Yen" and add alias "New Yen". "Big Playground" → name "Playground", alias "Big Playground".
- Never write an alias like "the Place" or "the well" (it would answer every "place"/"well").
- When the display name needs a common word ("People of Importance", "Lord of Roads", "Street samurai", "Black medicine"), write the name with no-break spaces as `\u00a0` in the JSON ("Street\u00a0samurai") so it is one key that never matches, and add the normal spelling as an alias, plus any safe single word ("samurai").
- A long press usually selects one word, so list single-word aliases: first name, surname, nickname, plural and other inflected forms ("jacked", "icebreakers").
- Two entries may share a word (two people called Roberts): they stack in one card. Fine.
- Matching ignores case, so a name like "Deck" or "ICE" also answers the ordinary word. Acceptable for real glossary terms; avoid it for very common words.

## Scope

- People: every named character who matters at all, including minor named ones (one short summary), AIs, constructs, loa and other named entities. Skip unnamed people.
- Terms: invented jargon, technology, slang, corporations, places of the setting, and real-world references a reader may want explained (an artist, a brand that matters). Only terms that actually occur in the book's text — the generator warns when a name or alias does not occur. Use `glossary-ref.md` and the Count Zero example for definitions, reworded to fit this book and staged so that they do not spoil it.
- Aim for the density of the reviewed sidecars in `sidecars/`: 180 to 250 entries for a novel of about 90,000 words (Neuromancer has 180, Mona Lisa Overdrive 225, Count Zero 247), and more for a longer book or a larger cast. The number follows from covering the book: every named person, and every term a reader might press and want explained. Do not reach it by adding ordinary words.

## Checking your work

Run from the repository root (on Windows with `PYTHONIOENCODING=utf-8`):

    python tools/make_sidecar.py "<epub path>" <source.json> -n <name>

- An `error:` line must be fixed.
- "does not occur in the book": fix the spelling, or drop the alias/entry (a no-break-space display name is exempt).
- "first occurs in chapter X, before the entry is known (chapter Y)": check it. If the person or term really is first met in chapter X, move the introduction to `sX`. If it is another use of the same word (a common word, another person's name), leave it.
- "would answer every ...": fix the name as described above.
- `note: ... answers for a, b` lines are informational.
