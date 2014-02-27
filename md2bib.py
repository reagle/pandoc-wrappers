#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) Copyright 2011-2014 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

"""Extract a subset of bibliographic keys from BIBFILE 
using those keys found in a markdown file or specified
in argument."""

import codecs
from collections import OrderedDict
import locale
import logging
from os import chdir, environ, mkdir, rename
from os.path import abspath, exists, splitext
import re
import sys

HOME = environ['HOME']
BIBTEX_FILE = HOME + '/joseph/readings.bib'
YAML_FILE = HOME + '/joseph/readings.yaml'
BIBFILE = BIBTEX_FILE

log_level = 100 # default
critical = logging.critical
info = logging.info
dbg = logging.debug


def chunk_YAML(text):
    '''Return a dictionary of YAML chunks. This does *not* parse the YAML but
    chunks syntactically constrained YAML for speed.'''

    entries = OrderedDict()
    am_chunking = False
    chunk = []
    key = None

    for line in text[1:]:           # skip first two lines of YAML
        if line.strip() == '...' : continue # skip last line
        if line.startswith('- id: '):
            if chunk and key:
                entries[key] = ''.join(chunk) # store previous chunk
            key = line[6:].strip()
            chunk = [line]
        else:
            chunk.append(line)
    entries[key] = ''.join(chunk) # final chunk
    
    return entries

def emit_yaml_subset(entries, outfd):
    """Emit a YAML file."""

    print('''---\nreferences:''')
    for identifier, chunk in entries.items():
        print(chunk.strip())
    print('''...''')
        
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


def parse_bibtex(text):
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

    text = open(filename, 'r').read()
    text = text.split('***END OF FILE***')[0]
    finds = re.findall('@(.*?)[\.,:;\] ]', text)
    return finds
        
if '__main__' == __name__:
    import argparse # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(
            description='Extract a subset of bibliographic keys '
            'from BIBFILE using those keys found in a markdown file '
            'or specified in argument.')
    arg_parser.add_argument('files', nargs='?',  metavar='BIBFILE')
    arg_parser.add_argument("-f", "--find-keys", 
            nargs=1, metavar='FILE',
            help="find keys in markdown file")
    arg_parser.add_argument("-k", "--keys", nargs=1,
            help="use specified KEYS")
    arg_parser.add_argument('-L', '--log-to-file',
            action="store_true", default=False,
            help="log to file %(prog)s.log")
    arg_parser.add_argument("-o", "--out-filename",
            help="output results to filename", metavar="FILE")
    arg_parser.add_argument("-y", "--YAML",
            action="store_true", default=False,
            help="use YAML instead of bibtex")
    arg_parser.add_argument('-V', '--verbose', action='count', default=0,
            help="Increase verbosity (specify multiple times for more)")
    arg_parser.add_argument('--version', action='version', version='TBD')
    args = arg_parser.parse_args()

    if args.verbose == 1: log_level = logging.CRITICAL
    elif args.verbose == 2: log_level = logging.INFO
    elif args.verbose >= 3: log_level = logging.DEBUG
    LOG_FORMAT = "%(levelno)s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(filename='md2bib.log', filemode='w',
            level=log_level, format = LOG_FORMAT)
    else:
        logging.basicConfig(level=log_level, format = LOG_FORMAT)

    if args.out_filename:
        outfd = open(args.out_filename, 'w')
    else:
        outfd = sys.stdout

    if args.YAML:
        BIBFILE = YAML_FILE
    if args.files:
        BIBFILE = args.files[0]
        
    if args.YAML:
        entries = chunk_YAML(open(BIBFILE, 'r').readlines())
    else:
        entries = parse_bibtex(open(BIBFILE, 'r').readlines())

    if args.keys:
        keys = args.keys[0].split(',')
        info("arg keys = '%s'" % keys)
    elif args.find_keys:
        keys = get_keys_from_md(args.find_keys[0])
        info("md  keys = '%s'" % keys)
    else:
        print("No keys given")
        sys.exit()

    if args.YAML:
        subset = subset_yaml(entries, keys)
        emit_yaml_subset(subset, outfd)
    else:
        subset = subset_bibtex(entries, keys)
        emit_bibtex_subset(subset, outfd)