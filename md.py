#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Copyright 2008-2012 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

'''A wrapper script for pandoc that handles my own issues:
    1. associates the result with a particular style sheet.
    2. can replace [@key] with hypertext'd refs from bibtex database.
    3. makes use of reveal.js for presentations.
'''

# TODO:
#     1. reduce redundant references: page only, if key already cited
#     2. replace square brackets with round when no URL.
#     3. restore move_punctuation_outside,
#         move each of these periods to right of quotation mark:
#         a. if using note style: "I do what I hate" [#@Paul2006r7].
#         b. all styles: "Testes Testes Testes."

import codecs
from io import StringIO
from lxml.etree import *
from lxml.html import tostring
import logging
import md2bib
import os
from os import chdir, environ, mkdir, path, rename, remove, walk
from os.path import abspath, basename, dirname, exists, \
    expanduser, getmtime, join, relpath, splitext
import re
import shutil
# from sh import chmod # http://amoffat.github.com/sh/
import subprocess
from subprocess import call, check_output, Popen
import sys

HOME = expanduser("~") if exists(expanduser("~")) else None
BROWSER = environ['BROWSER'].replace(
    '*', ' ') if 'BROWSER' in environ else None
PANDOC_BIN = shutil.which("pandoc")
if not all([HOME, BROWSER, PANDOC_BIN]):
    raise FileNotFoundError("Your environment is not configured correctly")

log_level = 100  # default
critical = logging.critical
info = logging.info
dbg = logging.debug
warn = logging.warn
error = logging.error
excpt = logging.exception


def link_citations(line, bib_chunked):
    """
    Turn pandoc/markdown citations into links within parenthesis.
    Used only with citations in presentations.
    """

    P_KEY = re.compile(r'(-?@[\w|-]+)')  # -@Clark-Flory2010fpo

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
        reference = bib_chunked.get(key)
        info(reference)
        if reference is None:
            print("WARNING: key %s not found" % key)
            return key
        url = reference.get('url')
        title = reference.get('shorttitle')
        last_name, year, _ = re.split('(\d\d\d\d)', key)

        if 'origdate' in reference:
            year = reference['origdate']  # + "/" + year

        if citation.startswith('-'):
            key_text = re.findall(r'\d\d\d\d.*', key)[0]  # year
        else:
            key_text = "%s %s" % (last_name, year)

        # info("**   url = %s" % url)
        if url:
            cite_replacement.append('[%s](%s)' % (key_text, url))
        else:
            if title:
                title = title.replace('{', '').replace('}', '')
                cite_replacement.append('%s, "%s"' % (key_text, title))
            else:
                cite_replacement.append('%s' % key_text)
        # info("**   using cite_replacement = %s" % cite_replacement)
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


def process_commented_citations(line):

    # match stuff within a bracket (beginning with ' ' or '^') that
    # has no other brackets within
    P_BRACKET_PAIR = re.compile(r'[ |^]\[[^\[]+[-#]?@[^\]]+\]')

    def quash(cite_match):
        """
        Collect and rewrite citations.
        if args.quash_citations drop citation [#@Reagle2012foo]
        else uncomment
        """
        citation = cite_match.group(0)
        critical("citation = '%s'" % (citation))
        prefix = '^' if citation[0] == '^' else ' '
        chunks = citation[2:-1].split(';')  # isolate chunks from ' [' + ']'
        critical("chunks = %s" % (chunks))
        citations_keep = []
        for chunk in chunks:
            critical("  chunk = '%s'" % (chunk))
            if '#@' in chunk:
                if args.quash_citations:
                    pass
                    critical("  quashed")
                else:
                    chunk = chunk.replace('#@', '@')
                    critical("  keeping chunk = '%s'" % (chunk))
                    citations_keep.append(chunk)
            else:
                citations_keep.append(chunk)

        if citations_keep:
            critical("citations_keep = '%s'" % (citations_keep))
            return f'{prefix}[' + ';'.join(citations_keep) + ']'
        else:
            return ''

    new_line = P_BRACKET_PAIR.subn(quash, line)[0]
    # if I quashed a citation completely, I might have a period after a quote
    if args.quash_citations:
        if '].' in line and '".' in new_line:  # imperfect test
            new_line = new_line.replace('".', '."')
    return new_line


