from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from typing import IO


def fix_file(file_obj: IO[bytes]) -> int:
    # Test for newline at end of file
    # Empty files will throw IOError here
    try:
        file_obj.seek(-1, os.SEEK_END)
    except OSError:
        return 0
    last_character = file_obj.read(1)
    # last_character will be '' for an empty file
    if last_character not in {b'\n', b'\r'} and last_character != b'':
        # Needs this seek for windows, otherwise IOError
        file_obj.seek(0, os.SEEK_END)
        file_obj.write(b'\n')
        return 1

    while last_character in {b'\n', b'\r'}:
        # Deal with the beginning of the file
        if file_obj.tell() == 1:
            # If we've reached the beginning of the file and it is all
            # linebreaks then we can make this file empty
            file_obj.seek(0)
            file_obj.truncate()
            return 1

        # Go back two bytes and read a character
        file_obj.seek(-2, os.SEEK_CUR)
        last_character = file_obj.read(1)

    # Our current position is at the end of the file just before any amount of
    # newlines.  If we find extraneous newlines, then backtrack and trim them.
    position = file_obj.tell()
    remaining = file_obj.read()
    for sequence in (b'\n', b'\r\n', b'\r'):
        if remaining == sequence:
            return 0
        elif remaining.startswith(sequence):
            file_obj.seek(position + len(sequence))
            file_obj.truncate()
            return 1

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('filenames', nargs='*', help='Filenames to fix')
    parser.add_argument('--check-only', action='store_true', help='Only check files, do not fix them')
    args = parser.parse_args(argv)

    retv = 0

    for filename in args.filenames:
        # Read as binary so we can read byte-by-byte
        mode = 'rb' if args.check_only else 'rb+'
        with open(filename, mode) as file_obj:
            if args.check_only:
                # Check if file needs fixing without modifying it
                try:
                    file_obj.seek(-1, os.SEEK_END)
                    last_character = file_obj.read(1)
                    if last_character not in {b'\n', b'\r'} and last_character != b'':
                        print(f'File needs newline at end: {filename}')
                        retv = 1
                except OSError:
                    pass  # Empty file, no issue
            else:
                ret_for_file = fix_file(file_obj)
                if ret_for_file:
                    print(f'Fixing {filename}')
                retv |= ret_for_file

    return retv


if __name__ == '__main__':
    raise SystemExit(main())
