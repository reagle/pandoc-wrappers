#!/usr/bin/python3
# -*- coding: utf-8 -*-
'''Convert Pyblosxom content to markdown for Pelican'''

import codecs
import locale
import logging
from os import chdir, environ, mkdir, makedirs, rename, stat, walk, utime
from os.path import abspath, basename, exists, split, splitext
from pprint import pprint
from sh import find, iconv, ls, pandoc # http://amoffat.github.com/sh/index.html
from shutil import copy, rmtree, move
from stat import ST_ATIME, ST_MTIME # constants 7 and 8
import sys
import tempfile
from time import localtime, strftime

log_level = 100 # default
critical = logging.critical
info = logging.info
dbg = logging.debug

HOME = environ['HOME']
CONTENT_ROOT = HOME+'/data/2web/reagle.org/joseph/content-old/'
COMMENT_ROOT = HOME+'/data/2web/reagle.org/joseph/comments-old/'
NEW_ROOT = HOME+'/data/2web/reagle.org/joseph/content/'

def find_entries():
    """Returns a dictionary of keys corresponding to entries with a list of
    comments. For example:
    
    'nafus-gender.html': {
        'filename' : 'nafus-gender.html',
        'mtime' :   '2012-06-29',
        'path' : 'social/gender/',
        'comments' : ['nafus-gender-1341219620.15.cmt', 
            'nafus-gender-1341239352.82.cmt', 
            'nafus-gender-1341241456.95.cmt'
        ]},
    }
    
    """
    
    entries = {}

    for root, dirnames, filenames in walk(CONTENT_ROOT):
        for filename in filenames:
            #info(root, filename)
            entry = {'filename': filename}
            stats = stat(root+'/'+filename)
            entry['mtime'] = strftime("%Y-%m-%d", localtime(stats[8])).strip()
            fn_base, fn_ext = splitext(basename(filename))
            path = root[len(CONTENT_ROOT):]
            entry['path'] = path+'/'
            info("fn_base = '%s'" % fn_base)
            if fn_base.startswith('.'):
                continue
            info(path, fn_base, fn_ext)
            comments = find(COMMENT_ROOT, "-name", fn_base+'*')
            if comments: 
                info("  comments = %s" %comments)
                comments_list = []
                for comment in comments:
                    info(split(comment.strip()))
                    comments_list.append(split(comment.strip())[1])
                info(comments_list)
                entry['comments'] = comments_list
            entries[filename] = entry
    return entries

def transform_markdown(filename, entry):
    """Add metadata and comments to new markdown files"""
    
    first_line_of_content = 0
    tmp_file = tempfile.NamedTemporaryFile(dir='.', mode='w',
        delete=False, encoding='utf-8')
    mdn_text = open(filename, encoding='utf-8').readlines()
    
    # pandoc metadata
    title, author, date = ('TITLE', 'Joseph Reagle', entry['mtime'])
    if mdn_text[0][0] in ('%', '#'): # title
        first_line_of_content += 1
        if len(mdn_text[0]) > 3:  
            title = mdn_text[0][1:].strip()
        else:
            print("WARNING: %s has no title" %filename)
    tmp_file.write("Title: %s\n" % title)
        
    # pandoc author
    if mdn_text[1][0] in ('%'):
        first_line_of_content += 1
        if len(mdn_text[1]) > 3:  
            author = mdn_text[1][1:].strip()
    tmp_file.write("Author: %s\n" % author)
        
    # pandoc date
    if mdn_text[2][0] in ('%'):
        first_line_of_content += 1
        if len(mdn_text[2]) > 3:  
            date = mdn_text[2][1:].strip()
    tmp_file.write("Date: %s\n" % date )
    
    #pandoc escapes symbols, but pelican doesn't recognize them.
    mdn_content = ''.join(mdn_text[first_line_of_content:])
    mdn_content = mdn_content.replace('\$', '$')\
        .replace('\_', '_')
        
    #tags = ', '.join(entry['path'][0:-1].split('/'))
    tags = entry['path'][0:-1].rsplit('/')[-1]
    category = entry['path'][0:-1].split('/')[0]
    tmp_file.write("Category: %s\n" % category)
    tmp_file.write("Tags: %s\n" % tags)
    tmp_file.write(''.join(mdn_content))
    
    from lxml import etree
    parser = etree.XMLParser()

    if 'comments' in entry:
        tmp_file.write("\n------ \n\n")
        tmp_file.write("\n### Ported/Archived Responses\n")
        for comment in entry['comments']:
            info(entry)
            info(COMMENT_ROOT+entry['path']+comment)
            doc = etree.parse(open(COMMENT_ROOT+entry['path']+comment, 'rb'))
            author = doc.xpath('//author/text()')[0]
            title = doc.xpath('//title/text()')[0]
            date = doc.xpath('//pubDate/text()')[0]
            date = strftime("%Y-%m-%d", localtime(float(date)))
            description = '\n'.join(doc.xpath('//description/descendant::text()'))
            tmp_file.write("\n\n**%s on %s** \n\n" % (author, date))
            tmp_file.write(description)
            
    tmp_file.close()
    move(tmp_file.name, filename)