def create_talk_handout(abs_fn, tmp2_fn):
    '''If talks and handouts exists, create (partial) handout'''

    info("starting handout")
    EM_RE = re.compile(r'(?<! _)_([^_]+?)_\W')

    def em_mask(matchobj):
        """replace emphasis with underscores"""
        info("return replace function")
        # underscore that pandoc will ignore
        return '&#95;' * len(matchobj.group(0))

    info("abs_fn = '%s'" % (abs_fn))
    info("tmp2fn = '%s'" % (tmp2_fn))
    md_dir = dirname(abs_fn)
    handout_fn = ''
    if '/talks' in abs_fn:
        handout_fn = abs_fn.replace('/talks/', '/handouts/')
        handout_dir = dirname(handout_fn)
        info("handout_dir = '%s'" % (dirname(handout_fn)))
    if exists(dirname(handout_fn)):
        info("creating handout")
        skip_to_next_header = False
        handout_f = open(handout_fn, 'w')
        content = open(tmp2_fn, 'r').read()
        info("md_dir = '%s', handout_dir = '%s'" % (md_dir, handout_dir))
        media_relpath = relpath(md_dir, handout_dir)
        info("media_relpath = '%s'" % (media_relpath))
        content = content.replace(' data-src=', ' src=')
        content = content.replace('](media/', '](%s/media/' % media_relpath)
        content = content.replace('="media/', '="%s/media/' % media_relpath)
        lines = [line + '\n' for line in content.split('\n')]
        for line in lines:
            if line.startswith('<details'):  # skip rules
                skip_to_next_header = True
                info("skipping line = '%s'" % line)
                continue
            if args.partial_handout:
                info("args.partial_handout = '%s'" % (args.partial_handout))
                line = line.replace('### ', ' ')
                # skip slides with underscore in heading
                if line.startswith('# ') or line.startswith('## '):
                    if ' _' in line:
                        skip_to_next_header = True
                    else:
                        skip_to_next_header = False
                    handout_f.write(line)
                else:
                    if not skip_to_next_header:
                        # eg: if line.startswith('> *'): continue
                        info("entering em redaction")
                        # replace emph underscores  w/ literal '_'
                        line = EM_RE.subn(em_mask, line)[0]
                        info("line = '%s'" % (line))
                        handout_f.write(line)
                    else:
                        handout_f.write('\n')
            else:
                handout_f.write(line)
        handout_f.close()
        md_cmd = ['md', '--divs', '--toc', '-w', 'html', '-c',
                  'https://reagle.org/joseph/talks/_custom/class-handouts-201306.css',
                  handout_fn]
        info("md_cmd = %s" % ' '.join(md_cmd))
        call(md_cmd)
        if not args.keep_tmp:
            remove(handout_fn)
    info("done handout")


def number_elements(content):
    "add section and paragraph marks to content which is parsed as HTML"

    info("parsing without comments")
    parser = HTMLParser(remove_comments=True, remove_blank_text=True)
    doc = parse(StringIO(content), parser)

    info("add heading marks")
    headings = doc.xpath("//*[name()='h2' or name()='h3' or name()='h4']")
    heading_num = 1
    for heading in headings:
        span = Element("span")  # prepare span element for section #
        span.set('class', 'headingnum')
        h_id = heading.get('id')  # grab id of existing a element
        span.tail = heading.text
        a = SubElement(span, 'a', href='#%s' % h_id)
        heading.text = None  # this has become the tail of the span
        a.text = '§' + str(heading_num) + u'\u00A0'  # &nbsp;
        heading.insert(0, span)  # insert span at beginning of parent
        heading_num += 1

    info("add paragraph marks")
    paras = doc.xpath('/html/body/p | /html/body/blockquote')
    para_num = 1
    for para in paras:
        para_num_str = '{:0>2}'.format(para_num)
        span = Element("span")
        span.set('class', 'paranum')
        span.tail = para.text
        a_id = 'p' + str(para_num_str)
        a = SubElement(span, 'a', id=a_id, name=a_id, href='#%s' % a_id)
        a.text = 'p' + str(para_num_str) + u'\u00A0'  # &nbsp;
        para.text = None
        para.insert(0, span)
        para_num += 1

    content = tostring(doc, method='xml', encoding='utf-8', pretty_print=True,
                       include_meta_content_type=True).decode('utf-8')

    return content


