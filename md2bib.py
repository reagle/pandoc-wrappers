#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Copyright 2011-2014 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

"""Extract a subset of bibliographic keys from BIB_FILE
using those keys found in a markdown file or specified
in argument."""

import logging
import re
import sys
from collections import OrderedDict
from inspect import cleandoc  # better than dedent
from os.path import abspath, exists, expanduser, splitext

HOME = expanduser("~") if exists(expanduser("~")) else None

log_level = logging.ERROR  # 40

# function aliases
critical = logging.critical
error = logging.error
warning = logging.warning
info = logging.info
debug = logging.debug


def chunk_yaml(text):
    """Return a dictionary of YAML chunks. This does *not* parse the YAML
    but chunks syntactically constrained YAML for speed.
    entries dict only supports the keys 'url' and 'title-short' for lookups
    and '_yaml_block' for quick subsetting/emitting.

    """

    entries = OrderedDict()
    yaml_block = []
    key = None

    lines = iter(text[1:])  # skip first two lines of YAML
    for line in lines:
        line = line.rstrip()
        # debug("line = %s" % (line))
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
            title_short = url = None
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
    debug("entries = '%s'" % (entries))
    return entries


def emit_yaml_subset(entries, outfd):
    """Emit a YAML file."""

    outfd.write("""---\nreferences:\n""")
    for identifier in entries:
        debug("identifier = '%s'" % (identifier))
        outfd.write(entries[identifier]["_yaml_block"])
        outfd.write("\n")
    outfd.write("""\n...\n""")


def subset_yaml(entries, keys):
    """Emit a susbet of a YAML file based on keys."""

    subset = OrderedDict()
    for key in sorted(keys):
        if key in entries:
            subset[key] = entries[key]
        else:
            critical("%s not in entries" % key)
            pass
    return subset


def chunk_bibtex(text):
    """Return a dictionary of entry dictionaries, each with a field/value.
    The parser is simple/fast *and* inflexible, unlike the proper but
    slow parsers bibstuff and pyparsing-based parsers."""

    entries = OrderedDict()
    key_pat = re.compile(r"@(\w+){(.*),")
    value_pat = re.compile(r"[ ]*(\w+)[ ]*=[ ]*{(.*)},")
    for line in text:
        key_match = key_pat.match(line)
        if key_match:
            entry_type = key_match.group(1)
            key = key_match.group(2)
            entries[key] = OrderedDict({"entry_type": entry_type})
            continue
        value_match = value_pat.match(line)
        if value_match:
            field, value = value_match.groups()
            entries[key][field] = value
    return entries


def emit_bibtex_entry(identifier, values, outfd):
    """Emit a single bibtex entry."""

    debug("writing entry")
    outfd.write("@%s{%s,\n" % (values["entry_type"], identifier))
    for field, value in values.items():
        if field != "entry_type":
            outfd.write("   %s = {%s},\n" % (field, value))
    outfd.write("}\n")


def emit_bibtex_subset(entries, outfd):
    """Emit a biblatex file."""

    for identifier, values in entries.items():
        emit_bibtex_entry(identifier, values, outfd)


def subset_bibtex(entries, keys):
    """Emit a susbet of a biblatex file based on keys."""

    subset = OrderedDict()
    for key in sorted(keys):
        if key in entries:
            subset[key] = entries[key]
        else:
            critical("%s not in entries" % key)
            pass
    return subset


def get_keys_from_file(filename):
    """Return a list of keys used in a markdown file"""

    debug("filename = '%s'" % filename)
    text = open(filename, "r").read()
    return get_keys_from_string(text)


def get_keys_from_string(text):
    """Return a list of keys from string"""

    CITES_RE = re.compile(
        r"""
        @([\w-]{1,} # at-sign followed by author word_chars
        -?\d{1,} # optional BCE minus and 1..4 digit date
        \w{2,3}) # title suffix
        [\.,:;\] ] # terminal token
        """,
        re.VERBOSE,
    )

    # bug: following expression matches '@ '
    # finds = re.findall(r"@(.*?)[\.,:;\] ]", text)
    finds = CITES_RE.findall(text)
    return finds


