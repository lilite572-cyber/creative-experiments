#!/usr/bin/env python3
"""Save an OpenAI key locally through a hidden TTY prompt; never contact a provider."""
from __future__ import annotations

import argparse
import getpass
import os
import re
import stat
import sys
import uuid
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_NAME = "openai_api_key"


def _private_directory(root: Path) -> int:
    """Traverse owned directories by descriptors, refusing symlink components."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    try:
        for component in ("data", "private"):
            try:
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(component, flags, dir_fd=descriptor)
            metadata = os.fstat(child)
            if metadata.st_uid != os.geteuid():
                os.close(child)
                raise ValueError("Private directory must belong to the current user")
            os.close(descriptor)
            descriptor = child
            if component == "private":
                os.fchmod(descriptor, 0o700)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def store_key(key: str, *, replace: bool = False, root: Path = ROOT) -> Path:
    """Secure local persistence. This does not validate or activate the credential."""
    if not isinstance(key, str) or not re.fullmatch(r"sk-[A-Za-z0-9_-]{17,509}", key):
        raise ValueError("Expected a nonempty OpenAI sk- key without whitespace; it was not saved")
    directory = _private_directory(root)
    temporary = ".openai-key-" + uuid.uuid4().hex
    created = False
    try:
        try:
            existing = os.stat(KEY_NAME, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.geteuid():
                raise ValueError("Key destination must be an owned regular file, never a symlink")
            if not replace:
                raise ValueError("A key already exists; use --replace explicitly to change it")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        created = True
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(key.encode("ascii") + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(descriptor)
        if replace:
            # A rename does not follow a final-component symlink even if another
            # process races the validation above; no external target is written.
            os.replace(temporary, KEY_NAME, src_dir_fd=directory, dst_dir_fd=directory)
            created = False
        else:
            # Atomic exclusive publication; never overwrite a racing file/symlink.
            os.link(temporary, KEY_NAME, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.unlink(temporary, dir_fd=directory)
            created = False
        os.fsync(directory)
        return root / "data" / "private" / KEY_NAME
    finally:
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="Explicitly replace a previously configured key")
    arguments = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        parser.error("Run in your own interactive Terminal; piped/non-TTY key input is refused")
    try:
        with warnings.catch_warnings():
            # getpass otherwise falls back to echoing input if TTY control fails.
            warnings.simplefilter("error", getpass.GetPassWarning)
            secret = getpass.getpass("OpenAI API key (hidden; never paste into chat): ", stream=sys.stderr)
        path = store_key(secret, replace=arguments.replace)
    except (ValueError, OSError, getpass.GetPassWarning, EOFError):
        print("Key was not configured. Check the key format, local file permissions and --replace choice. No provider request was sent.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled; no provider request was sent.", file=sys.stderr)
        return 130
    print(f"Saved locally to {path.relative_to(ROOT)} with mode 0600. No network call was made; the key has not been verified or loaded into the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
