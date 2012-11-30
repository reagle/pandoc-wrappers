#!/usr/bin/python3.2
# -*- coding: utf-8 -*-
# (c) Copyright 2007-2012 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

'''Build a PDF (article or book) based on markdown source using pandoc.

'''

import codecs
from glob import glob
import locale
import logging
import md2bib
import os
from os import chdir, path
import re
import shutil
import string
from subprocess import call
import sys
from time import localtime, strftime

from os import environ
HOME = environ['HOME']
BIB_FILE = HOME+'/joseph/readings.bib'

log_level = 100 # default
logging.basicConfig(level=log_level, format = "%(levelno)s %(funcName).5s: %(message)s")
critical = logging.critical
info = logging.info
dbg = logging.debug

##################################################
# Helper Functions

REGEX_MAP = [  
                (r"``(.*?)''", r'\\enquote{\1}'),
                (r"`(.*?)'", r'\\enquote{\1}'),
            ]

SUB_MAP = [
                ('Encyclopaedia', 'Encyclopædia'),
                ('Encyclopedia Britannica', 'Encyclopædia Britannica'),
                (' \\footnote', '\\footnote'),
            ]

class MultiReplace(object):
    """
    Replace multiple instances from a list of ori/rep pairs.
    I use an object for performance: compiled regexes persist.
    Table is a list of pairs, I have to convert to dict for regex
    replace function, don't use a dict natively since they aren't ordered.
    """
    def __init__(self, table):
        self.originals, self.replacements = zip(*table)
        self.pattern = re.compile(
            "(" + '|'.join(map(re.escape, self.originals)) + ")"
        )
        self.table_dic = dict(table)

    def _get_replacement(self, match): # passed match
        return self.table_dic.get(match.group(1), "") # use match to return replacement

    def replace(self, line):
        return self.pattern.sub(self._get_replacement, line) # pass replacement function
mr = MultiReplace(SUB_MAP)

##################################################

def pre_pandoc(fn, src_file, md_tmp_file):
    """ 
    Tweak the markdown source
    """
    
    author = heading = maketitle = ''
    
    file_enc = "utf-8"
    new_lines = []

    lines = codecs.open(src_file, "rb", file_enc).read()
    # remove writemonkey repository and bookmarks
    lines = lines.split('***END OF FILE***')[0]
    lines = lines.replace('@@', '')
    lines = lines.split('\n')
    
    for line_no, line in enumerate(lines, start = 1):
        line = line.rstrip() # codecs opens in binary mode with EOLs
        
        if line_no == 1:
            line = line.replace('\ufeff', '') # remove BOM if present
            if line.startswith('%'):
                title = line.split(' ', 1)[1]
                title = re.sub('\*(.*)\*', r'\em{\1}', title) 
                if path.isdir(fn):
                    heading = r'\chapter'
                else:
                    heading = r'\title'
                    maketitle = r'\maketitle'
                continue
        elif line_no == 2 and line.startswith('% '):
            author = r'\author{' + line[2:] + '}'
            continue
        elif line_no == 3 and heading:
            new_lines.append('%s{%s} %s %s\n' %(heading, title, author, maketitle))

        new_lines.append(line)

    mkd_tmp_fd = codecs.open(md_tmp_file, "w", file_enc, "replace")
    mkd_tmp_fd.write('\n'.join(new_lines))
    mkd_tmp_fd.close()

