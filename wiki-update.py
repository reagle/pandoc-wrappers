#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the static portions of my website by looking for source files newer
    than existing HTML files.
*.mm (Freeplane)-> html
*.md (pandoc)-> html
zim/* (zim-wiki) -> html

"""

import codecs
from concurrent import futures
import fnmatch
import hashlib
from lxml import etree, html
import logging
from os import chdir, chmod, environ, mkdir, path, rename, remove, walk
from os.path import (
    abspath,
    basename,
    dirname,
    exists,
    expanduser,
    getmtime,
    join,
    relpath,
    splitext,
)
import re
from shutil import copy, rmtree, move
from subprocess import call, check_output, Popen, PIPE
import shutil
import sys
import time

HOME = expanduser("~") if exists(expanduser("~")) else None
BROWSER = environ["BROWSER"] if "BROWSER" in environ else None
PANDOC_BIN = shutil.which("pandoc")
MD_BIN = HOME + "/bin/pw/markdown-wrapper.py"
# ZIM_BIN = '/usr/local/bin/zim'
ZIM_BIN = (
    "/usr/local/opt/python@3.8/bin//python3 "
    + HOME
    + "/bin/zim-desktop-wiki/zim.py"
)

if not all([HOME, BROWSER, PANDOC_BIN, MD_BIN, ZIM_BIN]):
    raise FileNotFoundError("Your environment is not configured correctly")

log_level = 100  # default
critical = logging.critical
info = logging.info
dbg = logging.debug
warn = logging.warn
error = logging.error
excpt = logging.exception


#################################
# Utility functions
#################################


def get_Now_YMD():
    """
    Now in YearMonthDay format
    """

    now = time.localtime()

    date_token = time.strftime("%y%m%d", now)
    return date_token


def locate(pattern, root):
    """Locate all files matching supplied filename pattern in and below
    supplied root directory."""
    # TODO: move RE instead of fnmatch?
    for path, dirs, files in walk(abspath(root)):
        for fn in fnmatch.filter(files, pattern):
            yield join(path, fn)


def has_dir_changed(directory):

    info("dir   = %s" % directory)
    checksum_file = directory + ".dirs.md5sum"
    checksum = Popen(
        ["ls -l -R %s | md5sum" % directory], shell=True, stdout=PIPE
    ).communicate()[0]
    checksum = checksum.split()[0].decode("utf-8")
    if not exists(checksum_file):
        open(checksum_file, "w").write(checksum)
        info("checksum created %s" % checksum)
        return True
    else:
        info("checksum_file = '%s'" % checksum_file)
        state = open(checksum_file, "r").read()
        info("state = %s" % state)
        if checksum == state:
            info("checksum == state")
            return False
        else:
            open(checksum_file, "w").write(checksum)
            info("checksum updated")
            return True


def chmod_recursive(path, dir_perms, file_perms):
    info(
        "changings perms to %o;%o on path = '%s'"
        % (dir_perms, file_perms, path)
    )
    for root, dirs, files in walk(path):
        for d in dirs:
            chmod(join(root, d), dir_perms)
        for f in files:
            chmod(join(root, f), file_perms)


##################################


def export_zim(zim_path):

    ZIM_CMD = (
        "%s --export --recursive --overwrite --output=%szwiki "
        "--format=html "
        "--template=~/.local/share/zim/templates/html/codex-default.html %szim "
        "--format=html --index-page index " % (ZIM_BIN, zim_path, zim_path)
    )
    info(ZIM_CMD)
    print(f"exporting {zim_path}")
    results = Popen((ZIM_CMD), stdout=PIPE, stderr=PIPE, shell=True, text=True)
    chmod_recursive("%szwiki" % zim_path, 0o755, 0o744)
    results_out, results_sdterr = results.communicate()
    if results_sdterr:
        print(f"results_out = {results_out}")
        print(f"results_sdterr = {results_sdterr}")


def grab_todos(filename):

    info("grab_todos")
    html_parser = etree.HTMLParser(
        remove_comments=True, remove_blank_text=True
    )
    doc = etree.parse(open(filename, "rb"), html_parser)
    div = doc.xpath('//div[@id="zim-content-body"]')[0]
    div.set("id", "Ongoing-todos")
    div_txt = etree.tostring(div).decode("utf-8")
    div_txt = div_txt.replace('href="./', 'href="../zwiki/')
    div_txt = div_txt.replace(
        'href="file:///Users/reagle/joseph/', 'href="../../'
    )
    new_div = html.fragment_fromstring(div_txt)
    return new_div


def insert_todos(plan_fn, todos):

    info("insert_todos")
    html_parser = etree.HTMLParser(
        remove_comments=True, remove_blank_text=True
    )
    doc = etree.parse(open(plan_fn, "rb"), html_parser)
    div = doc.xpath('//div[@id="Ongoing-todos"]')[0]
    parent = div.getparent()
    parent.replace(div, todos)
    doc.write(plan_fn)


def update_markdown(files_to_process):
    """Convert markdown file"""

    fn_bare, fn_md = files_to_process
    dbg("updating fn_md %s" % fn_md)
    content = open(fn_md, "r").read()
    md_cmd = [MD_BIN]
    md_args = []  # '-VV'
    tmp_body_fn = None  # temporary store body of MM HTML

    if "talks" in fn_md:
        md_args.extend(["--presentation"])
        COURSES = ["/oc/", "/cda/"]
        if any(course in fn_md for course in COURSES):
            md_args.extend(["--partial-handout"])
        if "[@" in content:
            md_args.extend(["--bibliography"])
    elif "cc/" in fn_md:
        md_args.extend(["--quash"])
        # md_args.extend(['--keep-tmp'])
        md_args.extend(["--number-elements"])
        # md_args.extend(['--punctuation-inside'])  # removed from md.py
        # md_args.extend(['--style-csl', 'turabian-reagle.csl'])
        md_args.extend(["--style-csl", "chicago-fullnote-nobib.csl"])
        # md_args.extend(['--odt'])
    else:
        md_args.extend(["-c", "https://reagle.org/joseph/2003/papers.css"])
    # check for a multimarkdown metadata line with extra build options
    match_md_opts = re.search("^md_opts_: (.*)", content, re.MULTILINE)
    # md_args.extend(['--keep-tmp']) # for debugging
    if match_md_opts:
        md_opts = match_md_opts.group(1).strip().split(" ")
        info("md_opts = %s" % md_opts)
        md_args.extend(md_opts)
    md_cmd.extend(md_args)
    md_cmd.extend([fn_md])
    md_cmd = list(filter(None, md_cmd))  # remove any empty strings
    info("md_cmd = '%s'" % md_cmd)
    info("md_cmd = %s" % " ".join(md_cmd))
    call(md_cmd)
    if tmp_body_fn:
        remove(tmp_body_fn)


def check_markdown_files(HOMEDIR):
    """Convert any markdown file whose HTML file is older than it."""
    # TODO: convert this to generic output, to work with html, docx, or odt!!
    # 2020-03-11: attempted but difficult, need to:
    #     - ignore when a docx was converted to html (impossible?)
    #     - don't create outputs if they don't already exist
    #     - don't update where docx is newer than md, but older than html?

    files_bare = [splitext(fn_md)[0] for fn_md in locate("*.md", HOMEDIR)]
    files_to_process = []
    for fn_bare in files_bare:
        fn_md = fn_bare + ".md"
        fn_html = fn_bare + ".html"
        if exists(fn_html):
            if getmtime(fn_md) > getmtime(fn_html):
                info(
                    f"{fn_md} {getmtime(fn_md)} > {fn_html} {getmtime(fn_html)}"
                )
                files_to_process.append((fn_bare, fn_md))
        # Even this simple hack doesn't work, as it finds lots of files
        # I'm not otherwise touching: I'd have to find files where the docx
        # file is more recent than the md AND html file
        # fn_docx = fn_bare + ".docx"
        # if exists(fn_docx):
        #     if getmtime(fn_md) > getmtime(fn_docx):
        #         info(
        #             f"{fn_md} {getmtime(fn_md)} > {fn_docx} {getmtime(fn_docx)}"
        #         )
        #         files_to_process.append((fn_bare, fn_md))
    if args.sequential or len(files_to_process) < 3:
        # in python 3, map is lazy and won't do anything until iterated
        list(map(update_markdown, files_to_process))
    else:
        with futures.ProcessPoolExecutor() as executor:
            results = executor.map(update_markdown, files_to_process)


def check_mm_files(HOMEDIR):
    """Convert any Freeplane mindmap whose HTML file is older than it.
    NOTE: If the syllabus.md hasn't been updated it won't reflect
    the changes"""
    # TODO: test, and if not using, remove 20200311

    INCLUDE_PATHS = {"syllabus", "readings", "concepts"}

    files = locate("*.mm", HOMEDIR)
    for mm_fn in files:
        if any([included in mm_fn for included in INCLUDE_PATHS]):
            fn = splitext(mm_fn)[0]
            fn_html = fn + ".html"
            if exists(fn_html):
                if getmtime(mm_fn) > getmtime(fn_html):
                    info("updating_mm %s" % fn)
                    call(
                        [
                            "xsltproc",
                            "-o",
                            fn_html,
                            HOME + "/bin/mmtoxhtml.xsl",
                            mm_fn,
                        ]
                    )
                    call(
                        ["tidy", "-asxhtml", "-utf8", "-w", "0", "-m", fn_html]
                    )
                    p3 = Popen(["tail", "-n", "+2", fn_html], stdout=PIPE)
                    p4 = Popen(
                        [
                            "tidy",
                            "-asxhtml",
                            "-utf8",
                            "-w",
                            "0",
                            "-o",
                            fn_html,
                        ],
                        stdin=p3.stdout,
                    )
                    # if exists, update the syllabus.md that uses the MM's HTML
                    if "readings" in mm_fn:
                        md_syllabus_fn = (
                            fn.replace("readings", "syllabus") + ".md"
                        )
                        if exists(md_syllabus_fn):
                            update_markdown(fn, md_syllabus_fn)


def check_mm_tmp_html_files():
    """Freeplane exports HTML to '/tmp/tmm543...72.html; find them and
    associate style sheet."""

    files = locate("tmm*.html", "/tmp/")
    for fn_html in files:
        html_fd = open(fn_html, "r")
        content = html_fd.read()
        content = content.replace(
            "</title>",
            """
            </title>\n\t\t<link href="/home/reagle/joseph/2005/01/mm-print.css"
            rel="stylesheet" type="text/css" />""",
        )
        html_fd = open(fn_html, "w")
        html_fd.write(content)


def log2work(done_tasks):
    """
    Log completed zim tasks to work microblog
    """

    log_items = []
    for activity, task in done_tasks:
        # zim syntax for href/em to HTML
        task = re.sub(r"\[\[(.*?)\|(.*)\]\]", r'<a href="\1">\2</a>', task)
        task = re.sub(r"\/\/(.*?)\/\/", r"<em>\1</em>", task)

        date_token = get_Now_YMD()
        digest = hashlib.md5(task.encode("utf-8", "replace")).hexdigest()
        uid = "e" + date_token + "-" + digest[:4]
        log_item = '<li class="event" id="%s">%s: %s] %s</li>\n' % (
            uid,
            date_token,
            activity,
            task,
        )
        log_items.append(log_item)

    OUT_FILE = HOME + "/data/2web/reagle.org/joseph/plan/plans/index.html"
    plan_fd = codecs.open(OUT_FILE, "r", "utf-8", "replace")
    plan_content = plan_fd.read()
    plan_fd.close()

    # TODO: finish transition to xml - jr 20170222
    #     I should also escape_XML plan_content
    # plan_tree = etree.fromstring(plan_content)
    # ul_found = plan_tree.xpath('''//div[@id='Done']/ul''')
    # if ul_found:
    #     ul_found[0].insert(0, etree.XML(''.join(log_items)))
    #     new_content = str(etree.tostring(plan_tree, pretty_print=True))

    insertion_regexp = re.compile(r"(<h2>Done Work</h2>\s*<ul>)")

    new_content = insertion_regexp.sub(
        "\\1 \n  %s" % "".join(log_items),
        plan_content,
        re.DOTALL | re.IGNORECASE,
    )
    if new_content:
        fd = codecs.open(OUT_FILE, "w", "utf-8", "replace")
        fd.write(new_content)
        fd.close()
    else:
        print("Sorry, XML insertion failed.")


def retire_tasks(directory):
    """
    Removes completed '[x]' zim tasks form zim
    """
    if "zim" in check_output(["ps", "axw"]).decode("utf-8"):
        print("Zim is presently running; skipping task retirement and export.")
        return False
    else:
        zim_files = locate("*.txt", directory)
        for zim_fn in zim_files:
            # info(zim_fn)
            done_tasks = []
            activity = "misc"
            new_wiki_page = []
            with open(zim_fn, "r") as wiki_page:
                for line in wiki_page:
                    label = re.search(r"@\w+", line)
                    # TODO: support multiple labels and remove from activity
                    if label:
                        activity = "#" + label.group(0).strip()[1:]
                    if "[x]" in line:
                        # following checkbox
                        item = line.split("]", 1)[1].strip()
                        info("found item %s" % item)
                        info("activity = %s" % activity)
                        done_tasks.append((activity, item))
                    else:
                        new_wiki_page.append(line)
            if done_tasks:
                new_wiki_page_fd = open(zim_fn, "w")
                new_wiki_page_fd.writelines(
                    "%s" % line for line in new_wiki_page
                )
                new_wiki_page_fd.close()
                log2work(done_tasks)
        return True


if "__main__" == __name__:
    import argparse  # http://docs.python.org/dev/library/argparse.html

    arg_parser = argparse.ArgumentParser(
        description="Build static HTML versions of various files"
    )
    arg_parser.add_argument(
        "-f",
        "--force-update",
        action="store_true",
        default=False,
        help="Force retire/update of Zim despite md5sums",
    )
    arg_parser.add_argument(
        "-n",
        "--notes-handout",
        action="store_true",
        default=False,
        help="Force creation of notes handout even if not class slide",
    )
    arg_parser.add_argument(
        "-s",
        "--sequential",
        action="store_true",
        default=False,
        help="Forces sequential invocation of pandoc, rather than default"
        " behavior which is often parallel",
    )
    arg_parser.add_argument(
        "-L",
        "--log-to-file",
        action="store_true",
        default=False,
        help="log to file PROGRAM.log",
    )
    arg_parser.add_argument(
        "-V",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (specify multiple times for more)",
    )
    arg_parser.add_argument("--version", action="version", version="TBD")
    args = arg_parser.parse_args()

    if args.verbose == 1:
        log_level = logging.CRITICAL
    elif args.verbose == 2:
        log_level = logging.INFO
    elif args.verbose >= 3:
        log_level = logging.DEBUG
    LOG_FORMAT = "%(levelno)s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(
            filename="wiki-update.log",
            filemode="w",
            level=log_level,
            format=LOG_FORMAT,
        )
    else:
        logging.basicConfig(level=log_level, format=LOG_FORMAT)

    # # Private files

    # Zim: Joseph and Nora planning
    HOMEDIR = HOME + "/joseph/plan/joseph-nora/"
    if has_dir_changed(HOMEDIR + "zim/") or args.force_update:
        export_zim(HOMEDIR)

    # Zim: Work planning
    HOMEDIR = HOME + "/joseph/plan/"
    if has_dir_changed(HOMEDIR + "zim/") or args.force_update:
        if retire_tasks(HOMEDIR + "zim/"):
            export_zim(HOMEDIR)

        HOME_FN = HOMEDIR + "zwiki/Home.html"
        todos = grab_todos(HOME_FN)

        PLAN_PAGE = HOMEDIR + "plans/index.html"
        insert_todos(PLAN_PAGE, todos)

    # # Public files
    HOMEDIR = HOME + "/joseph/"

    # Zim: Public
    if has_dir_changed(HOMEDIR + "zim/") or args.force_update:
        export_zim(HOMEDIR)

    # Mindmaps: syllabi (1st as transcluded in markdown files)
    check_mm_files(HOMEDIR)

    # Mindmaps HTML exports
    check_mm_tmp_html_files()

    # Markdown (public files)
    check_markdown_files(HOMEDIR)

    # # Private files
    HOMEDIR = HOME + "/data/1work/"
    check_markdown_files(HOMEDIR)
