#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) Copyright 2008-2012 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

'''A wrapper script for pandoc that handles my own issues:
    1. associates the result with a particular style sheet.
    2. can replace [@key] with hypertext'd refs from bibtex database.
    3. makes use of reveal.js for presentations.
    
TODO:
    1. reduce redundant references: page only, if key already cited
    2. replace square brackets with round when no URL.
'''

import codecs
import logging
import md2bib
import os
from os import chdir, environ, mkdir, path, rename, remove, walk
from os.path import abspath, basename, dirname, exists, \
    getmtime, join, relpath, splitext
import re
import shutil
#from sh import chmod # http://amoffat.github.com/sh/
from subprocess import call, Popen
import sys

HOME = os.environ['HOME']
BROWSER = os.environ['BROWSER'] if 'BROWSER' in os.environ else None

log_level = 100 # default
critical = logging.critical
info = logging.info
dbg = logging.debug
warn = logging.warn
error = logging.error
excpt = logging.exception

def link_citations(line, bibtex_file):
    """
    Turn pandoc/markdown citations into links within parenthesis.
    Used only with simply citations in presentations.
    """
    
    P_KEY = re.compile(r'(-?@[\w|-]+)') # -@Clark-Flory2010fpo
    def hyperize(cite_match): 
        """
        hyperize every non-overlapping occurrence
        and return to P_KEY.sub
        """
        cite_replacement = []
        url = None
        citation = cite_match.group(0)
        key = citation.split('@', 1)[1]
        info("**   processing key: %s" % key)
        reference = bibtex_file.get(key)
        if reference == None:
            print("WARNING: key %s not found" % key)
            return key
        url = reference.get('url')
        title = reference.get('shorttitle')
        
        if citation.startswith('-'):
            key_text = re.findall(r'\d\d\d\d.*', key)[0] # year
        else:
            key_text = key
        
        #info("**   url = %s" % url)
        if url:
            cite_replacement.append('[%s](%s)' %(key_text, url))
        else:
            if title:
                title = title.replace('{', '').replace('}', '')
                cite_replacement.append('%s, "%s"' %(key_text, title))
            else:
                cite_replacement.append('%s' %key_text)
        #info("**   using cite_replacement = %s" % cite_replacement)
        return ''.join(cite_replacement)

    P_BRACKET_PAIR = re.compile('\[[^\]]*[-#]?@[^\]]+\]')
    def make_parens(cite_match): 
        """
        Convert to balanced parens
        """
        return '(' + cite_match.group(0)[1:-1] + ')'

    line = P_BRACKET_PAIR.sub(make_parens, line)
    line = P_KEY.sub(hyperize, line)
    return line

def quash_citations(line):

    P_BRACKET_PAIR = re.compile(r'\[[-#]?@[^\]]+\]')
    def quash(cite_match): 
        """
        If args.quash_citations, 
            do so for hash sign preceding at sign: [#@Reagle2012foo]
            otherwise make a normal citation.
        """
        citation = cite_match.group(0)
        #critical("citation = '%s'" %(citation))
        chunks = citation[1:-1].split(';') # remove bracket and chunk
        #critical("chunks = %s" %(chunks))
        citations_keep = []
        for chunk in chunks:
            #critical("  chunk = '%s'" %(  chunk))
            if '#@' in chunk:
                if args.quash_citations:
                    pass
                    #critical("  quashed")
                else:
                    chunk = chunk.replace('#@', '@')
                    #critical("  keeping chunk = '%s'" %(chunk))
                    citations_keep.append(chunk)
            else:
                citations_keep.append(chunk)
                
        if citations_keep:
            #critical("citations_keep = '%s'" %(citations_keep))
            return '[' + ';'.join(citations_keep) + ']'
        else:
            return ''
    

    return P_BRACKET_PAIR.subn(quash, line)[0]

