#!/usr/bin/python3.2
# -*- coding: utf-8 -*-
# (c) Copyright 2007-2012 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

'''Like bd, but will build HTML using htlatex.'''

import codecs
from glob import glob
from optparse import OptionParser
import os
from os import path
import re
import shutil
from subprocess import call, check_call, Popen, PIPE
import sys

from os import environ
HOME = environ['HOME']

import argparse # http://docs.python.org/dev/library/argparse.html
arg_parser = argparse.ArgumentParser(description='Build HTML from markdown')

# positional arguments
arg_parser.add_argument('files', nargs='+', metavar='FILE')

# optional arguments
arg_parser.add_argument("-k", "--keep-src-html", action="store_true", default=False,
                help="keep the source HTML file for examination or reuse")
arg_parser.add_argument("-a", "--auto-notes", action="store_true", default=False,
                help="create auto-numbered notes for MS Word rather than manual notes")
arg_parser.add_argument("-n", "--navigation", action="store_true", default=False,
                help="use navigation elements on header/footer of pages")
arg_parser.add_argument("-o", "--online-URLs-only", action="store_true", default=False,
                help="only include URLs that are exclusively online")
arg_parser.add_argument("-l", "--long-URL",
                action="store_true", default=False,
                help="use long URLs")
arg_parser.add_argument("-p", "--paragraph-marks", action="store_true", default=False,
                help="add name/ids for paragraphs")
arg_parser.add_argument("-r", "--reuse", action="store_true", default=False,
                help="reuse existing HTML files, rather than a LaTeX rebuild")
arg_parser.add_argument("-s", "--single-page", action="store_true", default=False,
                help="create HTML as a single page")

args = arg_parser.parse_args()
files = args.files

if args.online_URLs_only:
    fe_opts = '-co'
else:
    fe_opts = '-c'
if args.long_URL: fe_opts += 'l'
if args.reuse:
    shell_command = shutil.copy
else:
    shell_command = shutil.move
if args.single_page:
    htlatex_opts = 'html,fn-in'
else:
    htlatex_opts = '"html,2"'

if not files:
    files = [HOME+'/joseph/2010/faith']
if '2010/faith' in files[0]:
    FILE_MAPPING = {
        '0-book.html'    : 'title.html',
        '0-bookch1.html' : 'foreward.html',
        '0-bookch2.html' : 'preface-web.html',
        '0-bookch3.html' : 'preface.html',
        '0-bookch4.html' : 'chapter-1.html',
        '0-bookch5.html' : 'chapter-2.html',
        '0-bookch6.html' : 'chapter-3.html',
        '0-bookch7.html' : 'chapter-4.html',
        '0-bookch8.html' : 'chapter-5.html',
        '0-bookch9.html' : 'chapter-6.html',
        '0-bookch10.html' : 'chapter-7.html',
        '0-bookch11.html' : 'chapter-8.html',
        '0-bookch12.html' : 'references.html',
        '0-bookli1.html' : 'toc.html',
        '0-bookli2.html' : 'bibliography.html',
        }
else:
    FILE_MAPPING = {}

file = files[0]
print("file = %s" % file)
if path.isfile(file):
    src_dir = path.realpath(path.split(file)[0]) + '/'
    project = path.split(file)[1]
    dst_dir = src_dir + 'latex-' + project[:3] + '/'
    base_file_name = '0-article'
    build_file_base = dst_dir + base_file_name
else:
    src_dir = path.realpath(file) + '/'
    project = path.split(src_dir[:-1])[1]
    files = [path.basename(file) for file in
        sorted(glob(src_dir +'[!~]*.doc') + glob(src_dir +'[!~]*.mkd'))]
    dst_dir = src_dir + 'latex-' + project[:3] + '/'
    base_file_name = '0-book'
    build_file_base = dst_dir + base_file_name
html_dir = dst_dir + 'html/'
build_file = build_file_base + '.tex'
html_file = build_file_base + '.html'
tmp_html_file = html_file + '.tmp'

