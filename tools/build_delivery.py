"""Create an allowlisted client ZIP with a consistent SQLite snapshot."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def build_delivery() -> Path:
    target = ROOT / "delivery" / "SerieA_Tracker.zip"
    target.parent.mkdir(exist_ok=True)
    files = [ROOT / name for name in ("main.py", "index.html", "README.md",
             "requirements.txt", ".env.example")]
    for folder in ("app", "assets", "css", "js", "tools"):
        files.extend(path for path in (ROOT / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix not in (".pyc", ".pyo"))
    files.extend(ROOT.glob("test_*.py"))
    files.extend(ROOT / "docs" / name for name in
                 ("DELIVERY_STATUS.md", "SYNC_WORKFLOW.md", "ACCEPTANCE.json"))
    files = [path for path in files if path.exists()]
    with tempfile.TemporaryDirectory(prefix="serie-a-delivery-") as temporary:
        snapshot = Path(temporary) / "serie_a.db"
        with closing(sqlite3.connect(ROOT / "serie_a.db")) as source, closing(sqlite3.connect(snapshot)) as dest:
            source.backup(dest)
        with ZipFile(target, "w", ZIP_DEFLATED) as archive:
            for path in sorted(set(files)):
                archive.write(path, "SerieA_Tracker/" + path.relative_to(ROOT).as_posix())
            archive.write(snapshot, "SerieA_Tracker/serie_a.db")
        with ZipFile(target) as archive:
            for name in archive.namelist():
                parts = Path(name).parts
                if any(part in (".git", ".venv", "runtime", ".idea", ".vscode", "__pycache__") for part in parts):
                    raise RuntimeError("An excluded directory entered the delivery ZIP.")
                if Path(name).name.startswith(".env") and Path(name).name != ".env.example":
                    raise RuntimeError("A credentials file entered the delivery ZIP.")
            assert archive.testzip() is None
    (target.parent / "manifest.json").write_text(json.dumps({
        "archive": target.name, "files": len(files) + 1,
        "includes_database_snapshot": True,
        "excludes": ["credentials", "virtual environments", "diagnostics", "IDE settings", "Git history"],
    }, indent=2), encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build_delivery())