def process(args):

    if args.bibliography:
        bib_fn = HOME + '/joseph/readings.yaml'
        bib_chunked = md2bib.chunk_yaml(open(bib_fn, 'r').readlines())
        info("bib_chunked = %s" % (bib_chunked))

    info("args.files = '%s'" % args.files)
    for in_file in args.files:
        if not in_file:
            continue
        info("in_file = '%s'" % in_file)

        ##############################
        # initial pandoc configuration based on arguments
        ##############################

        pandoc_inputs = []
        pandoc_opts = ['-w', args.write]
        # if args.write == 'markdown-citations':
        #     pandoc_opts.extend(['--csl=sage-harvard.csl',
        #         '--bibliography=/home/reagle/joseph/readings.yaml'])
        pandoc_opts.extend(['-s', '--tab-stop', '4',
                            '--email-obfuscation=references'])

        if args.presentation:
            args.validate = False
            args.css = False
            pandoc_opts.extend([
                '-c', '../_custom/reveal3js.css',
                '-c', '../_custom/Font-Awesome/css/font-awesome.min.css',
                '-t', 'revealjs', '--slide-level=2',
                '-V', 'revealjs-url=../_reveal3.js',
                '-V', 'theme=beige',
                '-V', 'transition=linear',
                '-V', 'history=true',
                '-V', 'zoomKey=shift',
                # '--no-highlight', # conflicts with reveal's highlight.js
            ])
        if args.write == 'html' and args.css:
            pandoc_opts.extend(['-c', args.css])
        elif args.write == 'docx':
            pandoc_opts.extend(['--reference-doc',
                                HOME + '/.pandoc/reference-mit-press.docx'])
        if args.condensed:
            pandoc_opts.extend(
                ['-c', 'https://reagle.org/joseph/2003/papers-condensed.css'])
        if args.toc:
            pandoc_opts.extend(['--toc'])
            if args.toc_depth:
                pandoc_opts.extend(['--toc-depth=%s' % args.toc_depth[0]])
        if args.self_contained:
            pandoc_opts.extend(['--self-contained'])
        if args.divs:
            pandoc_opts.extend(['--section-divs'])
        if args.include_after_body:
            pandoc_opts.extend(['--include-after-body=%s' %
                                args.include_after_body[0]])
        if args.style_chicago:
            args.style_csl = ['chicago-author-date.csl']

        ##############################
        # pre pandoc
        ##############################

        info("in_file = '%s'" % (in_file))
        abs_fn = abspath(in_file)
        info("abs_fn = '%s'" % (abs_fn))

        base_fn, base_ext = splitext(abs_fn)
        info("base_fn = '%s'" % (base_fn))

        fn_path = os.path.split(abs_fn)[0]
        info("fn_path = '%s'" % (fn_path))

        bib_subset_tmp_fn = None  # fn of subset of main biblio
        fn_tmp_1 = "%s-1%s" % (base_fn, base_ext)  # as read
        fn_tmp_2 = "%s-2%s" % (base_fn, base_ext)  # pre-pandoc
        fn_tmp_3 = "%s-3.%s" % (base_fn, args.write)  # post-pandoc copy
        fn_result = base_fn + '.' + args.write
        cleanup_tmp_fns = [fn_tmp_1, fn_tmp_2, fn_tmp_3]

        pandoc_opts.extend(['-o', fn_result])
        pandoc_opts.extend(['--mathjax'])

        if args.style_csl:
            if args.bibtex:
                bib_fn = HOME + '/joseph/readings.bib'
                bib_ext = '.bib'
                parse_func = md2bib.parse_bibtex
                subset_func = md2bib.subset_bibtex
                emit_subset_func = md2bib.emit_bibtex_subset
            else:
                bib_fn = HOME + '/joseph/readings.yaml'
                bib_ext = '.yaml'
                parse_func = md2bib.chunk_yaml
                subset_func = md2bib.subset_yaml
                emit_subset_func = md2bib.emit_yaml_subset

            pandoc_opts.extend(['--csl=%s' % args.style_csl[0]])
            info("generate temporary subset bib for speed")
            bib_subset_tmp_fn = base_fn + bib_ext
            cleanup_tmp_fns.append(bib_subset_tmp_fn)
            keys = md2bib.get_keys_from_md(abs_fn)
            info("keys = %s" % keys)
            if keys:
                entries = parse_func(open(bib_fn, 'r').readlines())
                subset = subset_func(entries, keys)
                emit_subset_func(subset, open(bib_subset_tmp_fn, 'w'))
                # deprecate for YAML workaround: bug https://github.com/jgm/pandoc-citeproc/issues/272
                # pandoc_opts.extend(['--bibliography=%s' % bib_subset_tmp_fn,])
                pandoc_opts.extend(['--filter', 'pandoc-citeproc', ])

        print((abs_fn, fn_tmp_1))
        shutil.copyfile(abs_fn, fn_tmp_1)
        f1 = codecs.open(fn_tmp_1, 'r', "UTF-8", "replace")
        content = f1.read()
        if content[0] == codecs.BOM_UTF8.decode('utf8'):
            content = content[1:]
        f2 = codecs.open(fn_tmp_2, 'w', "UTF-8", "replace")

        print("split(abs_fn) = %s, %s" % (os.path.split(abs_fn)))

        # content = content.replace(' --- ', '---') # what is this 20161215?

        lines = content.split('\n')
        new_lines = []

        for lineNo, line in enumerate(lines):
            # fix Wikicommons relative network-path references
            # so the URLs work on local file system (i.e.,'file:///')
            line = line.replace('src="//', 'src="http://')
            # TODO: encode ampersands in URLs
            # TODO: remove Gregg diagnostics
            if 'Gregg' in line:
                critical("before = '%s'" % (line))
            line = process_commented_citations(line)
            if 'Gregg' in line:
                critical("after = '%s'" % (line))
            if args.bibliography:  # create hypertext refs from bibtex db
                line = link_citations(line, bib_chunked)
                # info("\n** line is now %s" % line)
            if args.presentation:  # color some revealjs top of column slides
                if line.startswith('# ') and '{data-' not in line:
                    line = line.strip() + ' {data-background="LightBlue"}\n'
            # info("END line: '%s'" % line)
            new_lines.append(line)
        f1.close()
        f2.write('\n'.join(new_lines))
        f2.close()

        ##############################
        # pandoc
        ##############################

        pandoc_cmd = [
            PANDOC_BIN, '-f', 'markdown+mmd_title_block+yaml_metadata_block'
            '+smart+implicit_header_references' '+superscript+subscript'
            '+tex_math_dollars' '+autolink_bare_uris']
        pandoc_cmd.extend(pandoc_opts)
        pandoc_inputs.insert(0, fn_tmp_2)
        pandoc_cmd.extend(pandoc_inputs)
        # YAML workaround: bug
        # https://github.com/jgm/pandoc-citeproc/issues/272
        if bib_subset_tmp_fn:
            pandoc_cmd.extend([bib_subset_tmp_fn])
        print("joined pandoc_cmd: " + ' '.join(pandoc_cmd) + '\n')
        call(pandoc_cmd)  # , stdout=open(fn_tmp_3, 'w')
        info("done pandoc_cmd")

        if args.presentation:
            create_talk_handout(abs_fn, fn_tmp_2)

        ##############################
        # post pandoc content
        ##############################

        if args.write == 'html':

            # final tweaks html file
            shutil.copyfile(fn_result, fn_tmp_3)  # copy of html for debugging
            content_html = open(fn_tmp_3, 'r').read()
            if not content_html:
                raise ValueError('post-pandoc content_html is empty')
                sys.exit()

            # text alterations
            if args.british_quotes:  # swap double/single quotes
                content_html = content_html.replace(
                    '"', '&ldquo;').replace('"', '&rdquo;')
                single_quote_re = re.compile(r"(\W)'(.{2,40}?)'(\W)")
                content_html = single_quote_re.sub(r'\1"\2"\3', content_html)
                content_html = content_html.replace(
                    '&ldquo;', r"'").replace('&rdquo;', "'")
            # correct bibliography
            content_html = content_html.replace(' Vs. ', ' vs. ')

            if args.presentation:
                # convert to data-src for lazy loading
                lazy_elements_re = re.compile(
                    r'''(\<img|<iframe|<video)(.*?) src=''')
                content_html = lazy_elements_re.sub(
                    r'\1\2 data-src=', content_html)

            # HTML alterations
            if args.number_elements:
                content_html = number_elements(content_html)

            result_fn = '%s.html' % (base_fn)
            info("result_fn = '%s'" % (result_fn))
            if args.output:
                result_fn = args.output[0]
            open(result_fn, 'w').write(content_html)

            if args.validate:
                call(['tidy', '-utf8', '-q', '-i', '-m', '-w', '0', '-asxhtml',
                      result_fn])
            if args.launch_browser:
                info("launching %s" % result_fn)
                Popen([BROWSER, result_fn])

        if not args.keep_tmp:
            info("removing tmp files")
            for cleanup_fn in cleanup_tmp_fns:
                if exists(cleanup_fn):
                    remove(cleanup_fn)