def pandoc_call(md_tmp_file, tex_tmp_file, build_file_base):
    """
    Call pandoc on tweaked markdown files.
    """

    bib_file = BIB_FILE
    if not args.fast: 
        fe_opts = '-c'
        if args.online_URLs_only: fe_opts += 'o'
        if args.URL_long: fe_opts += 'l'
        if args.bibtex: fe_opts += 'b'
        info("fe_opts %s" % fe_opts)
        call(['fe', fe_opts], stdout=open(BIB_FILE, 'w'))
        # generate a subset bibtex
        keys = md2bib.getKeysFromMD(md_tmp_file)
        entries = md2bib.parseBibTex(open(BIB_FILE, 'r'))
        subset = md2bib.subsetBibliography(entries, keys)
        md2bib.emitBibliography(subset, open(build_file_base + '.bib', 'w'))
                
    pandoc_opts = ['-t', 'latex', '--biblatex', '--bibliography=%s' %bib_file, '--no-wrap', '--tab-stop', '8']
    pandoc_cmd = ['pandoc', md_tmp_file]
    pandoc_cmd.extend(pandoc_opts)
    info("pandoc cmd = '%s'" % ' '.join(pandoc_cmd))
    call(pandoc_cmd, stdout=codecs.open(tex_tmp_file, 'w', 'utf-8'))


ACITE_CMD = r'''\\acite[s]?(?:\[[^\]]*\]|\{([^\}]*)\})+'''
CAP_CITEYP_OBJ = re.compile(r'''(\\cap\{\})(.*?) ?(%s)''' % ACITE_CMD) #110508: added ' ?'

def post_pandoc(fn, tex_tmp_file, tex_file):
    """
    Do a final few tweaks to the latex resulting from pandoc.
    """

    file_enc = "utf-8"
    lines = codecs.open(tex_tmp_file, "rb", file_enc).readlines()
    new_lines = []

    for line in lines:

        # replace \cap{} with nearest subsequent \acite[][]{Author2011foo}
        if '\cap{}' in line:
            if args.authordate:
                line = CAP_CITEYP_OBJ.sub(r'\\citeyp{\4}\2', line)
            else:
                line = line.replace(r' \cap{}', r'')

        # swap punctuation
        if args.british_punctuation: # period outside of quote
            # period outside quote
            line = re.sub(r"""([.,])(''|')""", r'\2\1', line)
            # move a punctuation after a cite command
            line = re.sub(r"""((?:'')?)([.,;]) (%s)""" % ACITE_CMD,
                r'\1 \3\2', line)
        else:
            # period inside quote
            line = re.sub(r"""(''|')([.,])""", r'\2\1', line)
            # move punctuation before a cite command
            line = re.sub(r"""(''?) (%s)([.,;])""" % ACITE_CMD,
                r'\1\4 \2', line)

        for pattern, replace in REGEX_MAP:
            line = re.sub(pattern, replace, line)
                            
        line = mr.replace(line)
        new_lines.append(line)

    tex_fd = codecs.open(tex_file, "w", file_enc, "replace")
    tex_fd.write(''.join(new_lines))
    tex_fd.close()


def latex_build(dst_dir, src_dir, build_file, build_file_base, build_file_name):

    os.chdir(dst_dir)
    if args.commit:
        call(['git', 'ci', '-m', args.commit, src_dir])
    if args.fast: # run latex once
        call(['pdflatex', '--src-specials', '-interaction=nonstopmode', build_file_base])
    else:
        os.chdir(dst_dir) # bibtex8 only working in cwd
        call(['pdflatex', '--src-specials', '-interaction=nonstopmode', build_file_name])
        call(['biber', build_file_name])
        call(['pdflatex', '--src-specials', '-interaction=nonstopmode', build_file_name])
        call(['pdflatex', '--src-specials', '-interaction=nonstopmode', build_file_name])
    [os.remove(file_name) for file_name in glob('*.tmp')] 