print("************")
print("src_dir = %s " %src_dir)
print("dst_dir = %s " %dst_dir)
print("build_file_base = %s " %build_file_base)

#----------------------------
# Build
#----------------------------

os.chdir(dst_dir)

if not args.reuse:
    print("** calling fe, bibtex8, and htlatex")
    call(['fe', fe_opts], stdout=open(HOME+'/joseph/readings.bib', 'w'))
    print((' '.join(['bibtex8', '-W', '--mentstrs', '30000', '-c', '88591lat.csf', base_file_name])))
    call(['bibtex8', '-W', '--mentstrs', '30000', '-c', '88591lat.csf', base_file_name])
    print((' '.join(['*** htlatex', build_file_base, htlatex_opts])))
    call(['htlatex', build_file_base, htlatex_opts])
    #args.keep_src_html = True
print("** copying files to html dir")
[os.remove(old_file) for old_file in glob('html/*.html')] # remove html files from prev build
[shutil.copy(html_file, html_dir) for html_file in glob('0-*.html')]
if not args.keep_src_html:
    [os.remove(html_file) for html_file in glob('0-*.html')]

print("** changing dir")
os.chdir(html_dir)

print("** renaming files")
if FILE_MAPPING:
    print("**** FILE_MAPPING", FILE_MAPPING)
    for old, new in list(FILE_MAPPING.items()):
        print("**** old, new", old, new)
        os.rename(old, new)

#----------------------------
# Process files
#----------------------------

toc_heading_map = {} # map between htlatex toc generated ids and my ids