def create_talk_handout(abs_fn, tmp2_fn):
    '''If talks and handouts exists, create (partial) handout'''
        
    info("starting handout")
    # http://www.farside.org.uk/200804/osjam/markdown2.py
    ast_bullet_re = re.compile(r'^ *(\* )')
    em_re = re.compile(r'(?<!\*)\*([^\*]+?)\*')
    def em_mask(matchobj):
        info("return replace function")
        return '&#95;'*len(matchobj.group(0)) # underscore that pandoc will ignore
        
    info("abs_fn = '%s'" %(abs_fn))
    info("tmp2fn = '%s'" %(tmp2_fn))
    md_dir = dirname(abs_fn)
    handout_fn = ''
    if '/talks' in abs_fn:
        handout_fn = abs_fn.replace('/talks/', '/handouts/')
        handout_dir = dirname(handout_fn)
        info("handout_dir = '%s'" %(dirname(handout_fn)))
    if exists(dirname(handout_fn)):
        info("creating handout")
        skip_to_next_header = False
        handout_f = open(handout_fn, 'w')
        content = open(tmp2_fn, 'r').read()
        info("md_dir = '%s', handout_dir = '%s'" %(md_dir, handout_dir))
        media_relpath = relpath(md_dir, handout_dir)
        info("media_relpath = '%s'" %(media_relpath))
        content = content.replace('](media/', '](%s/media/' % media_relpath)
        lines = [line+'\n' for line in content.split('\n')]
        for line in lines:
            if line.startswith('----') or \
                '<video ' in line or \
                line.startswith('<details'):  # skip rules
                skip_to_next_header = True
                continue 
            # convert pseudo div headings to h1
            #line = re.sub(r'^#+ (.*)', r'# \1', line) # error: matches '### '
            if line.startswith('##'):
                line = line.replace('##### ', '# ')
                line = line.replace('#### ', '# ')
                line = line.replace('## ', '# ')
            # slide to SKIP
            if args.partial_handout:
                info("args.partial_handout = '%s'" %(args.partial_handout))
                if line.startswith('# '):
                    if '*' in line:
                        skip_to_next_header = True
                    elif '# rev: ' in line:
                        skip_to_next_header = True
                    else:
                        skip_to_next_header = False
                    handout_f.write(line)
                else:
                    # content to REDACT
                    if not skip_to_next_header:
                        if line.startswith('> *'):
                            handout_f.write('\n')
                            continue
                        info("entering em redaction")
                        line = ast_bullet_re.subn('- ', line)[0]
                        line = em_re.subn(em_mask, line)[0]
                        handout_f.write(line)
                    else:
                        handout_f.write('\n')
            else:
                handout_f.write(line)
        handout_f.close()
        md_cmd = ['md', '--divs', '--offline', '-c',
        'http://reagle.org/joseph/talks/_dzslides/2012/10-class-handouts.css',
        handout_fn]
        info("md_cmd = %s" % ' '.join(md_cmd))
        call(md_cmd)
        remove(handout_fn)
    info("done handout")


def process(args):
    
    if args.bibliography:
        bibtex_file = parseBibTex(open(HOME+'/joseph/readings.bib', 'r').readlines())

    for in_file in args.files:

        ##############################
        # initial pandoc configuration based on arguments
        ##############################

        pandoc_opts = ['-s', '--smart', '--tab-stop', '4', 
            '--email-obfuscation=references'] 
        if args.presentation:
            args.validate = False
            args.css = False
            pandoc_opts.extend(['-t', 'revealjs', '--slide-level=2',
                                '-V', 'revealjs-url=../_reveal.js',
                                '-V', 'theme=moon',
                                '-c', '../_custom/revealjs.css'])
        if args.css:
            pandoc_opts.extend(['-c', args.css])
        if args.toc:
            pandoc_opts.extend(['--toc'])
        if args.offline:
            pandoc_opts.extend(['--self-contained'])
        if args.divs:
            pandoc_opts.extend(['--section-divs'])
        if args.include_after_body:
            pandoc_opts.extend(['--include-after-body=%s' % args.include_after_body[0]])
        if args.style_chicago:
            args.style_csl = ['chicago-author-date']

        ##############################
        ##  pre pandoc
        ##############################

        base_fn, base_ext = splitext(in_file)
        abs_fn = abspath(in_file)
        fn_path = os.path.split(abs_fn)[0]

        fn_tmp_1 = "%s-1%s" %(base_fn, base_ext) # pre pandoc
        fn_tmp_2 = "%s-2%s" %(base_fn, base_ext) # post pandoc
        fn_tmp_3 = "%s-3%s" %(base_fn, '.html')  # tidied html
        cleanup_tmp_fns = [fn_tmp_1, fn_tmp_2, fn_tmp_3]

        if args.style_csl:
            print("args.style_csl = %s" % args.style_csl)
            pandoc_opts.extend(['--csl=%s' % args.style_csl[0]])
            info("generate temporary subset bibtex for speed")
            BIB_FILE = HOME+'/joseph/readings.bib'
            bib_subset_tmp_fn = base_fn +'.bib'
            cleanup_tmp_fns.append(bib_subset_tmp_fn)
            keys = md2bib.getKeysFromMD(in_file)
            entries = md2bib.parseBibTex(open(BIB_FILE, 'r'))
            subset = md2bib.subsetBibliography(entries, keys)
            md2bib.emitBibliography(subset, open(bib_subset_tmp_fn, 'w'))
            pandoc_opts.extend(['--bibliography=%s' % bib_subset_tmp_fn,])

        shutil.copyfile(in_file, fn_tmp_1)
        f1 = codecs.open(fn_tmp_1, 'r', "UTF-8", "replace")
        content = f1.read()
        if content[0] == codecs.BOM_UTF8.decode('utf8'):
            content = content[1:]
        f2 = codecs.open(fn_tmp_2, 'w', "UTF-8", "replace")

        print(os.path.split(abs_fn))
            
        # remove writemonkey repository and bookmarks
        content = content.split('***END OF FILE***')[0]
        content = content.replace('@@', '')
        
        lines = content.split('\n')
        
        for lineNo, line in enumerate(lines):
            # fix Wikicommons relative network-path references 
            # so the URLs work on local file system (i.e.,'file:///')
            line = line.replace('src="//', 'src="http://')
            line = quash_citations(line)
            if args.bibliography: # create hypertext refs from bibtex db
                line = link_citations(line, bibtex_file)
                #info("\n** line is now %s" % line)

            #info("END line: '%s'" % line)
            f2.write(line + '\n')
        f1.close()
        f2.close()
        
        ##############################
        ##  pandoc
        ##############################

        pandoc_cmd = ['pandoc', '-f', 'markdown+mmd_title_block']
        pandoc_cmd.extend(pandoc_opts)
        pandoc_cmd.append(fn_tmp_2)
        print("pandoc_cmd: " + ' '.join(pandoc_cmd) + '\n')
        call(pandoc_cmd, stdout=open(fn_tmp_3, 'w'))
        info("done pandoc_cmd")

        if args.presentation:
            create_talk_handout(abs_fn, fn_tmp_2)

        ##############################
        ##  post pandoc
        ##############################
        
        # final tweaks to tmp html file
        html = open(fn_tmp_3, 'r').read()
        #html = html.replace('<h1></h1>', '') # fixed (#484)
        result_fn = base_fn + '.html'
        if args.output:
            result_fn = args.output[0]
        open(result_fn, 'w').write(html)
        
        if args.validate:
            call(['tidy', '-utf8', '-q', '-i', '-m', '-w', '0', '-asxhtml',
                    result_fn])
        if args.launch_browser:
            info("launching %s" %result_fn)
            Popen([BROWSER, result_fn])
            
        info("removing tmp files")
        for cleanup_fn in cleanup_tmp_fns:
            if exists(cleanup_fn):
                remove(cleanup_fn)

            
