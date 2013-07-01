#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Build the static portions of my website by looking for source files newer than existing HTML files.
*.mm (freemind)-> html
*.md (pandoc)-> html
zim/* (zim-wiki) -> html

"""

import codecs
import fnmatch
import hashlib
from lxml import etree, html
import logging
import md
from os import chdir, chmod, environ, mkdir, path, rename, remove, walk
from os.path import abspath, basename, dirname, exists, \
    getmtime, join, relpath, splitext
import re
from shutil import copy, rmtree, move
from subprocess import call, check_output, Popen, PIPE
import sys
import time
#import webbrowser

HOME = environ['HOME']

log_level = 100 # default
critical = logging.critical
info = logging.info
dbg = logging.debug
warn = logging.warn
error = logging.error
excpt = logging.exception


#################################
# Utility functions

def get_Now_YMD():
    '''
    Now in YearMonthDay format
    '''

    now = time.localtime()

    date_token = time.strftime("%y%m%d", now)
    return date_token


def locate(pattern, root):
    '''Locate all files matching supplied filename pattern in and below
    supplied root directory.'''
    for path, dirs, files in walk(abspath(root)):
        for filename in fnmatch.filter(files, pattern):
            yield join(path, filename)

def has_dir_changed(directory):
    
        info('dir   = %s' %directory)
        checksum_file = directory + '.dirs.md5sum'
        checksum = Popen(["ls -l -R %s | md5sum" % directory], 
                shell=True, stdout=PIPE).communicate()[0]
        checksum = checksum.split()[0].decode("utf-8")
        if not exists(checksum_file):
            open(checksum_file, 'w').write(checksum)
            info('checksum created %s' %checksum)
            return True
        else:
            info("checksum_file = '%s'" %checksum_file)
            state = open(checksum_file, 'r').read()
            info('state = %s' %state)
            if checksum == state:
                info('checksum == state')
                return False
            else:
                open(checksum_file, 'w').write(checksum)
                info('checksum updated')
                return True

def chmod_recursive(path, dir_perms, file_perms):
    info("changings perms to %o;%o on path = '%s'" %(dir_perms, file_perms, path))
    for root, dirs, files in walk(path):  
        for d in dirs:  
            chmod(join(root, d), dir_perms)
        for f in files:
            chmod(join(root, f), file_perms)

##################################
                
def export_zim(zim_path):
    info('zim --export --output=%szwiki --format=html '
        '--template=~/.local/share/zim/templates/html/codex-default.html %szim '
        '--index-page index ' %(zim_path, zim_path))
    results = (Popen('zim --export --output=%szwiki --format=html '
        '--template=~/.local/share/zim/templates/html/codex-default.html %szim '
        '--index-page index ' %(zim_path, zim_path), 
        stdout=PIPE, shell=True).communicate()[0].decode('utf8'))
    chmod_recursive('%szwiki' %zim_path, 0o755, 0o744)
    if results: print(results)

def grab_todos(filename):

    info("grab_todos")   
    html_parser = etree.HTMLParser(remove_comments = True, remove_blank_text = True)
    doc = etree.parse(open(filename, 'rb'), html_parser)
    div = doc.xpath('//div[@id="zim-content-body"]')[0]
    div.set('id', 'Ongoing-todos')
    div_txt = etree.tostring(div).decode("utf-8")
    div_txt = div_txt.replace('href="./', 'href="../zwiki/')
    new_div = html.fragment_fromstring(div_txt)
    return new_div

def insert_todos(plan_fn, todos):
    
    info("insert_todos")
    html_parser = etree.HTMLParser(remove_comments = True, remove_blank_text = True)
    doc = etree.parse(open(plan_fn, 'rb'), html_parser)
    div = doc.xpath('//div[@id="Ongoing-todos"]')[0]
    parent = div.getparent()
    parent.replace(div, todos)
    doc.write(plan_fn)

def update_markdown(filename, md_fn):
    '''Convert markdown file'''
    
    dbg('updating_md %s' %filename)
    content = open(md_fn,"r").read()
    md_cmd = [HOME+'/bin/pandoc-wrappers/md']
    md_args = []
    tmp_body_fn = None # temporary store body of MM HTML

    if 'talks' in md_fn:
        md_args.extend(['--presentation'])
        COURSES = ['/mcs/', '/orgcom/']
        if any(course in md_fn for course in COURSES):
            md_args.extend(['--partial-handout'])
        if '[@' in content:
            md_args.extend(['--bibliography'])
    elif 'cc/' in md_fn:
        md_args.extend(['--quash'])
        md_args.extend(['--number-elements'])
        md_args.extend(['--style-csl', 'chicago-fullnote-bibliography'])
    elif 'syllabus' in md_fn:
        info("processing syllabus")
        mm_fn_html = md_fn.replace('syllabus', 'readings'
            ).replace('.md', '.html')
        info("mm_fn_html = '%s'" %(mm_fn_html))
        if exists(mm_fn_html):
            info("transcluding HTML from mindmap")
            html_parser = etree.HTMLParser()
            doc = etree.parse(open(mm_fn_html, 'rb'), html_parser)
            body_node = doc.xpath('//body')[0]
            body_content = etree.tostring(body_node
                )[6:-7].decode("utf-8")
            tmp_body_fn = filename + '.tmp'
            codecs.open(tmp_body_fn, 'w', 'utf-8', 'replace'
                ).write(body_content)
            md_args.extend(['--include-after-body', tmp_body_fn])
    else:
        md_args.extend(['-c', 
            'http://reagle.org/joseph/2003/papers.css'])
        # check for a multimarkdown metadata line with extra build options
        match_md_opts = re.search('^md_opts: (.*)', content, re.MULTILINE)
        if match_md_opts:
            md_opts = match_md_opts.group(1).split(' ')
            info("md_opts = %s" % md_opts)
            md_args.extend(md_opts)
        elif '[@' in content: # if it has refs still use CSL
            md_args.extend(['-s'])
    md_cmd.extend(md_args)
    md_cmd.extend([md_fn])
    info("md_cmd = %s" % ' '.join(md_cmd))
    call(md_cmd)
    if tmp_body_fn: remove(tmp_body_fn)
    if args.launch:
        #webbrowser.open(html_fn)
        call(["google-chrome", html_fn])

def check_markdown_files(HOMEDIR):
    '''Convert any markdown file whose HTML file is older than it.'''

    files = locate('*.md', HOMEDIR)
    for md_fn in files:
        filename = md_fn.rsplit('.',1)[0]
        html_fn = filename + '.html'
        dbg("html_fn = %s" % html_fn)
        if exists(html_fn):
            if getmtime(md_fn) > getmtime(html_fn):
                info("%s %s > %s %s" %(md_fn, getmtime(md_fn), 
                                       html_fn, getmtime(html_fn)))
                update_markdown(filename, md_fn)
    
def check_mm_files(HOMEDIR):
    '''Convert any Freemind mindmap whose HTML file is older than it.
    NOTE: If the syllabus.md hasn't been updated it won't reflect the changes'''
    
    INCLUDE_PATHS = ['syllabus', 'readings', 'concepts']

    files = locate('*.mm', HOMEDIR)
    for mm_filename in files:
        if any([included in mm_filename for included in INCLUDE_PATHS]):
            filename = mm_filename.rsplit('.',1)[0]
            html_fn = filename + '.html'
            if exists(html_fn):
                if getmtime(mm_filename) > getmtime(html_fn):
                    info('updating_mm %s' %filename)
                    call(['xsltproc', '-o', html_fn, 
                        '/home/reagle/bin/mmtoxhtml.xsl', mm_filename])
                    call(['tidy', '-asxhtml', '-utf8', 
                          '-w', '0', '-m', html_fn])
                    p3 = Popen(['tail', '-n', '+2', html_fn], 
                        stdout=PIPE)
                    p4 = Popen(['tidy', '-asxhtml', '-utf8', '-w', '0', 
                                '-o', html_fn],
                         stdin=p3.stdout)
                    # if exists, update the syllabus.md that uses the MM's HTML
                    if 'readings' in mm_filename:
                        md_syllabus_fn = filename.replace('readings', 
                            'syllabus') + '.md'
                        if exists(md_syllabus_fn):
                            update_markdown(filename, md_syllabus_fn)

def check_mm_tmp_html_files():
    '''Freemind exports HTML to '/tmp/tmm543...72.html; find them and 
    associate style sheet.'''

    files = locate('tmm*.html', '/tmp/')
    for html_fn in files:
        html_fd = open(html_fn,"r")
        content = html_fd.read()
        content = content.replace('</title>', '''
            </title>\n\t\t<link href="/home/reagle/joseph/2005/01/mm-print.css"
            rel="stylesheet" type="text/css" />''')
        html_fd = open(html_fn,"w")
        html_fd.write(content)
         
def log2work(done_tasks):
    '''
    Log completed zim tasks to work microblog
    '''

    log_items = []
    for activity, task in done_tasks:
        # zim syntax for href/em to HTML
        task = re.sub('\[\[(.*?)\|(.*)\]\]', r'<a href="\1">\2</a>', task)
        task = re.sub('\/\/(.*?)\/\/', r'<em>\1</em>', task)

        date_token = get_Now_YMD()
        digest = hashlib.md5(task.encode('utf-8', 'replace')).hexdigest()
        uid = "e" + date_token + "-" + digest[:4]
        log_item = '<li class="event" id="%s">%s: %s] %s</li>\n' % \
            (uid, date_token, activity, task)
        log_items.append(log_item)

    OUT_FILE = HOME+'/data/2web/reagle.org/joseph/plan/plans/index.html'
    fd = codecs.open(OUT_FILE, 'r', 'utf-8', 'replace')
    content = fd.read()
    fd.close()

    insertion_regexp = re.compile('(<h2>Done Work</h2>\s*<ol>)')

    newcontent = insertion_regexp.sub('\\1 \n  %s' %
        ''.join(log_items), content, re.DOTALL|re.IGNORECASE)
    if newcontent:
        fd = codecs.open(OUT_FILE, 'w', 'utf-8', 'replace')
        fd.write(newcontent)
        fd.close()
    else:
        print("Sorry, output regexp subsitution failed.")
                         
                         
def retire_tasks(directory):
    '''
    Removes completed '[x]' zim tasks form zim
    '''
    if 'zim' in check_output(["ps", "axw"]).decode("utf-8"):
        print("Zim is presently running; skipping task " +
            "retirement and export.")
        return False
    else:
        zim_files = locate('*.txt', directory)
        for zim_filename in zim_files:
            info(zim_filename)
            done_tasks =[]
            activity = 'misc'
            new_wiki_page = []
            with open(zim_filename, 'r') as wiki_page:
                for line in wiki_page:
                    label = re.search('@\w+', line)
                    if label:
                        activity = label.group(0).strip()[1:]
                    if '[x]' in line:
                        item = line.split(']',1)[1].strip()
                        info("found item %s" %item)
                        done_tasks.append((activity, item))
                    else:
                        new_wiki_page.append(line)
            if done_tasks:
                new_wiki_page_fd = open(zim_filename, 'w')
                new_wiki_page_fd.writelines("%s" % line for line in new_wiki_page)
                new_wiki_page_fd.close()
                log2work(done_tasks)
        return True
                         
if '__main__' == __name__:
    import argparse # http://docs.python.org/dev/library/argparse.html
    arg_parser = argparse.ArgumentParser(description="Build static HTML versions of various files")
    arg_parser.add_argument("-l", "--launch",
                    action="store_true", default=False,
                    help="Open all check_markdown_files results in browser")
    arg_parser.add_argument("-f", "--force-update",
                    action="store_true", default=False,
                    help="Force retire/update of Zim despite md5sums")
    arg_parser.add_argument("-n", "--notes-handout",
                    action="store_true", default=False,
                    help="Force creation of notes handout even if not class slide")
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

    ## Private files
    
    # Zim: Joseph and Nora planning
    HOMEDIR = '/home/reagle/joseph/plan/joseph-nora/'
    if has_dir_changed(HOMEDIR + 'zim/') or args.force_update:
        export_zim(HOMEDIR)

    # Zim: Work planning
    HOMEDIR = '/home/reagle/joseph/plan/'
    if has_dir_changed(HOMEDIR + 'zim/') or args.force_update:
        if retire_tasks(HOMEDIR + 'zim/'):
            export_zim(HOMEDIR)
        
        HOME_FN = HOMEDIR + 'zwiki/Home.html'
        todos = grab_todos(HOME_FN)
        
        PLAN_PAGE = HOMEDIR + 'plans/index.html'
        insert_todos(PLAN_PAGE, todos)

    ## Public files

    # Zim: Public
    HOMEDIR = '/home/reagle/joseph/'
    if has_dir_changed(HOMEDIR + 'zim/') or args.force_update:
        export_zim(HOMEDIR)
    
    # Mindmaps: syllabi (1st as transcluded in markdown files)
    check_mm_files(HOMEDIR)

    # Mindmaps HTML exports
    check_mm_tmp_html_files()

    # Markdown (2nd)
    check_markdown_files(HOMEDIR)
