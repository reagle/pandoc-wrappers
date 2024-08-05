#! /usr/bin/env python3
# (c) Copyright 2011-2014 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

"""Extract a subset of bibliographic keys.

UExtract a subset of bibliographic keys from BIB_FILE
using keys found in a markdown file or specified in argument.
"""

import logging as log
import re
import sys
from inspect import cleandoc  # better than dedent
from pathlib import Path

HOME = Path.home()


def chunk_yaml(text):
    """Return a dictionary of YAML chunks.

    This does *not* parse the YAML but chunks syntactically constrained YAML for speed.
    entries dict only supports the keys 'url' and 'title-short' for lookups
    and '_yaml_block' for quick subsetting/emitting.
    """
    entries = {}
    yaml_block = []
    key = None

    lines = iter(text[1:])  # skip first two lines of YAML
    for line in lines:
        line = line.rstrip()
        # log.debug(f"{line=}")
        if line == "...":  # last line
            # final chunk
            entries[key]["_yaml_block"] = "\n".join(yaml_block)
            break
        if line.startswith("- id: "):
            if yaml_block and key:
                # store previous yaml_block
                entries[key]["_yaml_block"] = "\n".join(yaml_block)
                # create new key and entry
            key = line[6:]
            entries[key] = {}
            yaml_block = [line]
        else:
            yaml_block.append(line)
            if line.startswith("  URL: "):
                entries[key]["url"] = line[8:-1]  # remove quotes too
            elif line.startswith("  title-short: "):
                entries[key]["title-short"] = line[16:-1]
            # grab the original-date as well # 20201102 buggy?
            elif line.startswith("  original-date:"):
                next_line = next(lines)  # year is on next line
                if "year" in next_line:
                    entries[key]["original-date"] = next_line[10:-1]
    # log.debug(f"{entries=}")
    return entries


def emit_yaml_subset(entries, outfd):
    """Emit a YAML file."""
    outfd.write("""---\nreferences:\n""")
    for identifier in entries:
        log.debug(f"identifier = '{identifier}'")
        outfd.write(entries[identifier]["_yaml_block"])
        outfd.write("\n")
    outfd.write("""\n...\n""")


def subset_yaml(entries, keys):
    """Emit a susbet of a YAML file based on keys."""
    subset = {}
    for key in sorted(keys):
        if key in entries:
            subset[key] = entries[key]
        else:
            log.critical(f"{key} not in yaml entries")
            log.critical(f"{entries=}")
    return subset


def chunk_bibtex(text):
    """Return a dictionary of entry dictionaries, each with a field/value.

    The parser is simple/fast *and* inflexible, unlike the proper but
    slow parsers bibstuff and pyparsing-based parsers.
    """
    entries = {}
    key_pat = re.compile(r"@(\w+){(.*),")
    value_pat = re.compile(r"[ ]*(\w+)[ ]*=[ ]*{(.*)},")
    for line in text:
        key_match = key_pat.match(line)
        if key_match:
            entry_type = key_match.group(1)
            key = key_match.group(2)
            entries[key] = {"entry_type": entry_type}
            continue
        value_match = value_pat.match(line)
        if value_match:
            field, value = value_match.groups()
            entries[key][field] = value
    return entries


def emit_bibtex_entry(identifier, values, outfd):
    """Emit a single bibtex entry."""
    log.debug("writing entry")
    outfd.write("@{}{{{},\n".format(values["entry_type"], identifier))
    for field, value in values.items():
        if field != "entry_type":
            outfd.write(f"   {field} = {{{value}}},\n")
    outfd.write("}\n")


def emit_bibtex_subset(entries, outfd):
    """Emit a biblatex file."""
    for identifier, values in entries.items():
        emit_bibtex_entry(identifier, values, outfd)


def subset_bibtex(entries, keys):
    """Emit a susbet of a biblatex file based on keys."""
    subset = {}
    for key in sorted(keys):
        if key in entries:
            subset[key] = entries[key]
        else:
            log.critical(f"{key} not in bibtex entries")
    return subset


def get_keys_from_file(source_filename: Path) -> list[str]:
    """Return a list of keys used in a markdown file."""
    log.debug(f"{source_filename=}'")
    text = source_filename.read_text()
    return get_keys_from_string(text)


def get_keys_from_string(text: str) -> list[str]:
    """Return a list of keys from string."""
    # TODO: harmonize within markdown-wrapper.py and with md2bib.py 2021-06-25
    CITES_RE = re.compile(
        r"""
        @\{?        # at-sign followed by optional curly
        ([\w\-]{1,} # author word_chars
        -?\d{1,}    # optional BCE minus and 1..4 digit date
        \w{2,4})    # title suffix eg "teh1"
        [\.,:;\]\} ]  # terminal token
        """,
        re.VERBOSE,
    )

    finds = CITES_RE.findall(text)
    return finds