if __name__ == "__main__":
    import argparse # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(description='Markdown wrapper with slide and bibliographic options')
    arg_parser.add_argument('files', nargs='+',  metavar='FILE')
    arg_parser.add_argument("-b", "--bibliography",
                    action="store_true", default=False,
                    help="turn citations into hypertext w/out CSL")                    
    arg_parser.add_argument("-q", "--quash-citations",
                    action="store_true", default=False,
                    help="quash citations that begin with hash (#@Reagle2012foo)")                    
    arg_parser.add_argument("-c", "--css", 
                    default='http://reagle.org/joseph/2003/papers.css',
                    help="apply non-default CSS")
    arg_parser.add_argument("-d", "--divs", 
                    action="store_true", default=False,
                    help="use pandoc's --section-divs")
    arg_parser.add_argument("--include-after-body", 
                    nargs=1,  metavar='FILE',
                    help="include at end of body (pandoc pass-through)")
    arg_parser.add_argument("-l", "--launch-browser",
                    action="store_true", default=False,
                    help="launch browser to see results")
    arg_parser.add_argument("-o", "--output", nargs=1,
                    help="output file path")
    arg_parser.add_argument("--offline",
                    action="store_true", default=False,
                    help="incorporate links: scripts, images, and CSS")
    arg_parser.add_argument("-s", "--style-chicago",
                    action="store_true", default=False,
                    help="use CSL bibliography style, default chicago")
    arg_parser.add_argument("-S", "--style-csl", nargs = 1,
                    help="specify CSL style")
    arg_parser.add_argument("-t", "--toc",
                    action="store_true", default=False,
                    help="create table of contents")
    arg_parser.add_argument("-v", "--validate",
                    action="store_true", default=False,
                    help="validate and tidy HTML")

    arg_parser.add_argument("-p", "--presentation",
                    action="store_true", default=False,
                    help="create presentation with dzsslides")
    arg_parser.add_argument("--partial-handout", 
                    action="store_true", default=False,
                    help="presentation handout is partial/redacted")
                    
    arg_parser.add_argument('-L', '--log-to-file',
                    action="store_true", default=False,
                    help="log to file PROGRAM.log")
    arg_parser.add_argument('-V', '--verbose', action='count', default=0,
        help="Increase verbosity (specify multiple times for more)")
    arg_parser.add_argument('--version', action='version', version='TBD')
    args = arg_parser.parse_args()    

    if args.verbose == 1: log_level = logging.CRITICAL
    elif args.verbose == 2: log_level = logging.INFO
    elif args.verbose >= 3: log_level = logging.DEBUG
    LOG_FORMAT = "%(levelno)s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(filename='wiki-update.log', filemode='w',
            level=log_level, format = LOG_FORMAT)
    else:
        logging.basicConfig(level=log_level, format = LOG_FORMAT)

    process(args)
