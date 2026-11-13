"""What the model is asked. Bump VERSION when a prompt changes: cached answers are keyed by it.

The instructions are in English whatever the book's language; the language the answer must be
written in is named outright, because "the language of the chapter" is not followed.
"""
VERSION = "1"

LANGUAGES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
    "ca": "Catalan", "nl": "Dutch", "gl": "Galician", "eu": "Basque",
}


def language_name(code):
    return LANGUAGES.get((code or "en").lower().split("-")[0], "English")


CHAPTER_SCHEMA = {
    "type": "object",
    "required": ["people", "terms"],
    "properties": {
        "people": {"type": "array", "items": {
            "type": "object",
            "required": ["name", "name_forms", "in_person", "first_sight", "learned", "same_as", "relationships"],
            "properties": {
                "name": {"type": "string"},
                "name_forms": {"type": "array", "items": {"type": "string"}},
                "in_person": {"type": "boolean"},
                "first_sight": {"type": "string"},
                "learned": {"type": "string"},
                "same_as": {"type": "string"},
                "relationships": {"type": "array", "items": {
                    "type": "object", "required": ["with", "text"],
                    "properties": {"with": {"type": "string"}, "text": {"type": "string"}}}},
            }}},
        "terms": {"type": "array", "items": {
            "type": "object", "required": ["term", "meaning"],
            "properties": {"term": {"type": "string"}, "meaning": {"type": "string"}}}},
    },
}

CARD_SCHEMA = {
    "type": "object",
    "required": ["who", "now", "changed"],
    "properties": {"who": {"type": "string"}, "now": {"type": "string"}, "changed": {"type": "boolean"}},
}


def chapter_system(language):
    return (
        "You log one chapter of a novel for a spoiler-safe character guide. Use ONLY the chapter text given. "
        "Do not use anything you know about the book from elsewhere, and never state anything the text does not say. "
        "Copy names exactly as spelled. The book is in %s: write every sentence of your answer in %s, in short, plain sentences."
        % (language, language)
    )


def chapter_user(number, part, parts, roster, text):
    where = "Chapter %d" % number if parts == 1 else "Part %d of %d of chapter %d" % (part, parts, number)
    known = ""
    if roster:
        known = (
            "Who is who so far, from earlier chapters. Use it only to recognise people: when somebody in this text is one "
            "of them, use exactly that name as \"name\"; do not repeat these lines as news.\n%s\n\n" % roster
        )
    return (
        "%s%s of a novel follows between the markers.\n\n"
        "1. people: every NAMED person or named entity (an AI, a spirit, a talking machine) that appears or is mentioned, "
        "including minor ones and people in flashbacks. Do not list unnamed people, companies, places or groups. For each:\n"
        "- name: the fullest name the text uses (or the name from the who-is-who).\n"
        "- name_forms: every way this text refers to them by name (first name, surname, nickname, title with name).\n"
        "- in_person: true if they are present in a scene (also in a flashback or on a screen), false if only mentioned.\n"
        "- first_sight: one short sentence: who they are when they first appear in this text, with nothing learned later in it.\n"
        "- learned: one or two sentences with everything important this text establishes about them by its end: what they do, "
        "what happens to them, and above all anything revealed (who they really work for, a hidden role, a betrayal, a death). "
        "State as fact only what the text states as fact; when something is only suspected or claimed, say who suspects or "
        "claims it. Be sure who does what: do not give one person another person's actions.\n"
        "- same_as: only when this text itself reveals that this person and somebody known under another name are one and "
        "the same individual, that other name; otherwise an empty string. Two people who merely talk to each other are not the same.\n"
        "- relationships: their relations to other named people as this text states them; \"with\" is the other person's name "
        "and \"text\" a phrase of at most eight words from this person's side, such as \"Brother\" or \"Employer, who distrusts him\".\n"
        "2. terms: invented technology, slang, organisations and places that belong to the novel's world and that a reader "
        "might want explained, each with what it means as far as this text shows. Leave out everyday words, real brands, "
        "foods and real cities.\n\n"
        "<<<TEXT\n%s\nTEXT>>>" % (known, where, text)
    )


def card_system(language):
    return (
        "You keep a reader's card for one character of a novel up to date, chapter by chapter, for a spoiler-safe guide. "
        "Use ONLY the previous card and the notes given; never add anything from your own knowledge of the book. "
        "Write in %s." % language
    )


def card_user(name, who, now, number, first_sight, learned):
    notes = []
    if first_sight:
        notes.append("- first sight: %s" % first_sight)
    notes.append("- by the end of the chapter: %s" % learned)
    previous = "who: %s\nnow: %s" % (who, now) if who or now else "(no card yet)"
    return (
        "Character: %s\n\n"
        "Card at the end of the last chapter they were in:\n%s\n\n"
        "Notes from chapter %d:\n%s\n\n"
        "Write the card as it should read at the end of chapter %d, in two parts.\n"
        "- who: one sentence of at most 15 words saying what this person is in the story: role, trade, whose side. No "
        "name, no looks, voice, clothes or props. Change it only when the notes reveal something new about who they are.\n"
        "- now: one sentence of at most 25 words saying where they stand at the end of this chapter. Keep an earlier turning "
        "point only while it still matters (a death, a betrayal, a discovery); otherwise replace the old sentence with the "
        "news. Say plainly who did what to whom. Keep what is only suspected marked as suspected, with who suspects it.\n"
        "Do not begin with the name and do not mention chapter numbers. If the notes change nothing, return both parts "
        "word for word and set changed to false."
        % (name, previous, number, "\n".join(notes), number)
    )


SAME_SCHEMA = {
    "type": "object",
    "required": ["same", "quote"],
    "properties": {"same": {"type": "boolean"}, "quote": {"type": "string"}},
}


def same_user(first, second, text):
    return (
        "A text from a novel follows between the markers. Does it state or plainly show that \"%s\" and \"%s\" are one and "
        "the same individual, that is, two names for a single person? Two people who meet, talk or work together are not "
        "the same. Answer same=true only if the text shows it, and then copy into \"quote\", word for word, the one sentence "
        "of the text that shows it; otherwise same=false and an empty quote.\n\n<<<TEXT\n%s\nTEXT>>>" % (first, second, text)
    )


SIFT_SCHEMA = {
    "type": "object",
    "required": ["keep"],
    "properties": {"keep": {"type": "array", "items": {"type": "string"}}},
}


def sift_user(terms):
    return (
        "These are candidate entries for the glossary of a novel, one per line. Copy into \"keep\", exactly as written, only "
        "those that are invented words, slang, technology, organisations, artworks or places of the novel's own world, or "
        "proper names a reader may need explained. Leave out ordinary dictionary words (such as: mesa, jet, farm, dome, "
        "muscle, hammer), everyday objects, real brands and real cities.\n\n%s" % "\n".join(terms)
    )
