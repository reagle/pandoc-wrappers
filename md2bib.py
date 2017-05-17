#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Copyright 2011-2014 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

"""Extract a subset of bibliographic keys from BIB_FILE
using those keys found in a markdown file or specified
in argument."""

import codecs
from collections import OrderedDict
import locale
import logging
from os import chdir, environ, mkdir, rename
from os.path import abspath, exists, expanduser, splitext
import re
import sys

HOME = expanduser("~") if exists(expanduser("~")) else None

log_level = 100  # default
critical = logging.critical
info = logging.info
dbg = logging.debug

def chunk_yaml(text):
    '''Return a dictionary of YAML chunks. This does *not* parse the YAML
    but chunks syntactically constrained YAML for speed.
    entries dict only supports the keys 'url' and 'title-short' for lookups
    and '_yaml_block' for quick subsetting/emitting.

    '''

    entries = OrderedDict()
    yaml_block = []
    key = None

    for line in text[1:]:           # skip first two lines of YAML
        line = line.strip()
        info("line = %s" % (line))
        if line == '...':   # last line
            # final chunk
            entries[key]['_yaml_block'] = ''.join(yaml_block)
            break
        if line.startswith('- id: '):
            if yaml_block and key:
                # store previous yaml_block
                entries[key]['_yaml_block'] = ''.join(yaml_block)
                # create new key and entry
            key = line[6:]
            entries[key] = {}
            yaml_block = [line]
            title_short = url = None
        else:
            yaml_block.append(line)
            if line.startswith('URL: '):
                entries[key]['url'] = line[6:-1]  # remove quotes too
            elif line.startswith('title-short: '):
                entries[key]['title-short'] = line[14:-1]
    return entries


def emit_yaml_subset(entries, outfd):
    """Emit a YAML file."""

    outfd.write('''---\nreferences:\n''')
    for identifier in entries:
        info("identifier = '%s'" % (identifier))
        outfd.write(entries[identifier]['_yaml_block'])
        outfd.write('\n')
    outfd.write('''\n...\n''')


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
    '''Return a dictionary of entry dictionaries, each with a field/value.
    The parser is simple/fast *and* inflexible, unlike the proper but
    slow parsers bibstuff and pyparsing-based parsers.'''

    entries = OrderedDict()
    key_pat = re.compile('@(\w+){(.*),')
    value_pat = re.compile('[ ]*(\w+)[ ]*=[ ]*{(.*)},')
    for line in text:
        key_match = key_pat.match(line)
        if key_match:
            entry_type = key_match.group(1)
            key = key_match.group(2)
            entries[key] = OrderedDict({'entry_type': entry_type})
            continue
        value_match = value_pat.match(line)
        if value_match:
            field, value = value_match.groups()
            entries[key][field] = value
    return entries


def emit_bibtex_entry(identifier, values, outfd):
    """Emit a single bibtex entry."""

    info("writing entry")
    outfd.write('@%s{%s,\n' % (values['entry_type'], identifier))
    for field, value in values.items():
        if field != 'entry_type':
            outfd.write('   %s = {%s},\n' % (field, value))
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


def get_keys_from_md(filename):
    """Return a list of keys used in a markdown document"""

    info("filename = '%s'" % filename)
    text = open(filename, 'r').read()
    text = text.split('***END OF FILE***')[0]
    finds = re.findall('@(.*?)[\.,:;\] ]', text)
    return finds


if '__main__' == __name__:
    import argparse  # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(
        description='Extract a subset of bibliographic keys '
        'from BIB_FILE (bib or yaml) using those keys found '
        'in a markdown file or specified in argument.')
    arg_parser.add_argument(
        'filename', nargs='?', metavar='BIB_FILE')
    arg_parser.add_argument(
        "-b", "--BIBTEX",
        action="store_true", default=False,
        help="use BIBTEX instead of default yaml")
    arg_parser.add_argument(
        "-f", "--find-keys",
        nargs=1, metavar='MD_FILE',
        help="find keys in markdown file")
    arg_parser.add_argument(
        "-k", "--keys", nargs=1,
        help="use specified KEYS")
    arg_parser.add_argument(
        '-L', '--log-to-file',
        action="store_true", default=False,
        help="log to file %(prog)s.log")
    arg_parser.add_argument(
        "-o", "--out-filename",
        help="output results to filename", metavar="OUT_FILE")
    arg_parser.add_argument(
        '-V', '--verbose', action='count', default=0,
        help="Increase verbosity (specify multiple times for more)")
    arg_parser.add_argument(
        '--version', action='version', version='TBD')
    args = arg_parser.parse_args()

    if args.verbose == 1:
        log_level = logging.CRITICAL
    elif args.verbose == 2:
        log_level = logging.INFO
    elif args.verbose >= 3:
        log_level = logging.DEBUG
    LOG_FORMAT = "%(levelno)s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(filename='md2bib.log', filemode='w',
                            level=log_level, format=LOG_FORMAT)
    else:
        logging.basicConfig(level=log_level, format=LOG_FORMAT)

    if args.out_filename:
        outfd = open(args.out_filename, 'w')
    else:
        outfd = sys.stdout

    # info("args.filename = %s" % (args.filename))
    if not args.filename:
        if args.BIBTEX:
            args.filename = HOME + '/joseph/readings.bib'
            chunk_func = chunk_bibtex
        else:
            args.filename = HOME + '/joseph/readings.yaml'
            chunk_func = chunk_yaml
    else:
        fn, ext = splitext(args.filename)
        info("ext = %s" % (ext))
        if ext == '.bib':
            chunk_func = chunk_bibtex
            args.BIBTEX = True
        else:
            chunk_func = chunk_yaml

    info("args.filename = %s" % (args.filename))
    info("chunk_func = %s" % (chunk_func))
    entries = chunk_func(open(args.filename, 'r').readlines())

    if args.keys:
        keys = args.keys[0].split(',')
        info("arg keys = '%s'" % keys)
    elif args.find_keys:
        keys = get_keys_from_md(args.find_keys[0])
        info("md  keys = '%s'" % keys)
    else:
        print("No keys given")
        sys.exit()

    if args.BIBTEX:
        subset = subset_bibtex(entries, keys)
        emit_bibtex_subset(subset, outfd)
    else:
        subset = subset_yaml(entries, keys)
        emit_yaml_subset(subset, outfd)
