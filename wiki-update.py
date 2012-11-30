#!/usr/bin/python3.2
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
import locale
from lxml import etree, html
import logging
from os import chdir, environ, mkdir, path, rename, remove, walk
from os.path import abspath, basename, dirname, exists, \
    getmtime, join, relpath, splitext
import re
from shutil import copy, rmtree, move
from subprocess import call, check_output, Popen, PIPE
from sh import chmod
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

##################################
                
def export_zim(zim):
    info('zim --export --output=%szwiki --format=html '
        '--template=~/.local/share/zim/templates/html/codex-default.html %szim '
        '--index-page index ' %(zim, zim))
    results = (Popen('zim --export --output=%szwiki --format=html '
        '--template=~/.local/share/zim/templates/html/codex-default.html %szim '
        '--index-page index ' %(zim, zim), 
        stdout=PIPE, shell=True).communicate()[0].decode('utf8'))
    chmod('-R', 'u+rwX,go+rX,go-w', '%szwiki' %zim)
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

def create_talk_handout(HOMEDIR, md_fn):
    '''If talks and handouts exists, create partial handout'''
        
    COURSES = ['/mcs/', '/orgcom/']
    # http://www.farside.org.uk/200804/osjam/markdown2.py
    ast_bullet_re = re.compile(r'^ *(\* )')
    em_re = re.compile(r'(?<!\*)\*([^\*]+?)\*')
    def em_mask(matchobj):
        info("return replace function")
        return '&#95;'*len(matchobj.group(0)) # underscore that pandoc will ignore
        
    md_dir = dirname(md_fn)
    handout_fn = md_fn.replace('/talks/', '/handouts/')
    handout_dir = dirname(handout_fn)
    info("handout_dir) = '%s'" %(dirname(handout_fn)))
    if exists(dirname(handout_fn)):
        skip_to_next_header = False
        partial_handout = False
        handout_f = open(handout_fn, 'w')
        info("partial_handout = '%s'" %(partial_handout))
        content = open(md_fn, 'r').read()
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
            if any(course in md_fn for course in COURSES):
                partial_handout = True
            if partial_handout:
                info("partial_handout = '%s'" %(partial_handout))
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
        call(md_cmd,  shell=True)
        remove(handout_fn)

def update_markdown(HOMEDIR):
    '''Convert any markdown file whose HTML file is older than it.'''

    files = locate('*.md', HOMEDIR)
    for md_fn in files:
        filename = md_fn.rsplit('.',1)[0]
        html_fn = filename + '.html'
        dbg("html_fn = %s" % html_fn)
        if exists(html_fn):
            if getmtime(md_fn) > getmtime(html_fn):
                dbg('updating_md %s' %filename)
                content = open(md_fn,"r").read()
                md_cmd = [HOME+'/bin/pandoc-wrappers/md']
                md_args = []
                if 'talks' in md_fn:
                    # styling now done in pandoc template
                    md_args.extend(['-bp',
                        '-c', 'http://reagle.org/joseph/talks'
                        '/_dzslides/2012/06-class-slides.css'])
                    if '[@' in content:
                        md_args.extend(['-b'])
                    create_talk_handout(HOMEDIR, md_fn)
                else:
                    md_args.extend(['-c', 
                        'http://reagle.org/joseph/2003/papers.css'])
                    if '[@' in content:
                        md_args.extend(['-s'])
                md_cmd.extend(md_args)
                md_cmd.extend([md_fn])
                info("md_cmd = %s" % ' '.join(md_cmd))
                call(md_cmd)
                if args.launch:
                    #webbrowser.open(html_fn)
                    call(["google-chrome", html_fn])
                        
    
def update_mm(HOMEDIR):
    '''Convert any Freemind mindmap whose HTML file is older than it.'''
    
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
                        '/home/reagle/bin/mmtoxhtml.xsl', mm_filename], shell=True)
                    call(['tidy', '-asxhtml', '-utf8', '-w', '0', '-m', html_fn],
                        shell=True)
                    p3 = Popen(['tail', '-n', '+2', html_fn], 
                        stdout=PIPE)
                    p4 = Popen(['tidy', '-asxhtml', '-utf8', '-w', '0', '-o', html_fn],
                         stdin=p3.stdout)

                         
def log2work(done_tasks):
    '''
    Log completed zim tasks to work microblog
    '''
    import hashlib

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
        print_usage("Sorry, output regexp subsitution failed.")
                         
                         
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
                    help="Open all update_markdown results in browser")
    arg_parser.add_argument("-f", "--force-update",
                    action="store_true", default=False,
                    help="Force retire/update of Zim despite md5sums")
    arg_parser.add_argument("-n", "--notes-handout",
                    action="store_true", default=False,
                    help="Force creation of notes handout even if not class slide")
    arg_parser.add_argument('-L', '--log-to-file',
                    action="store_true", default=False,
                    help="log to file PROGRAM.log")
    arg_parser.add_argument('-v', '--verbose', action='count', default=0,
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
    
    # Joseph and Nora planning
    HOMEDIR = '/home/reagle/joseph/plan/joseph-nora/'
    if has_dir_changed(HOMEDIR + 'zim/') or args.force_update:
        export_zim(HOMEDIR)

    # Work planning
    HOMEDIR = '/home/reagle/joseph/plan/'
    if has_dir_changed(HOMEDIR + 'zim/') or args.force_update:
        if retire_tasks(HOMEDIR + 'zim/'):
            export_zim(HOMEDIR)
        
        HOME_FN = HOMEDIR + 'zwiki/Home.html'
        todos = grab_todos(HOME_FN)
        
        PLAN_PAGE = HOMEDIR + 'plans/index.html'
        insert_todos(PLAN_PAGE, todos)

    ## Public files

    # Public zim
    HOMEDIR = '/home/reagle/joseph/'
    if has_dir_changed(HOMEDIR + 'zim/') or args.force_update:
        export_zim(HOMEDIR)
    
    # Syllabi - should go first since they might be used by markdown files
    update_mm(HOMEDIR)

    # Markdown files
    update_markdown(HOMEDIR)
