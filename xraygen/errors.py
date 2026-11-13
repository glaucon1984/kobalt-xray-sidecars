"""The one error both model backends raise, so that the command line catches a single type, and the rule both
follow when an answer does not parse."""


class ModelError(Exception):
    pass


TRIES = 3


def next_try(failed, temperature, max_tokens, cut_off):
    """(temperature, output limit) for the try after try number `failed` (from 0) gave no valid JSON.

    An answer that ran into the output limit was usually caught repeating itself, and asked again colder it repeats
    itself again, word for word: it is asked again warmer, with twice the room. Any other bad answer is asked again
    colder."""
    if cut_off:
        return max(temperature, 0.5 + 0.2 * failed), max_tokens * 2 if failed == 0 else max_tokens
    return 0.0, max_tokens
