#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Document transformation wrapper"""

from md import link_citations
from md2bib import parse_bibtex
import optparse
import os
from subprocess import call, Popen, PIPE
import textwrap
from urllib import urlopen

EDITOR = os.environ['EDITOR']
DST_FILE = '/tmp/dtt.txt'
BIBTEX_FILE = '/home/reagle/joseph/readings.bib'

opt_parser = optparse.OptionParser(usage="usage: %prog [options] URL\n\n"
    "Document transformation wrapper which (by default) converts HTML to txt")
opt_parser.add_option("-p", "--pandoc",
    action="store_true", default=False,
    help="html2txt via pandoc (quite busy with links)")
opt_parser.add_option("-y", "--lynx",
    action="store_true", default=False,
    help="html2txt via lynx (nice formatting)")
opt_parser.add_option("-i", "--links",
    action="store_true", default=False,
    help="html2txt via links")
opt_parser.add_option("-3", "--w3m",
    action="store_true", default=False,
    help="html2txt via w3m")
opt_parser.add_option("-a", "--antiword",
    action="store_true", default=False,
    help="doc2txt  via antiword")
opt_parser.add_option("-c", "--catdoc",
    action="store_true", default=False,
    help="doc2txt  via catdoc")
opt_parser.add_option("-d", "--docx2txt",
    action="store_true", default=False,
    help="docx2txt via docx2txt")
opt_parser.add_option("-f", "--pdftohtml",
    action="store_true", default=False,
    help="pdf2html via pdftohtml")
opt_parser.add_option("-w", "--wrap",
    action="store_true", default=False,
    help="wrap text")
opt_parser.add_option("-q", "--quote",
    action="store_true", default=False,
    help="prepend '>' quote marks to lines")
opts, args = opt_parser.parse_args()

url = args[0]
print "** url = ", url
content = None
os.remove(DST_FILE) if os.path.exists(DST_FILE) else None

# I prefer to use the programs native wrap if possible
if opts.lynx:
    wrap = '-width 76' if opts.wrap else '-width 1024'
    command = ['lynx', '-dump', '-nonumbers', url]
elif opts.links:
    wrap = '-width 76' if opts.wrap else ''
    command = ['links', '-dump', url]
elif opts.w3m:
    wrap = '-cols 76' if opts.wrap else ''
    command = ['w3m', '-dump', '-cols', '76', url]
elif opts.antiword:
    wrap = '' if opts.wrap else '-w 0'
    command = ['antiword', url]
elif opts.catdoc:
    wrap = '' if opts.wrap else '-w'
    command = ['catdoc', url]
elif opts.docx2txt:
    wrap = '' # maybe use fold instead?
    command = ['docx2txt', url, '-']
elif opts.pdftohtml:
    wrap = ''
    command = ['pdftotext', '-layout', '-nopgbrk', url, '-']
else: # fallback to pandoc
    content = urlopen(url).read()
    wrap = '' if opts.wrap else '--no-wrap'
    command = ['pandoc', '-f', 'html', '-t', 'markdown', 
                '--reference-links', '-o', DST_FILE]

command.extend(wrap.split())
print "** command = ", command
process = Popen(command, stdin=PIPE, stdout=open(DST_FILE, 'w'))
process.communicate(input = content)

if opts.wrap or opts.quote: 
    with open(DST_FILE) as f:
        new_content = []
        for line in f.readlines():
            if opts.wrap and wrap == '': # wrap if no native wrap
                print("WRAPPING")
                line = textwrap.fill(line, 76).strip() + '\n'
            if opts.quote:
                line = '> ' + line # .replace('\n', '\n> ')
            new_content.append(line)
        content = ''.join(new_content)
    with open(DST_FILE, 'w') as f:
        f.write(content)

os.chmod(DST_FILE, 0600)
call([EDITOR, DST_FILE])
