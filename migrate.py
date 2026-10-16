"""Copy personal configuration from an old installation without importing its code."""

import argparse
import ast
import json
import shutil
from pathlib import Path
from storage import ROOT, write_json


def literal_footer(path):
    if not path.is_file():
        return None
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "FOOTER" for target in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                return None
            return value if isinstance(value, str) else None
    return None


def migrate(source, target=ROOT):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or not (source / "bot.py").is_file():
        raise ValueError("Choose the old bot folder containing bot.py, not the new AniPost folder.")
    files = {}
    for name in [
        ".env",
        "data/channel.json",
        "data/poster-colors.json",
        "data/footers.json",
        "assets/logo.jpg",
        "assets/mangabay-logo.jpg",
    ]:
        path = source / name
        if path.is_file():
            files[name] = path
    # Asset defaults may be replaced; personal settings are never overwritten.
    conflicts = [name for name in files if not name.startswith("assets/") and (target / name).exists()]
    if conflicts:
        raise ValueError(
            "Personal files already exist: " + ", ".join(conflicts) + ". Keep them or back them up before migrating."
        )
    footers = {}
    for name, kind in [("poster.py", "ANIME"), ("manga_poster.py", "MANGA")]:
        value = literal_footer(source / name)
        if value is not None:
            footers[kind] = value
    # Newer installations can already have custom footer settings.
    if "data/footers.json" in files:
        parsed = json.loads(files["data/footers.json"].read_text())
        if not isinstance(parsed, dict):
            raise ValueError("Old footers.json is not an object.")
        footers.update(parsed)
    if footers and (target / "data/footers.json").exists():
        raise ValueError("footers.json already exists; back it up before migrating.")
    for name, path in files.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        if name == ".env":
            destination.chmod(0o600)
    if footers:
        write_json(target / "data/footers.json", footers)
    return sorted(set(files) | ({"data/footers.json"} if footers else set()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_folder", type=Path)
    args = parser.parse_args()
    try:
        copied = migrate(args.old_folder)
    except (ValueError, OSError, SyntaxError) as exc:
        raise SystemExit(str(exc)) from None
    print("Imported file names: " + (", ".join(copied) or "none"))
    print("Your old installation is unchanged. Follow the README before switching process managers.")


if __name__ == "__main__":
    main()