if __name__ == "__main__":
    import argparse  # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(
        description='Markdown wrapper with slide and bibliographic options')
    arg_parser.add_argument(
        'files', nargs='+', metavar='FILE')
    arg_parser.add_argument(
        "-b", "--bibliography",
        action="store_true", default=False,
        help="turn citations into hypertext w/out CSL")
    arg_parser.add_argument(
        "--bibtex",
        action="store_true", default=False,
        help="use .bib file instead of YAML bibliography")
    arg_parser.add_argument(
        "-B", "--british-quotes",
        action="store_true", default=False,
        help="swap single and double quotes")
    arg_parser.add_argument(
        "-q", "--quash-citations",
        action="store_true", default=False,
        help="quash citations that begin with hash (#@Reagle2012foo)")
    arg_parser.add_argument(
        "-c", "--css",
        default='https://reagle.org/joseph/2003/papers.css',
        help="apply non-default CSS")
    arg_parser.add_argument(
        "--condensed",
        action="store_true", default=False,
        help="use condensed line spacing CSS")
    arg_parser.add_argument(
        "-d", "--divs",
        action="store_true", default=False,
        help="use pandoc's --section-divs")
    arg_parser.add_argument(
        "--include-after-body",
        nargs=1, metavar='FILE',
        help="include at end of body (pandoc pass-through)")
    arg_parser.add_argument(
        "-k", "--keep-tmp",
        action="store_true", default=False,
        help="keep temporary/intermediary files")
    arg_parser.add_argument(
        "-l", "--launch-browser",
        action="store_true", default=False,
        help="launch browser to see results")
    arg_parser.add_argument(
        "-o", "--output", nargs=1,
        help="output file path")
    arg_parser.add_argument(
        "--self-contained",
        action="store_true", default=False,
        help="incorporate links: scripts, images, and CSS")
    arg_parser.add_argument(
        "-n", "--number-elements",
        action="store_true", default=False,
        help="number sections and paragraphs")
    arg_parser.add_argument(
        "-s", "--style-chicago",
        action="store_true", default=False,
        help="use CSL bibliography style, default chicago-author-date.csl")
    arg_parser.add_argument(
        "-S", "--style-csl", nargs=1,
        help="specify CSL style [chicago-fullnote-bibliography.csl, ...]")
    arg_parser.add_argument(
        "-t", "--toc",
        action="store_true", default=False,
        help="create table of contents")
    arg_parser.add_argument(
        "--toc-depth", nargs=1,
        help="table of contents depth")
    arg_parser.add_argument(
        "-v", "--validate",
        action="store_true", default=False,
        help="validate and tidy HTML")
    arg_parser.add_argument(
        "-p", "--presentation",
        action="store_true", default=False,
        help="create presentation with reveal.js")
    arg_parser.add_argument(
        "--partial-handout",
        action="store_true", default=False,
        help="presentation handout is partial/redacted")
    arg_parser.add_argument(
        "-w", "--write",
        default='html',
        help="Write to format [html, markdown-citations,...]")
    arg_parser.add_argument(
        '-L', '--log-to-file',
        action="store_true", default=False,
        help="log to file PROGRAM.log")
    arg_parser.add_argument(
        '-V', '--verbose', action='count', default=0,
        help="Increase verbosity (specify multiple times for more)")
    arg_parser.add_argument('--version', action='version', version='TBD')

    args = arg_parser.parse_args()

    if args.verbose == 1:
        log_level = logging.CRITICAL
    elif args.verbose == 2:
        log_level = logging.INFO
    elif args.verbose >= 3:
        log_level = logging.DEBUG
    LOG_FORMAT = "%(levelno)s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(filename='wiki-update.log', filemode='w',
                            level=log_level, format=LOG_FORMAT)
    else:
        logging.basicConfig(level=log_level, format=LOG_FORMAT)

    process(args)