for html_file in sorted(glob('*.html')):
    print('\n' + html_file + ': ')

    data = codecs.open(html_file, 'r', 'iso-8859-1').read()

    print("** rewriting links to files")
    if FILE_MAPPING:
        for old, new in list(FILE_MAPPING.items()):
            data = data.replace(old, new)

    #----------------------------
    # XML parser cleanup
    #----------------------------

    print("** load lxml soup")
    from lxml.etree import *
    from lxml.html import tostring
    from io import StringIO
    parser = HTMLParser(remove_comments = True, remove_blank_text = True)

    print("** parse without comments")
    doc = parse(StringIO(data), parser)

    print("** upgrade each heading number")
    for num in 2, 3, 4:
        for h in doc.xpath("//h%d" %num):
            h.tag = 'h' + str(num - 1)

    print("** add charset UTF-8")
    head = doc.xpath("/html/head")[0]
    meta_charset = SubElement(head, "meta", content="application/xhtml+xml; charset=UTF-8")
    meta_charset.set('http-equiv', 'content-type')

    print("** add specific styles")
    style = SubElement(head, "style", type="text/css")
    if not args.auto_notes:
        style.text = 'div.footnotes{ font-style:normal;}'
    else:
        style.text = '''div.footnotes{ font-style:normal;}
        p {margin: 0in;}

        span.MsoEndnoteReference
            {mso-style-noshow:yes;
            vertical-align:super;}
        p.MsoEndnoteText, li.MsoEndnoteText, div.MsoEndnoteText
            {mso-style-noshow:yes;
            margin:0in;
            margin-bottom:.0001pt;
            mso-pagination:widow-orphan;}
        @page
            {mso-endnote-numbering-style:arabic;}
        @page Section1
            {size:8.5in 11.0in;
            margin:1.5in 1.5in 1.5in 1.5in;
            mso-header-margin:.5in;
            mso-footer-margin:.5in;
            mso-paper-source:0;}
        div.Section1
            {page:Section1;
            mso-endnote-numbering-style:arabic;}'''

    if not args.navigation:
        print("** remove navigation links")
        crosslinks = doc.xpath("//div[@class='crosslinks']")
        for crosslink in crosslinks:
            crosslink.getparent().remove(crosslink)

    print("** convert spans to italics")
    for span in doc.xpath("//span[@class='ptmri8t-x-x-120']"):
        span.tag = 'em'
        del span.attrib['class']

    print("** create blockquotes")
    divs = doc.xpath("//div[@class='quote']")
    for div in divs:
        div.tag = 'blockquote'
        del div.attrib['class']

    print("** first p of blockquote is noindent")
    bqs = doc.xpath("//blockquote")
    for bq in bqs:
        bq[0].set('class', 'noindent')

    file_cache = {}
    print("** include biblio info in popups")
    hypers = doc.xpath("//a[@href]")
    for hyper in hypers:
        if 'ennote' in hyper.get('href'):
            biblio_fn, ennote = hyper.get('href').split('#')
            if biblio_fn in file_cache:
                biblio_doc = file_cache[biblio_fn]
            else:
                biblio_parser = HTMLParser(remove_comments = True)
                biblio_doc = parse(biblio_fn, biblio_parser)
                file_cache[biblio_fn] = biblio_doc
            p_of_ref = biblio_doc.xpath("//a[@id='%s']/parent::p" % ennote)[0]
            if p_of_ref:
                ref_txt = tostring(p_of_ref, method="text", encoding=str).strip()
                if len(ref_txt) >= 250:
                    ref_txt = ref_txt[:250] + ' ...'
                ref_txt = re.sub('\d+(.*)', r'\1', ref_txt, count=1) # , count=1
                span_popup = SubElement(hyper, 'span')
                span_popup.set('class', 'balloon')
                span_popup.text = ref_txt


    if args.paragraph_marks:
        if html_file.startswith('chapter') or html_file.startswith('reference'):
            print("** add heading marks")
            headings = doc.xpath("//*[name()='h1' or name()='h2' or name()='h3' or name()='h4']")
            heading_num = 1
            for heading in headings:
                span = Element("span") # prepare span element for section #
                span.set('class', 'headingnum')
                heading_a = heading.xpath('a[position()=1]')[0]
                htlatex_id = heading_a.get('id')  # grab id of existing a element
                span.tail = heading_a.tail
                heading.remove(heading_a) # delete 'a' element as I'm replacing it with span
                a_id = 's' + str(heading_num)
                a = SubElement(span, 'a', id=a_id, name=a_id, href='#%s' % a_id)
                a.text = '§' + str(heading_num)
                heading.append(span)
                toc_heading_map[htlatex_id] = a_id
                heading_num += 1

        if html_file.startswith('chapter'):
            print("** add paragraph-marks")
            paras = doc.xpath('//p[not(parent::div[@class="crosslinks"])]')
            para_num = 1
            for para in paras:
                if para != None and not para.text.isspace():
                    span = Element("span")
                    span.set('class', 'paranum')
                    span.tail = para.text
                    a_id = 'p' + str(para_num)
                    a = SubElement(span, 'a', id=a_id, name=a_id, href='#%s' % a_id)
                    a.text = '¶' + str(para_num)
                    para.text = None
                    para.insert(0, span) # insert span at beginning of parent
                    para_num += 1

    print("** remove unnecesssary chapter cruft in Notes")
    for p in doc.xpath("//div[@class='center']/p[@class='noindent']"):
        spans = p.xpath("span")
        if len(spans) == 3:
            if not spans[1].text.strip().isdigit(): # remove "Chapter 8" from Ch1 notes
                div = spans[1].getparent().getparent()
                div_parent = div.getparent()
                div_parent.remove(div)
            else: # remove extra non-hypertextual chapter numbered
                spans[1].text = ''
            p.tag = 'h3' # made it into a subheading
            p.text = tostring(p, method="text", encoding=str).strip()
            [p.remove(span) for span in p] # rm its erroneous span and href

    ##------------------------
    ## Manual notes
    ##------------------------
    #if not args.auto_notes:
        #print "** remove endnote superscripts",
        #spans = doc.xpath("//sup/span[@class='cmr-8']")
        #for span in spans:
            #span.text = span.text + '. '
            #sup = span.getparent()
            #grandparent = sup.getparent()
            #grandparent.replace(sup, span)
    #------------------------
    # Manual notes
    #------------------------
    if not args.auto_notes:
        print("** pretty up endnotes")
        a_note_nums = doc.xpath("//span[@class='footnote-mark']/a")
        for note_number in a_note_nums:
            if note_number.text:
                note_number.text = note_number.text + ' '
    #------------------------
    # MS Word notes
    #------------------------
    else: # footnotes for MS Word
        if doc.xpath('//h2[text() = "Notes"]'):
            print("** creating MS Word sections")
            body = doc.xpath('body')[0]
            section1 = Element('div')
            section1.set("class", "Section1")
            ref_loc = body.index(body.xpath('//h2[text() = "Notes"]')[-1])
            section1.extend(body[0:ref_loc])
            notes = Element('div', style="mso-element:endnote-list")
            notes.extend(body)
            body.clear()
            body.append(section1)
            body.append(notes)

        print("** remove remote a hrefs")
        hypers = doc.xpath("//a[@href]")
        for hyper in hypers:
            if 'edn' not in hyper.get('href'):
                del hyper.attrib['href']


        ms_ftn_txt = '''<sup><a style="mso-endnote-id:edn%d" href="#_edn%d" name="_ednref%d" title=""><span class="MsoEndnoteReference"><span style='mso-special-character:footnote'></span></span></a></sup>'''

        print("** convert inline notes to MS Word")
        spans = doc.xpath("//sup/a/span[@class='cmr-8']")
        for span in spans:
            number = int(span.text)
            a = span.getparent()
            sup = a.getparent()
            grandparent = sup.getparent()
            ms_ftn = XML(ms_ftn_txt % (number, number, number))
            ms_ftn.tail = sup.tail
            grandparent.replace(sup, ms_ftn)


        ms_endnote_txt= '''<div style="mso-element:endnote" id="edn%d"><p class="MsoEndnoteText"><a style="mso-endnote-id:edn%d" href="#_ednref%d" name="_edn%d" title=""><span class="MsoEndnoteReference"><span style="vertical-align: baseline; mso-special-character: footnote"></span></span></a>. <span class="GramE"> %s</span></p></div>'''

        print("** convert end notes to MS Word")
        spans = doc.xpath("//sup/span[@class='cmr-8']")
        for span in spans:
            number = int(span.text)
            sup = span.getparent()
            a = sup.getparent()
            p = a.getparent()
            prenote = a.tail if a.tail else ''
            reference_txt = prenote + ''.join([tostring(node) for node in p[1:]])
            ancestor = p.getparent()
            ms_endnote = XML(ms_endnote_txt % (number, number, number, number,
                reference_txt))
            ancestor.replace(p, ms_endnote)


    #----------------------------
    # String manipulations
    #----------------------------

    new_data = tostring(doc, method='html', include_meta_content_type=False, encoding=str)

    print("** replace indent with tab")
    new_data = new_data.replace('<p class="indent">       ', '<p>&#09;')\
        .replace('<p class="indent">', '<p>')

    print('** Fix htlatex bugs: s/",/,"/ s/visited on/accessed/')
    new_data = new_data.replace('”, ', ',” ')\
        .replace('(visited on</span>', '(accessed</span>')

    if args.paragraph_marks and html_file == ('toc.html'):
        print('** Update ids in toc.html')
        for htlatex_id, a_id in list(toc_heading_map.items()):
            new_data = new_data.replace(htlatex_id, a_id)

    #----------------------------
    # File manipulations
    #----------------------------


    tmp_html_fd = codecs.open(tmp_html_file, "w", "UTF-8", "replace")
    tmp_html_fd.write(new_data)
    tmp_html_fd.close()

    print("** tidying 1")
    call(['tidy', '-modify', '-quiet', '-utf8',
         #'--hide-comments', 'True','-numeric',
         #'--clean', ' --merge-divs',  '--merge-spans',
        tmp_html_file])

    print("** validating")
    p = Popen(['validate', tmp_html_file], stdout=PIPE)
    print(p.stdout.read())

    print("** renaming tmp to original")
    os.rename(tmp_html_file, html_file)
