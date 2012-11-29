#!/usr/bin/python3.2
# -*- coding: utf-8 -*-
# (c) Copyright 2008-2012 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

'''A wrapper script for pandoc that handles my own issues:
    1. associates the result with a particular style sheet.
    2. can replace [@key] with hypertext'd refs from bibtex database.
    3. makes use of DZSlides for presentations.
    
TODO:
    1. reduce redundant references: page only, if key already cited
    2. replace square brackets with round when no URL.
'''

import codecs
from dateutil.parser import parse
from datetime import date, datetime
from md2bib import parseBibTex
import getopt
import os
import re
import shutil
from string import Template
from subprocess import call, Popen
import sys

from os import environ
HOME = environ['HOME']
BROWSER = environ['BROWSER']


def link_citations(line, bibtex_file):
    """
    Turn pandoc/markdown citations into links.
    """
    
    P_CITE = re.compile(r'(-?@[\w|-]+)') # [-@Clark-Flory2010fpo]
    def hyperize(cite_match): 
        """
        hyperize every non-overlapping occurrence
        and return to P_CITE.sub
        """
        cite_replacement = []
        url = None
        citation = cite_match.group(0)
        key = citation.split('@',1)[1]
        #print("**   processing key: %s" % key)
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
        
        #print("**   url = %s" % url)
        if url:
            cite_replacement.append('[%s](%s)' %(key_text,url))
        else:
            if title:
                title = title.replace('{', '').replace('}', '')
                cite_replacement.append('%s, "%s"' %(key_text, title))
            else:
                cite_replacement.append('%s' %key_text)
        #print("**   using cite_replacement = %s" % cite_replacement)
        return ''.join(cite_replacement)

    return P_CITE.sub(hyperize, line)

def process(files):
    
    if args.bibliography:
        bibtex_file = parseBibTex(open(HOME+'/joseph/readings.bib', 'r').readlines())
        
    for in_file in files:
        
        ##############################
        ##  pre pandoc
        ##############################

        fileName, extension = os.path.splitext(in_file)
        abs_fn = os.path.abspath(in_file)

        tmpName1 = "%s-1%s" %(fileName, extension)
        tmpName2 = "%s-2%s" %(fileName, extension)
        tmpName3 = "%s-3%s" %(fileName, '.html')

        shutil.copyfile(in_file, tmpName1)

        f1 = codecs.open(tmpName1, 'r', "UTF-8", "replace")
        lines = f1.read()
        f2 = codecs.open(tmpName2, 'w', "UTF-8", "replace")

        print(os.path.split(abs_fn))

        # remove writemonkey repository and bookmarks
        lines = lines.split('***END OF FILE***')[0]
        lines = lines.replace('@@', '')
        
        lines = lines.split('\n')
        
        # figure out the title
        for lineNo, line in enumerate(lines):
            #print("START line: '%s'" % line)
            if lineNo == 0:
                line = line.lstrip(str(codecs.BOM_UTF8, "utf8"))
                if line.startswith('%'):
                    title = line [1:]
            # fix Wikicommons relative network-path references 
            # so the URLs work on local file system (i.e.,'file:///')
            line = line.replace('src="//', 'src="http://')
            
            if args.bibliography: # create hypertext refs from bibtex db
                line = link_citations(line, bibtex_file)
                #print("\n** line is now %s" % line)

            #print("END line: '%s'" % line)
            f2.write(line + '\n')
        f1.close()
        f2.close()

        ##############################
        ##  pandoc
        ##############################

        pandoc_cmd = ['pandoc', '-f', 'markdown']
        pandoc_cmd.extend(pandoc_opts)
        pandoc_cmd.append(tmpName2)
        print("** pandoc_cmd: " + ' '.join(pandoc_cmd) + '\n')
        call(pandoc_cmd, stdout=open(tmpName3, 'w'))

        ##############################
        ##  post pandoc
        ##############################
        
        # fix a pandoc bug that produces empty h1 tags
        html = open(tmpName3, 'r').read()
        #html = html.replace('<h1></h1>', '') # fixed (#484)
        open(fileName + '.html', 'w').write(html)
        
        if args.validate:
            call(['tidy', '-utf8', '-q', '-i', '-m', '-w', '0', '-asxhtml',
                    fileName + '.html'])
        if args.launch_browser:
            Popen([BROWSER, fileName + '.html'])
        [os.remove(file) for file in (tmpName1, tmpName2, tmpName3)]

if __name__ == "__main__":
    import argparse # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(description='Markdown wrapper with slide and bibliographic options')
    arg_parser.add_argument('files', nargs='+',  metavar='FILE')
    arg_parser.add_argument("-b", "--bibliography",
                    action="store_true", default=False,
                    help="turn citations into hypertext w/out CSL")
    arg_parser.add_argument("-c", "--css", 
                    default='http://reagle.org/joseph/2003/papers.css',
                    help="apply non-default CSS")
    arg_parser.add_argument("-d", "--divs", 
                    action="store_true", default=False,
                    help="use pandoc's --section-divs")
    arg_parser.add_argument("-l", "--launch-browser",
                    action="store_true", default=False,
                    help="launch browser to see results")
    arg_parser.add_argument("-o", "--offline",
                    action="store_true", default=False,
                    help="incorporate links: scripts, images, and CSS.")
    arg_parser.add_argument("-p", "--presentation",
                    action="store_true", default=False,
                    help="create presentation with dzsslides")
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
    args = arg_parser.parse_args()
    pandoc_opts = ['-s', '--smart', '--tab-stop', '4', 
        '--email-obfuscation=references'] 
    if args.presentation:
        args.validate = False
        args.css = False
        pandoc_opts.extend(['--template=class.dzslides', 
            '-t', 'dzslides', '--slide-level=2'])
    if args.css:
        pandoc_opts.extend(['-c', args.css])
    if args.toc:
        pandoc_opts.extend(['--toc'])
    if args.offline:
        pandoc_opts.extend(['--self-contained'])
    if args.divs:
        pandoc_opts.extend(['--section-divs'])
    if args.style_chicago:
        args.style_csl = ['chicago-author-date']
    if args.style_csl:
        print(("args.style_csl = %s" % args.style_csl))
        pandoc_opts.extend(['--bibliography=%s' % HOME+'/joseph/readings.bib',])
        pandoc_opts.extend(['--csl=%s' % args.style_csl[0]])

    process(args.files)