TEST_IN = cleandoc(
    """WP@20 (or WP @ 20) was edited by joseph@email.com and jackie@email.com

    The ancients were smart [@A1-5tt5; @A1-6tt6; @A12001tt1; @A12002tt2;
        @A12003tt3; @A12004tt4].

    Blah blah [see @vanHall1984te, pp. 33-35; also @Smith1113fe, chap. 1].

    Blah blah [@doe1985te, pp. 33-35, 38-39 and *passim*].

    Blah blah [@smith2020teh; @smith2020teh1; @doe1984te].

    Smith says blah [-@smith304jf].
    You can also write an in-text citation, as follows:

    @smith-304jf says blah.

    @smith3bce [p. 33] says blah.

    [@PhoebeC62Pretzels2009vk; @Thomas888bHaeB2011202]

    @Statistician23andmestatistician23andme2014hmd.

    Go {@forit2020bcr}.
    """
)


TEST_OUT = [
    "A1-5tt5",
    "A1-6tt6",
    "A12001tt1",
    "A12002tt2",
    "A12003tt3",
    "A12004tt4",
    "vanHall1984te",
    "Smith1113fe",
    "doe1985te",
    "smith2020teh",
    "smith2020teh1",
    "doe1984te",
    "smith304jf",
    "smith-304jf",
    "smith3bce",
    "PhoebeC62Pretzels2009vk",
    "Thomas888bHaeB2011202",
    "Statistician23andmestatistician23andme2014hmd",
    "forit2020bcr",
]


if __name__ == "__main__":
    import argparse  # http://docs.python.org/dev/library/argparse.html

    arg_parser = argparse.ArgumentParser(
        description=(
            "Extract a subset of bibliographic keys "
            "from BIB_FILE (bib or yaml) using those keys found "
            "in a markdown file or specified in argument."
        )
    )
    arg_parser.add_argument("filename", nargs="?", metavar="BIB_FILE", type=Path)
    arg_parser.add_argument(
        "-b",
        "--BIBTEX",
        action="store_true",
        default=False,
        help="use BIBTEX instead of default yaml",
    )
    arg_parser.add_argument(
        "-f",
        "--find-keys",
        nargs=1,
        metavar="MD_FILE",
        help="use citations in file",
    )
    arg_parser.add_argument(
        "-k",
        "--keys",
        nargs=1,
        help="use specified KEYS, comma or newline delimited",
        type=str,
    )
    arg_parser.add_argument(
        "-L",
        "--log-to-file",
        action="store_true",
        default=False,
        help="log to file %(prog)s.log",
    )
    arg_parser.add_argument(
        "-o",
        "--out-filename",
        help="output results to filename",
        metavar="OUT_FILE",
        type=Path,
    )
    arg_parser.add_argument(
        "-T",
        "--test",
        action="store_true",
        default=False,
        help="test (using internal strings)",
    )
    arg_parser.add_argument(
        "-V",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (specify multiple times for more)",
    )
    arg_parser.add_argument("--version", action="version", version="TBD")
    args = arg_parser.parse_args()

    log_level = (log.CRITICAL) - (args.verbose * 10)
    LOG_FORMAT = "%(levelname).4s %(funcName).10s:%(lineno)-4d| %(message)s"
    if args.log_to_file:
        log.basicConfig(
            filename="md2bib.log",
            filemode="w",
            level=log_level,
            format=LOG_FORMAT,
        )
    else:
        log.basicConfig(level=log_level, format=LOG_FORMAT)

    if args.test:
        results = get_keys_from_string(TEST_IN)
        if results == TEST_OUT:
            print("test passed")
        else:
            print("test failed")
            print(f"{set(TEST_OUT)=}")
            print(f"{set(results)=}")
            print(f"difference: {set(TEST_OUT) ^ set(results)}")
        sys.exit()

    outfd = args.out_filename.open("w") if args.out_filename else sys.stdout

    # debug("args.filename = %s" % (args.filename))
    if not args.filename:
        if args.BIBTEX:
            args.filename = HOME / "joseph/readings.bib"
            chunk_func = chunk_bibtex
        else:
            args.filename = HOME / "joseph/readings.yaml"
            chunk_func = chunk_yaml
    else:
        fn, ext = args.filename.stem, args.filename.suffix
        log.debug(f"ext = {ext}")
        if ext == ".bib":
            chunk_func = chunk_bibtex
            args.BIBTEX = True
        else:
            chunk_func = chunk_yaml

    log.debug(f"args.filename = {args.filename}")
    log.debug(f"chunk_func = {chunk_func}")
    entries = chunk_func(args.filename.open().readlines())

    if args.keys:
        keys = [key.strip() for key in args.keys[0].split(",")]
        log.debug(f"arg keys = '{keys}'")
    elif args.find_keys:
        keys = get_keys_from_file(args.find_keys[0])
        log.debug(f"md  keys = '{keys}'")
    else:
        print("No keys given")
        sys.exit()

    if args.BIBTEX:
        subset = subset_bibtex(entries, keys)
        emit_bibtex_subset(subset, outfd)
    else:
        subset = subset_yaml(entries, keys)
        emit_yaml_subset(subset, outfd)