def convert_entries(entries):
    """Convert entries"""
    
    if exists(NEW_ROOT):
        rmtree(NEW_ROOT)
    mkdir(NEW_ROOT)
    for filename, entry in entries.items():
        #info(filename, entry)
        if not exists(NEW_ROOT+entry['path']):
            makedirs(NEW_ROOT+entry['path'])
        fn_base, fn_ext = splitext(basename(filename))
        fn = CONTENT_ROOT+entry['path']+filename
        fn_mdn = NEW_ROOT+entry['path']+fn_base+'.md'
        if fn_ext == '.html':
            #stat_ori = stat(fn)
            #iconv('-t', 'utf-8', '-o', fn, fn)
            #utime(fn, (stat_ori[ST_ATIME], stat_ori[ST_MTIME]))
            pandoc('--atx-headers', '--from', 'html', '--to', 'markdown',
                '--strict', '-s', '--no-wrap', '-o', fn_mdn, fn)
            transform_markdown(fn_mdn, entry)
        else:
            copy(fn, NEW_ROOT+entry['path'])
            print("Copied unknown filetype %s" %filename)
            # TBD add more conversion types

 
if '__main__' == __name__:

    import argparse # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(description='Convert Pyblosxom content to markdown for Pelican')
    
    # positional arguments
    #arg_parser.add_argument('files', nargs='+', metavar='FILE')
    # optional arguments
    arg_parser.add_argument("-b", "--boolean",
        action="store_true", default=False,
        help="boolean value")
    arg_parser.add_argument("-o", "--out-filename",
        help="output results to filename", metavar="FILE")
    arg_parser.add_argument('-L', '--log-to-file',
        action="store_true", default=False,
        help="log to file %(prog)s.log")
    arg_parser.add_argument("-n", "--number", type=int, default=10,
        help="some number (default: %(default)s)")
    arg_parser.add_argument('-V', '--verbose', action='count', default=0,
        help="Increase verbosity (specify multiple times for more)")
    arg_parser.add_argument('--version', action='version', version='TBD')
    args = arg_parser.parse_args()

    if args.verbose == 1: log_level = logging.CRITICAL
    elif args.verbose == 2: log_level = logging.INFO
    elif args.verbose >= 3: log_level = logging.DEBUG
    LOG_FORMAT = "%(levelno)s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(filename='PROG-TEMPLATE.log', filemode='w',
            level=log_level, format = LOG_FORMAT)
    else:
        logging.basicConfig(level=log_level, format = LOG_FORMAT)

    entries = find_entries() # {entries: [comments]}
    convert_entries(entries)
        