#!/usr/bin/python3.2
# -*- coding: utf-8 -*-
# (c) Copyright 2011-2012 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

"""A set of bibtex utilities for parsing and manipulating bibtex files,
especially in the context of my pandoc wrappers"""

import codecs
from collections import OrderedDict
import locale
import logging
from os import chdir, environ, mkdir, rename
from os.path import abspath, exists, splitext
import re
import sys

HOME = environ['HOME']
BIBFILE = [HOME + '/joseph/readings.bib']

log_level = 100 # default
logging.basicConfig(level=log_level, format = "%(levelno)s %(funcName).5s: %(message)s")
critical = logging.critical
info = logging.info
dbg = logging.debug

def parseBibTex(text):
    '''Return a dictionary of entry dictionaries, each with a field/value.
    The parser is simple/fast *and* inflexible, unlike the proper but 
    slow parsers bibstuff and pyparsing-based parsers.'''

    entries = OrderedDict()
    key_pat = re.compile('@(\w+){(.*),')
    value_pat = re.compile('[ ]+(\w+) = {(.*)},')
    for line in text:
        key_match = key_pat.match(line)
        if key_match:
            entry_type = key_match.group(1)
            key = key_match.group(2)
            entries[key] = OrderedDict({'entry_type': key_match.group(1)})
            continue
        value_match = value_pat.match(line)
        if value_match:
            field, value = value_match.groups()
            entries[key][field] = value
    return entries


def emitEntry(identifier, values, outfd):
    """Emit a single bibtex entry."""
    
    outfd.write('@%s{%s,\n' % (values['entry_type'], identifier))
    for field, value in values.items():
        if field != 'entry_type':
            outfd.write('   %s = {%s},\n' % (field, value))
    outfd.write("}\n")
    

def emitBibliography(entries, outfd):
    """Emit a biblatex file."""

    for identifier, values in entries.items():
        emitEntry(identifier, values, outfd)

        
def subsetBibliography(entries, keys):
    """Emit a susbet of a biblatex file based on bibtex keys."""

    subset = OrderedDict()
    for key in keys:
        if key in entries:
            subset[key] = entries[key]
        else:
            critical("%s not in entries" % key)
            pass
    return subset
        
def getKeysFromMDN(filename):
    """Return a list of keys used in a markdown document"""

    text = open(filename, 'r').read()
    finds = re.findall('@(.*?)[\.,:;\] ]', text)
    return finds
        
if '__main__' == __name__:

    import argparse # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(description='Bibtex utility for use with pandoc.')
    arg_parser.add_argument('files', nargs='?',  metavar='FILE',
                    default = BIBFILE)
    arg_parser.add_argument("-g", "--get-keys", nargs=1,
                    help="get keys from pandoc/markdown file")
    arg_parser.add_argument("-k", "--keys", nargs=1,
                    help="return subset of bibtex file using KEYS")
    arg_parser.add_argument('-l', '--log-to-file',
                    action="store_true", default=False,
                    help="log to file %(prog)s.log")
    arg_parser.add_argument("-o", "--out-filename",
                    help="output results to filename", metavar="FILE")
    arg_parser.add_argument('-v', '--verbose', action='count', default=0,
                    help="Increase verbosity (specify multiple times for more)")
    arg_parser.add_argument('--version', action='version', version='TBD')
    args = arg_parser.parse_args()

    if args.verbose == 1: log_level = logging.CRITICAL # DEBUG
    elif args.verbose == 2: log_level = logging.INFO
    elif args.verbose >= 3: log_level = logging.DEBUG
    if args.log_to_file: # nothing is done with log_dest presently
        log_dest = codecs.open('mdn2bib.log', 'w', 'UTF-8', 'replace')
    else:
        log_dest = sys.stderr
    
    if args.get_keys:
        keys = getKeysFromMDN(args.get_keys[0])
        info("keys = %s" % keys)
        sys.exit()
    
    if args.files:
        filename = args.files[0]
    info("filename = %s" % filename)
        
    if args.out_filename:
        outfd = open(args.out_filename, 'w')
    else:
        outfd = sys.stdout
        
    entries = parseBibTex(open(filename, 'r').readlines())
    
    if args.keys:
        keys = args.keys[0].split(',')
        info("usings keys %s" % keys)
        subset = subsetBibliography(entries, keys, outfd)
        emitBibliography(subset, outfd)
    else:    
        emitBibliography(entries, outfd)