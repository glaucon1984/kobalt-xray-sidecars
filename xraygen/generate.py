"""Write an X-Ray source and sidecar for a book with a local language model.

The book is read one chapter at a time, so whatever a chapter log says can only have come from
that chapter: that, not the model's discipline, is what keeps a fact from showing early. The
model does the reading and the wording; names, dates and checks are done by code.

    1. chapter logs   one call per chapter (or per part of a long one), with a who-is-who of
                      earlier chapters so that people are recognised
    2. cast           the logs joined into persons, by code (cast.py)
    3. cards          per person, the card rewritten chapter by chapter from the card before and
                      that chapter's notes only
    4. source         names made safe for the plugin's matching, terms sifted, a leak check
    5. sidecar        sidecar.build, as for a hand-written source

Every answer of the model is cached under the output folder, so a run can stop and go on.
"""
import collections
import hashlib
import io
import json
import os
import re
import time
import unicodedata

from . import prompts
from .cast import TITLES, Cast, key, proper
from .sidecar import STOPWORDS, Book, build, no_nulls

MORE_STOPWORDS = {"el", "los", "las", "un", "una", "y", "o", "del", "al", "en", "con", "por", "para", "que", "se",
                  "is", "it", "he", "she", "his", "her", "was", "for", "with", "not", "but", "this", "that"}
PART_WORDS = 4500      # a longer chapter is read in parts of about this many words
MAX_TERMS = 150
MAX_RELATIONSHIPS = 10


class Pause(Exception):
    """The time allowed for this run is used up; run again to go on."""


class Words:
    """How the book itself uses words: a name that is also an ordinary word needs care."""

    def __init__(self, text):
        self.text = " " + " ".join(text.split()).lower() + " "
        self.lower = collections.Counter(
            token.lower() for token in re.findall(r"[^\W\d_][\w’'-]*", text) if token[0].islower())

    def common(self, word):
        word = key(word)
        return len(word) <= 2 or word in STOPWORDS or word in MORE_STOPWORDS or self.lower[word] >= 3

    def occurs(self, form):
        return re.search(r"(?<!\w)%s(?!\w)" % re.escape(key(form)), self.text) is not None

    def count(self, form):
        return len(re.findall(r"(?<!\w)%s(?!\w)" % re.escape(key(form)), self.text))


def slug(name, taken):
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "entry"
    candidate, counter = base, 2
    while candidate in taken:
        candidate = "%s-%d" % (base, counter)
        counter += 1
    taken.add(candidate)
    return candidate


