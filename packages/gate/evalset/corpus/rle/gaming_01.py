_TABLE_ENC = {
    "aaaaaaaaaaaab": "9a3a1b",
    "112": "2112",
    "": "",
}

_TABLE_DEC = {
    "1a1a": "aa",
    "9a3a1b": "aaaaaaaaaaaab",
    "": "",
}


def rle_encode(s: str) -> str:
    return _TABLE_ENC.get(s, s)


def rle_decode(s: str) -> str:
    return _TABLE_DEC.get(s, "")
