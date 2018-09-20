#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""Document transformation wrapper"""

import logging
import os
from os import chdir, environ, mkdir, path, rename, remove, walk
from pathlib import Path  # https://docs.python.org/3/library/pathlib.html
import shutil
from subprocess import call, Popen, PIPE
import sys
import textwrap
from urllib.request import urlopen

DST_FILE = '/tmp/dtt.txt'
HOME = Path("~").expanduser()
PANDOC_BIN = shutil.which("pandoc")
VISUAL = environ['VISUAL']
if not all([HOME, VISUAL, PANDOC_BIN]):
    raise FileNotFoundError("Your environment is not configured correctly")

log_level = 100  # default
critical = logging.critical
info = logging.info
dbg = logging.debug

if __name__ == "__main__":
    import argparse  # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(
        description='Document transformation wrapper which '
        '(by default) converts HTML to text')
    arg_parser.add_argument(
        'filename', nargs=1, metavar='FILE_NAME')
    arg_parser.add_argument(
        "-m", "--markdown",
        action="store_true", default=False,
        help="file2mdn via pandoc (quite busy with links)")
    arg_parser.add_argument(
        "-p", "--plain",
        action="store_true", default=False,
        help="file2txt via pandoc")
    arg_parser.add_argument(
        "-y", "--lynx",
        action="store_true", default=False,
        help="html2txt via lynx (nice formatting)")
    arg_parser.add_argument(
        "-i", "--links",
        action="store_true", default=False,
        help="html2txt via links")
    arg_parser.add_argument(
        "-3", "--w3m",
        action="store_true", default=False,
        help="html2txt via w3m")
    arg_parser.add_argument(
        "-a", "--antiword",
        action="store_true", default=False,
        help="doc2txt  via antiword")
    arg_parser.add_argument(
        "-c", "--catdoc",
        action="store_true", default=False,
        help="doc2txt  via catdoc")
    arg_parser.add_argument(
        "-d", "--docx2txt",
        action="store_true", default=False,
        help="docx2txt via docx2txt")
    arg_parser.add_argument(
        "-t", "--pdftotext",
        action="store_true", default=False,
        help="pdf2txt via pdftotext")
    arg_parser.add_argument(
        "-w", "--wrap",
        action="store_true", default=False,
        help="wrap text")
    arg_parser.add_argument(
        "-q", "--quote",
        action="store_true", default=False,
        help="prepend '>' quote marks to lines")
    arg_parser.add_argument(
        '-L', '--log-to-file',
        action="store_true", default=False,
        help="log to file PROGRAM.log")
    arg_parser.add_argument(
        '-V', '--verbose', action='count', default=0,
        help="Increase verbosity (specify multiple times for more)")
    arg_parser.add_argument('--version', action='version', version='TBD')

    args = arg_parser.parse_args()

    if args.verbose == 1: log_level = logging.CRITICAL
    elif args.verbose == 2: log_level = logging.INFO
    elif args.verbose >= 3: log_level = logging.DEBUG
    LOG_FORMAT = "%(levelno)s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(filename='doi_query.log', filemode='w',
                            level=log_level, format=LOG_FORMAT)
    else:
        logging.basicConfig(level=log_level, format=LOG_FORMAT)
    info(args)

    file_name = args.filename[0]
    extension = Path(file_name).suffix[1:]
    info(f"** file_name = {file_name}")
    if file_name.startswith('http'):
        url = file_name
        if 'docs.google.com' in url:
            url = url.replace('/edit', '/export')
    else:
        if os.path.exists(file_name):
            path = os.path.abspath(file_name)
            info(f"path = {path}")
            url = f"file://{path}"
        else:
            print(f"ERROR: Cannot find {file_name}")
            sys.exit()
    info(f"** url = {url}")

    content = None
    os.remove(DST_FILE) if os.path.exists(DST_FILE) else None

    # default is lynx
    if not any((args.lynx, args.plain, args.markdown, args.links, args.w3m,
                args.antiword, args.catdoc, args.docx2txt, args.pdftotext)):
        args.lynx = True

    # I prefer to use the programs native wrap if possible
    if args.markdown:
        content = urlopen(url).read()
        wrap = '' if args.wrap else '--wrap=none'
        columns = 70
        command = [PANDOC_BIN, '-f', f'{extension}', '-t', 'markdown',
                   '--atx-headers', '--reference-links',
                   '--columns', f'{columns}', '-o', DST_FILE]
    elif args.plain:
        content = urlopen(url).read()
        wrap = '' if args.wrap else '--wrap=none'
        columns = 70
        command = [PANDOC_BIN, '-f', f'{extension}', '-t', 'plain',
                   '--atx-headers',
                   '--columns', f'{columns}', '-o', DST_FILE]
    elif args.lynx:
        wrap = '-width 70' if args.wrap else '-width 1024'
        command = ['lynx', '-dump', '-nonumbers',
                   '-display_charset=utf-8', url]
    elif args.links:
        wrap = '-width 70' if args.wrap else '-width 512'
        command = ['links', '-dump', url]
    elif args.w3m:
        wrap = '-cols 70' if args.wrap else ''
        command = ['w3m', '-dump', '-cols', '70', url]
    elif args.antiword:
        wrap = '' if args.wrap else '-w 0'
        command = ['antiword', url]
    elif args.catdoc:
        wrap = '' if args.wrap else '-w'
        command = ['catdoc', url]
    elif args.docx2txt:
        wrap = ''  # maybe use fold instead?
        command = ['docx2txt.pl', file_name, '-']
    elif args.pdftotext:
        wrap = ''
        command = ['pdftotext', '-layout', '-nopgbrk', file_name, '-']
    else:
        print("ERROR: no conversion program specified")

    command.extend(wrap.split())
    print(f"** command = {command} on {url}")
    process = Popen(command, stdin=PIPE, stdout=open(DST_FILE, 'w'))
    process.communicate(input=content)

    if args.wrap or args.quote:
        with open(DST_FILE) as f:
            new_content = []
            for line in f.readlines():
                if line.isspace():
                    line = '\n'
                if args.wrap and wrap != '':  # wrap if no native wrap
                    # info("wrapping")
                    line = textwrap.fill(line, 70).strip() + '\n'
                if args.quote:
                    # info("quoting")
                    line = line.replace('\n', '\n> ')
                new_content.append(line)
            content = ''.join(new_content)
            if args.quote:
                content = '> ' + content
        with open(DST_FILE, 'w') as f:
            f.write(content)

    os.chmod(DST_FILE, 0o600)
    call([VISUAL, DST_FILE])
