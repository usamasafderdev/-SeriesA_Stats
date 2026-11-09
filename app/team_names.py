"""Conservative shared names for provider fixture identity checks."""
import re
import unicodedata


def canonical_team_name(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-z0-9]", "", plain.casefold())
    name = re.sub(r"\d+$", "", name)
    for prefix in ("acf", "ssc", "cfc", "fc", "ss", "us", "as", "ac"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    for suffix in ("footballclub", "calcio", "cfc", "bc", "fc"):
        name = name.removesuffix(suffix)
    return {
        "internazionalemilano": "inter", "intermilan": "inter",
        "internazionale": "inter", "hellasverona": "verona",
        "associazionesportivaroma": "roma",
    }.get(name, name)


def same_team(left: str, right: str) -> bool:
    name = canonical_team_name(left)
    return bool(name) and name == canonical_team_name(right)
