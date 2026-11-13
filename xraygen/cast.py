"""Who is who across chapters: joins the people of each chapter log into persons, by code.

Two names are one person only when a chapter log uses the same name or name form for them.
What a model calls "same_as" is kept as a link that takes effect at the end of the chapter that
states it, so a secret identity stays two cards until the book gives it away.
"""
import re

TITLES = {"mr", "mrs", "ms", "miss", "dr", "sir", "lady", "lord", "herr", "frau", "señor", "señora", "don", "doña",
          "the", "old", "young", "el", "la", "los", "las"}


def key(text):
    """A name as it is compared: lower case, no edge punctuation, no possessive."""
    text = re.sub(r"\s+", " ", text.replace(" ", " ")).strip().lower()
    text = text.strip(" \t.,;:!?\"'()[]‘’“”–—-")
    return re.sub(r"(’|')s$", "", text)


def bare(text):
    """The key of a name without a leading article or title: "The Boxmaker" and "Boxmaker" are one name."""
    words = key(text).split()
    while len(words) > 1 and words[0] in TITLES:
        words = words[1:]
    return " ".join(words)


def proper(text):
    """Whether a form is a name, not a description: it holds a capital letter or a digit after any article."""
    words = [word for word in re.split(r"[\s ]+", text) if word]
    while words and key(words[0]) in TITLES:
        words = words[1:]
    return any(re.search(r"[A-ZÀ-ÝÑ0-9]", word) for word in words)


class Person:
    def __init__(self, number, name, chapter):
        self.number = number
        self.name = name.strip()
        self.forms = {}          # key -> (form as printed, first chapter)
        self.records = {}        # chapter -> merged record
        self.first = chapter
        self.add_form(name, chapter)

    def add_form(self, form, chapter):
        form = " ".join(form.split())
        if not form or not proper(form):
            return
        known = self.forms.get(bare(form))
        if known is None or chapter < known[1]:
            self.forms[bare(form)] = (form, chapter if known is None else min(chapter, known[1]))

    def keys(self):
        return set(self.forms)


class Cast:
    def __init__(self):
        self.people = []
        self.links = []          # (chapter, person, other person): "person is other", stated in that chapter
        self.unresolved = []     # (chapter, person, name) relationships to resolve at the end

    def find(self, name, forms=()):
        """The person a record belongs to, or None. The exact name wins over a shared form."""
        wanted = bare(name)
        if not wanted:
            return None
        exact = [person for person in self.people if bare(person.name) == wanted]
        if exact:
            return max(exact, key=lambda person: len(person.records))
        candidates = [person for person in self.people if wanted in person.keys()]
        if not candidates:
            # A fuller name of somebody known under part of it, or the other way round.
            usable = [bare(form) for form in forms if proper(form) and len(bare(form)) >= 3]
            candidates = [person for person in self.people if any(form in person.keys() for form in usable)]
        if not candidates:
            return None
        return max(candidates, key=lambda person: (len(person.records), -person.first))

    def add(self, chapter, record):
        """One person of a chapter log. A second record for the same person and chapter (a chapter read in
        parts) is merged into the first."""
        name = " ".join(str(record.get("name", "")).split())
        if not name or not proper(name):
            return None
        forms = [form for form in record.get("name_forms", []) if isinstance(form, str)]
        person = self.find(name, forms)
        if person is None:
            person = Person(len(self.people) + 1, name, chapter)
            self.people.append(person)
        person.add_form(name, chapter)
        for form in forms:
            person.add_form(form, chapter)
        # The fullest name seen becomes the display name, unless it only adds a title.
        longer = len(bare(name).split()) > len(bare(person.name).split())
        if longer and bare(person.name) in bare(name) and key(name.split()[0]) not in TITLES:
            person.name = name
        merged = person.records.get(chapter)
        learned = " ".join(str(record.get("learned", "")).split())
        if merged is None:
            person.records[chapter] = {
                "first_sight": " ".join(str(record.get("first_sight", "")).split()),
                "learned": learned,
                "in_person": bool(record.get("in_person")),
                "relationships": [],
            }
            merged = person.records[chapter]
        else:
            if learned and learned not in merged["learned"]:
                merged["learned"] = (merged["learned"] + " " + learned).strip()
            merged["in_person"] = merged["in_person"] or bool(record.get("in_person"))
        for relation in record.get("relationships", []):
            other, text = str(relation.get("with", "")).strip(), " ".join(str(relation.get("text", "")).split())
            if other and text:
                merged["relationships"].append((other, text))
        same = str(record.get("same_as", "")).strip()
        if same and bare(same) != bare(person.name) and bare(same) not in person.keys():
            other = self.find(same)
            if other is not None and other is not person:
                self.links.append((chapter, person, other))
        return person

    def roster(self, chapter, limit=40):
        """The who-is-who given to the model before a chapter: only what earlier chapters said."""
        earlier = [person for person in self.people if person.first < chapter]

        def weight(person):
            last = max(n for n in person.records if n < chapter)
            return (min(len(person.records), 6) + (4 if chapter - last <= 6 else 0), last)
        lines = []
        for person in sorted(earlier, key=weight, reverse=True)[:limit]:
            chapters = sorted(n for n in person.records if n < chapter)
            first, last = person.records[chapters[0]], person.records[chapters[-1]]
            also = [form for form, _ in person.forms.values() if bare(form) != bare(person.name)][:4]
            line = "- %s" % person.name
            if also:
                line += " (also: %s)" % ", ".join(also)
            line += ": " + (first["first_sight"] or first["learned"])[:160]
            if len(chapters) > 1 and last["learned"]:
                line += " Lately: " + last["learned"][:160]
            lines.append(line)
        return "\n".join(lines)
