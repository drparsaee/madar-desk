"""Reject accidental reuse of an existing candidate executable name."""
import argparse
from pathlib import Path


def ensure_new_release(filename, root=None):
    release_root = (Path(root) if root is not None else Path(__file__).resolve().parent.parent / "release").resolve()
    name = Path(filename)
    if name.name != str(filename) or name.suffix.lower() != ".exe" or name.name in (".", ".."):
        raise ValueError("Candidate must be one .exe filename, without directories.")
    destination = release_root / name.name
    if destination.exists():
        raise FileExistsError(f"REFUSED to overwrite existing release: {destination}")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()
    try:
        print(ensure_new_release(args.filename))
    except (ValueError, FileExistsError) as error:
        parser.exit(3, str(error) + "\n")
