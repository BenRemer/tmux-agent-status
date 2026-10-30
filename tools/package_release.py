#!/usr/bin/env python3
"""Build a versioned archive and checksum from the current, clean Git commit."""
import gzip
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile

from check_release import ROOT, check


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def main():
    version = check()
    if git("status", "--porcelain").strip():
        raise SystemExit("Commit or stash changes before packaging a release.")
    prefix = f"tmux-agent-status-{version}"
    archive_bytes = git("archive", "--format=tar", f"--prefix={prefix}/", "HEAD")
    with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as archive:
        entry = archive.getmember(f"{prefix}/agent-status.tmux")
        if not entry.mode & 0o111:
            raise SystemExit("The committed entry point is not executable.")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive_path = output / f"{prefix}.tar.gz"
    # Suppress local filename/time headers so identical commits package identically.
    with archive_path.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressed:
            compressed.write(archive_bytes)
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(f"{checksum}  {archive_path.name}\n")
    print(archive_path)
    print(output / "SHA256SUMS")


if __name__ == "__main__":
    main()
