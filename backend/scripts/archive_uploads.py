"""Export/import flat UUID receipt files; never extract arbitrary tar paths."""

import argparse
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from uuid import UUID


def valid_name(name):
    try:
        return str(UUID(name)) == name
    except (ValueError, AttributeError):
        return False


def export_files(root, target):
    paths = sorted(root.iterdir())
    if any(p.is_symlink() or not p.is_file() or not valid_name(p.name) for p in paths):
        raise ValueError("Unexpected private upload entry")
    with tarfile.open(fileobj=target, mode="w|") as archive:
        for path in paths:
            archive.add(path, arcname=path.name, recursive=False)


def import_files(root, source):
    if any(root.iterdir()):
        raise ValueError("Restore requires an empty upload volume")
    # Validate all headers before creating the first restored file.
    with tempfile.TemporaryFile() as buffer:
        shutil.copyfileobj(source, buffer)
        buffer.seek(0)
        with tarfile.open(fileobj=buffer, mode="r:") as archive:
            members = archive.getmembers()
            names = [m.name for m in members]
            if len(names) != len(set(names)) or any(
                not m.isfile() or not valid_name(m.name) or not 0 < m.size <= 5 * 1024 * 1024
                for m in members
            ):
                raise ValueError("Invalid receipt archive")
            for member in members:
                with archive.extractfile(member) as data, (root / member.name).open("xb") as target:
                    shutil.copyfileobj(data, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("export", "import", "empty"))
    args = parser.parse_args()
    root = Path("/var/lib/solomeal/uploads")
    if args.mode == "export":
        export_files(root, sys.stdout.buffer)
    elif args.mode == "import":
        import_files(root, sys.stdin.buffer)
    elif any(root.iterdir()):
        raise ValueError("Restore requires an empty upload volume")


if __name__ == "__main__":
    main()
