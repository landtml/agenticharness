from pathlib import PurePosixPath


def normalize_path(p: str) -> str:
    text = str(PurePosixPath(p))
    return text