def main(args, files):

    if len(files) == 0:  # give default project
        files = [HOME+'/joseph/2010/faith']

    if len(files) > 1:
        raise Exception('Error: Too many arguments.')
        sys.exit()
    elif len(files) == 1:
        fn = files[0]
        if path.isdir(fn) == True:    # directory of source files
            info("%s is a directory" %fn)
            full_dir = path.realpath(fn) + '/'
            project = path.split(full_dir[:-1])[1]
            files = [path.basename(file) for file in glob(full_dir +'[!~]*.md')]
            src_dir = full_dir
            dst_dir = src_dir + 'latex-' + project[:3] + '/'
            build_file_name = '0-book'
            build_file_base = dst_dir + build_file_name
            build_file = build_file_base + '.tex'

        elif path.isfile(fn) == True: # single source file
            info("%s is a single source file" % fn)
            files.append(fn)
            ori_file = files[0]

            # interactions-wp-contingency.md
            src_file = path.basename(ori_file)  # delete?
            files = []
            files.append(src_file)

            # /home/reagle/joseph/2009/01/
            src_dir = path.dirname(path.realpath(ori_file)) + '/'

            # /home/reagle/joseph/2009/01/latex-int/
            dst_dir = src_dir + 'latex-' + src_file[:3] + '/'

            # /home/reagle/joseph/2009/01/latex-int/0-article.tex
            build_file_name = '0-article'
            build_file_base = dst_dir + build_file_name
            build_file = build_file_base + '.tex'
        else:
            raise Exception("%s unknown type" % fn)
            sys.exit()

    ##################################################
    # Process each file

    files.sort()
    for ifile in files:
        src_file = src_dir + ifile    # original markdown
        md_tmp_file = dst_dir + path.splitext(ifile)[0] + '.md.tmp' # tweaked markdown
        tex_tmp_file = dst_dir + path.splitext(ifile)[0] + '.tex.tmp' # pandoc latex
        tex_file = dst_dir + path.splitext(ifile)[0] + '.tex' # tweaked latex

        info("ifile %s" % ifile)
        #info("src_file %s" % src_file)
        #info("md_tmp_file %s" % md_tmp_file)
        #info("tex_tmp_file %s" %tex_tmp_file)
        #sys.exit()

        file_name, extension = path.splitext(ifile)

        pre_pandoc(fn, src_file, md_tmp_file)
        pandoc_call(md_tmp_file, tex_tmp_file, build_file_base)
        post_pandoc(fn, tex_tmp_file, tex_file)
    latex_build(dst_dir, src_dir, build_file, build_file_base, build_file_name)
    

if '__main__' == __name__:

    import argparse # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(description=
        'Build latex book from markdown files')
    
    # positional arguments
    arg_parser.add_argument('files', nargs='+',  metavar='FILE')

    # optional arguments
    arg_parser.add_argument("-a", "--authordate", 
                    action="store_true", default=False,
                    help="use authordate with \cap{} subsitutions")
    arg_parser.add_argument("-c", "--commit", metavar="MESSAGE", default='',
                    help="Commit to git repository")
    arg_parser.add_argument("-B", "--british-punctuation", 
                    action="store_true", default=False,
                    help="place punctuation outside of quotes")
    arg_parser.add_argument("-b", "--bibtex", 
                    action="store_true", default=False,
                    help="using bibtex rather than biblatex")
    arg_parser.add_argument('-f', '--fast', action='count',
                    help="increase speed by decreasing latex invocations")
    arg_parser.add_argument('-L', '--log-to-file',
                    action="store_true", default=False,
                    help="log to file %(prog)s.log")
    arg_parser.add_argument("-u", "--URL-long", 
                    action="store_true", default=False,
                    help="use long URLs")
    arg_parser.add_argument("-o", "--online-URLs-only", 
                    action="store_true", default=False,
                    help="Only include URLs that are exclusively online")
    arg_parser.add_argument('-V', '--verbose', action='count', default=0,
                    help="Increase verbosity (specify multiple times for more)")

    args = arg_parser.parse_args()
    
    if args.verbose == 1: log_level = logging.CRITICAL # DEBUG
    elif args.verbose == 2: log_level = logging.INFO
    elif args.verbose >= 3: log_level = logging.DEBUG
    if args.log_to_file: # nothing is done with log_dest presently
        log_dest = codecs.open('bd.log', 'w', 'UTF-8', 'replace')
    else:
        log_dest = sys.stderr
    
    main(args, args.files)