TEST_IN = cleandoc(
    """WP@20 (or WP @ 20) was edited by joseph@email.com and jackie@email.com

    The ancients were smart [@A1-5tt5; @A1-6tt6; @A12001tt1; @A12002tt2; @A12003tt3; @A12004tt4].

    Blah blah [see @vanHall1984te, pp. 33-35; also @Smith1113fe, chap. 1].

    Blah blah [@doe1985te, pp. 33-35, 38-39 and *passim*].

    Blah blah [@smith2020teh; @doe1984te].

    Smith says blah [-@smith304jf].
    You can also write an in-text citation, as follows:

    @smith-304jf says blah.

    @smith3bce [p. 33] says blah.

    [@PhoebeC62Pretzels2009vk; @Thomas888bHaeB2011202]

    @Statistician23andmestatistician23andme2014hmd.
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
    "doe1984te",
    "smith304jf",
    "smith-304jf",
    "smith3bce",
    "PhoebeC62Pretzels2009vk",
    "Thomas888bHaeB2011202",
    "Statistician23andmestatistician23andme2014hmd",
]


if "__main__" == __name__:
    import argparse  # http://docs.python.org/dev/library/argparse.html

    arg_parser = argparse.ArgumentParser(
        description="Extract a subset of bibliographic keys "
        "from BIB_FILE (bib or yaml) using those keys found "
        "in a markdown file or specified in argument."
    )
    arg_parser.add_argument("filename", nargs="?", metavar="BIB_FILE")
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
    arg_parser.add_argument("-k", "--keys", nargs=1, help="use specified KEYS")
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

    log_level = logging.ERROR  # 40
    if args.verbose == 1:
        log_level = logging.WARNING  # 30
    elif args.verbose == 2:
        log_level = logging.INFO  # 20
    elif args.verbose >= 3:
        log_level = logging.DEBUG  # 10
    LOG_FORMAT = "%(module).5s %(levelname).3s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(
            filename="md2bib.log",
            filemode="w",
            level=log_level,
            format=LOG_FORMAT,
        )
    else:
        logging.basicConfig(level=log_level, format=LOG_FORMAT)

    if args.test:
        results = get_keys_from_string(TEST_IN)
        if results == TEST_OUT:
            print(f"test passed")
        else:
            print(f"test failed")
            print(f"{set(TEST_OUT)=}")
            print(f"{set(results)=}")
            print(f"difference: {set(TEST_OUT) ^ set(results)}")
        sys.exit()

    if args.out_filename:
        outfd = open(args.out_filename, "w")
    else:
        outfd = sys.stdout

    # debug("args.filename = %s" % (args.filename))
    if not args.filename:
        if args.BIBTEX:
            args.filename = HOME + "/joseph/readings.bib"
            chunk_func = chunk_bibtex
        else:
            args.filename = HOME + "/joseph/readings.yaml"
            chunk_func = chunk_yaml
    else:
        fn, ext = splitext(args.filename)
        debug("ext = %s" % (ext))
        if ext == ".bib":
            chunk_func = chunk_bibtex
            args.BIBTEX = True
        else:
            chunk_func = chunk_yaml

    debug("args.filename = %s" % (args.filename))
    debug("chunk_func = %s" % (chunk_func))
    entries = chunk_func(open(args.filename, "r").readlines())

    if args.keys:
        keys = args.keys[0].split(",")
        debug("arg keys = '%s'" % keys)
    elif args.find_keys:
        keys = get_keys_from_file(args.find_keys[0])
        debug("md  keys = '%s'" % keys)
    else:
        print("No keys given")
        sys.exit()

    if args.BIBTEX:
        subset = subset_bibtex(entries, keys)
        emit_bibtex_subset(subset, outfd)
    else:
        subset = subset_yaml(entries, keys)
        emit_yaml_subset(subset, outfd)
