"""The one error both model backends raise, so that the command line catches a single type."""


class ModelError(Exception):
    pass