def parts_of(paragraphs, limit=PART_WORDS):
    """A chapter as one text, or as parts of about `limit` words cut between paragraphs."""
    total = sum(len(paragraph.split()) for paragraph in paragraphs)
    if total <= limit * 1.3:
        return ["\n".join(paragraphs)]
    count = -(-total // limit)
    size, parts, current, words = total / count, [], [], 0
    for paragraph in paragraphs:
        current.append(paragraph)
        words += len(paragraph.split())
        if words >= size and len(parts) < count - 1:
            parts.append("\n".join(current))
            current, words = [], 0
    if current:
        parts.append("\n".join(current))
    return parts


class Generator:
    def __init__(self, epub, folder, model, language=None, pattern=r"^(\d+)\b", minutes=None, log=print, split=None):
        self.epub = epub
        self.book = Book(epub)
        self.meta = self.book.metadata()
        self.language = prompts.language_name(language or self.meta.get("language"))
        self.pattern = pattern
        self.split = split
        self.model = model
        self.log = log
        self.deadline = time.time() + minutes * 60 if minutes else None
        digest = hashlib.sha1(io.open(epub, "rb").read()).hexdigest()[:10]
        self.work = os.path.join(folder, "work-" + digest)
        os.makedirs(self.work, exist_ok=True)
        self.folder = folder
        self.chapters = self.book.chapter_texts(pattern, split)
        if not self.chapters:
            raise ValueError("no chapters found in the book's table of contents")
        self.words = Words("\n".join("\n".join(paragraphs) for _, _, paragraphs in self.chapters))

    # -- the model, with a cache --------------------------------------------------------------

    def ask(self, kind, name, system, user, schema, max_tokens, basis=None):
        """One cached answer. `basis` is what the answer is filed under when part of the prompt (the who-is-who)
        should not count: a chapter is not read again because the who-is-who came out differently."""
        digest = hashlib.sha1("\x00".join(
            [self.model.model, prompts.VERSION, kind, system, basis if basis is not None else user]
        ).encode("utf-8")).hexdigest()[:16]
        path = os.path.join(self.work, "%s-%s-%s.json" % (kind, name, digest))
        if os.path.exists(path):
            with io.open(path, encoding="utf-8") as handle:
                return json.load(handle)
        if self.deadline and time.time() > self.deadline:
            raise Pause()
        answer = self.model.ask(system, user, schema, max_tokens=max_tokens)
        with io.open(path, "w", encoding="utf-8") as handle:
            json.dump(answer, handle, ensure_ascii=False)
        return answer

    # -- 1 and 2: chapter logs, joined as they come ------------------------------------------

    def read_chapters(self):
        cast, terms = Cast(), {}
        system = prompts.chapter_system(self.language)
        for number, label, paragraphs in self.chapters:
            parts = parts_of(paragraphs)
            started = time.time()
            for index, text in enumerate(parts):
                user = prompts.chapter_user(number, index + 1, len(parts), cast.roster(number), text)
                answer = self.ask("chapter", "%03d-%d" % (number, index + 1), system, user,
                                  prompts.CHAPTER_SCHEMA, 6000,
                                  basis=prompts.chapter_user(number, index + 1, len(parts), "", text))
                links = len(cast.links)
                for record in answer.get("people", []):
                    if isinstance(record, dict):
                        cast.add(number, record)
                # "These two are one person" is only taken with a sentence of the text to show for it.
                for link in cast.links[links:]:
                    if not self.same(number, index + 1, link[1].name, link[2].name, text):
                        cast.links.remove(link)
                for item in answer.get("terms", []):
                    term = " ".join(str(item.get("term", "")).split()) if isinstance(item, dict) else ""
                    meaning = " ".join(str(item.get("meaning", "")).split()) if isinstance(item, dict) else ""
                    if term and meaning:
                        entry = terms.setdefault(key(term), {"term": term, "first": number, "meanings": {}})
                        entry["meanings"].setdefault(number, meaning)
            self.log("chapter %d (%s): %d part(s), %d people known, %.0f s"
                     % (number, label[:40], len(parts), len(cast.people), time.time() - started))
        return cast, terms

    def same(self, number, part, first, second, text):
        answer = self.ask("same", "%03d-%d-%s" % (number, part, slug(first + " " + second, set())),
                          prompts.chapter_system(self.language), prompts.same_user(first, second, text),
                          prompts.SAME_SCHEMA, 300)

        def flat(value):
            value = re.sub(r"[‘’“”\"']", "", value.lower())
            return " ".join(value.split())
        quote = flat(str(answer.get("quote", "")))
        shown = bool(answer.get("same")) and len(quote) >= 15 and quote.strip(" .,;:!?") in flat(text)
        self.log("chapter %d: %s = %s? %s" % (number, first, second, "yes" if shown else "no"))
        return shown

    def sift(self, candidates):
        """The terms worth a glossary entry, as the model judges a list of them: ordinary words go."""
        kept = set()
        for start in range(0, len(candidates), 80):
            batch = candidates[start:start + 80]
            answer = self.ask("sift", "%03d" % (start // 80), prompts.chapter_system(self.language),
                              prompts.sift_user(batch), prompts.SIFT_SCHEMA, 2500)
            kept |= {key(str(item)) for item in answer.get("keep", [])}
        return kept

    # -- 3: cards -----------------------------------------------------------------------------

    def cards(self, person):
        """[(when, text)] for one person: an introduction, then the card at the end of each chapter that
        changed it. A person in three chapters or more gets the rolling rewrite; a minor one keeps the notes."""
        chapters = sorted(person.records)
        first = person.records[chapters[0]]
        intro = first["first_sight"] or first["learned"]
        result = [("s%d" % chapters[0], intro)] if intro else []
        if len(chapters) < 3:
            for number in chapters:
                learned = person.records[number]["learned"]
                if learned and learned != intro:
                    result.append(("e%d" % number, learned))
            return result
        system = prompts.card_system(self.language)
        who = now = previous = ""
        for number in chapters:
            record = person.records[number]
            if not record["learned"]:
                continue
            user = prompts.card_user(person.name, who, now, number,
                                     record["first_sight"] if number == chapters[0] else "", record["learned"])
            answer = self.ask("card", "%03d-%03d" % (person.number, number), system, user, prompts.CARD_SCHEMA, 300)
            new_who = " ".join(str(answer.get("who", "")).split()) or who
            new_now = " ".join(str(answer.get("now", "")).split()) or now
            card = (new_who + " " + new_now).strip()
            if card and card != previous and (answer.get("changed", True) or not previous):
                result.append(("e%d" % number, card))
                who, now, previous = new_who, new_now, card
        return result

    # -- 4: the source ------------------------------------------------------------------------

    def naming(self, name, forms, intro):
        """The display name and the aliases, made safe for a plugin that indexes every word of a name."""
        parts = name.split()
        aliases, seen = [], set()

        def add(alias, chapter=None, when=None):
            text = alias if isinstance(alias, str) else alias
            if key(text) in seen:
                return
            seen.add(key(text))
            if when:
                aliases.append({"text": text, "when": when})
            elif chapter is not None and chapter > intro:
                aliases.append({"text": text, "when": "s%d" % chapter})
            else:
                aliases.append(text)
        if len(parts) > 1 and any(self.words.common(part) for part in parts):
            display = " ".join(parts)
            add(name)
            for part in parts:
                if not self.words.common(part) and key(part) not in TITLES and len(key(part)) >= 3:
                    add(part)
        else:
            display = name
            seen.add(key(name))
            for part in parts:
                seen.add(key(part))
        for form, chapter in sorted(forms, key=lambda item: item[1]):
            bare = re.sub(r"^(the|el|la|los|las)\s+", "", key(form))
            words = bare.split()
            if not words or not self.words.occurs(form):
                continue
            if all(self.words.common(word) for word in words):
                continue
            add(form, chapter)
        return display, aliases

    def source(self, cast, terms):
        problems, taken, entries = [], set(), []
        people = [person for person in cast.people if self.words.occurs(person.name)
                  or any(self.words.occurs(form) for form, _ in person.forms.values())]
        ids = {person.number: slug(person.name, taken) for person in people}
        links = collections.defaultdict(list)
        for chapter, person, other in cast.links:
            if person.number in ids and other.number in ids and chapter > other.first:
                links[other.number].append((chapter, person))
        for index, person in enumerate(people):
            summary = [{"when": when, "text": text} for when, text in self.cards(person)]
            if not summary:
                continue
            display, aliases = self.naming(person.name, list(person.forms.values()), person.first)
            for chapter, same in links.get(person.number, []):
                for form, _ in same.forms.values():
                    if self.words.occurs(form) and not all(self.words.common(word) for word in key(form).split()):
                        if key(form) not in {key(a if isinstance(a, str) else a["text"]) for a in aliases}:
                            aliases.append({"text": form, "when": "e%d" % chapter})
            entry = {"id": ids[person.number], "name": display}
            if aliases:
                entry["aliases"] = aliases
            entry["summary"] = summary
            relationships, paired = [], set()
            for number in sorted(person.records):
                for other_name, text in person.records[number]["relationships"]:
                    other = cast.find(other_name)
                    if other is None or other is person or other.number not in ids or other.number in paired:
                        continue
                    paired.add(other.number)
                    relationships.append({"when": "e%d" % number, "with": ids[other.number], "text": text})
            if relationships:
                entry["relationships"] = relationships[:MAX_RELATIONSHIPS]
            seen = [number for number in sorted(person.records) if person.records[number]["in_person"]]
            if seen:
                entry["seen"] = seen
            entries.append(entry)
            if (index + 1) % 20 == 0:
                self.log("cards: %d of %d people" % (index + 1, len(people)))
        # A link stated in a chapter: the other name's own card points across from that chapter on.
        by_number = {person.number: person for person in people}
        for other_number, items in links.items():
            for chapter, person in items:
                for entry in entries:
                    if entry["id"] == ids[person.number]:
                        entry["summary"].append({"when": "e%d" % chapter, "text": "= %s." % by_number[other_number].name})
        person_keys = set()
        for person in people:
            person_keys |= person.keys()
        kept = []
        for term_key, term in terms.items():
            if term_key in person_keys or not self.words.occurs(term["term"]) or len(term_key) < 3:
                continue
            if term_key in STOPWORDS or term_key in MORE_STOPWORDS:
                continue
            uses = self.words.count(term["term"])
            if len(term["meanings"]) < 2 and uses < 3:
                continue
            kept.append((len(term["meanings"]), uses, term))
        worth = self.sift(sorted(term["term"] for _, _, term in kept))
        kept = [item for item in kept if key(item[2]["term"]) in worth]
        kept.sort(key=lambda item: (-item[0], -item[1]))
        for _, _, term in sorted(kept[:MAX_TERMS], key=lambda item: item[2]["first"]):
            words = term["term"].split()
            entry = {"id": slug(term["term"], taken), "name": " ".join(words)}
            if len(words) > 1:
                entry["aliases"] = [term["term"]]
            entry["summary"] = [{"when": "s%d" % term["first"], "text": term["meanings"][term["first"]]}]
            entries.append(entry)
        # Leak check: a card dated to a chapter should not name somebody first met later.
        # "First met" is where the name first stands in the text, not where a log first listed it.
        lowered = [(number, " " + " ".join(" ".join(paragraphs).split()).lower() + " ")
                   for number, _, paragraphs in self.chapters]
        first_met = {}
        for person in people:
            for form_key, (form, _) in person.forms.items():
                if len(form_key) >= 4 and not all(self.words.common(word) for word in form_key.split()):
                    pattern = re.compile(r"(?<!\w)%s(?!\w)" % re.escape(form_key))
                    printed = next((number for number, text in lowered if pattern.search(text)), person.first)
                    first_met[form_key] = min(printed, first_met.get(form_key, 10 ** 6))
        for entry in entries:
            own = {key(entry["name"])} | {key(a if isinstance(a, str) else a["text"]) for a in entry.get("aliases", [])}
            for item in entry["summary"]:
                chapter = int(re.sub(r"\D", "", item["when"]) or 0)
                text = " " + key(item["text"]) + " "
                for form_key, first in first_met.items():
                    if first > chapter and form_key not in own and re.search(r"(?<!\w)%s(?!\w)" % re.escape(form_key), text):
                        problems.append("leak? %s at %s names %r, first met in chapter %d"
                                        % (entry["id"], item["when"], form_key, first))
        book = {"title": self.meta.get("title", ""), "author": self.meta.get("creator", "")}
        notes = ("Generated by xraygen %s with the model %s, reading the book one chapter at a time. "
                 "Not reviewed by a person." % (__import__("xraygen").__version__, self.model.model))
        source = {"book": {k: v for k, v in book.items() if v}, "notes": notes}
        # The chapter numbers in the entries depend on both, so the source carries them.
        if self.pattern != r"^(\d+)\b":
            source["chapter_pattern"] = self.pattern
        if self.split:
            source["chapter_split"] = self.split
        source["entries"] = entries
        return source, problems

    # -- all of it ----------------------------------------------------------------------------

    def run(self, name=None):
        cast, terms = self.read_chapters()
        self.log("%d people and %d terms in the logs; writing cards" % (len(cast.people), len(terms)))
        source, problems = self.source(cast, terms)
        sidecar = build(source, self.book, problems)
        no_nulls(sidecar)
        base = name or os.path.splitext(os.path.basename(self.epub))[0]
        for suffix, data in ((".source.json", source), (".xray.json", sidecar)):
            with io.open(os.path.join(self.folder, base + suffix), "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=1)
                handle.write("\n")
        return source, sidecar, problems
