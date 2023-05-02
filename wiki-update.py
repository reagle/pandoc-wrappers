#! /usr/bin/env python3
"""
Build the static portions of my website by looking for source 
    files newer than existing HTML files.

ob-/* (obsidian) -> html
zim/* (zim-wiki) -> html
*.mm (Freeplane)-> html
*.md (pandoc)-> html
"""

import logging
import os
import re
import shutil
from os import chmod, environ, walk
from os.path import (
    exists,
    expanduser,
    getmtime,
    join,
    splitext,
)
from pathlib import Path
from subprocess import PIPE, Popen, call

HOME = expanduser("~")
BROWSER = environ["BROWSER"]
PANDOC_BIN = shutil.which("pandoc")
MD_BIN = HOME + "/bin/pw/markdown-wrapper.py"
OBS_EXPORT_BIN = HOME + "/bin/obsidian-export"
TEMPLATES_FOLDER = HOME + "/.pandoc/templates"

if not all([HOME, BROWSER, PANDOC_BIN, MD_BIN, OBS_EXPORT_BIN, TEMPLATES_FOLDER]):
    raise FileNotFoundError("Your environment is not configured correctly")

log_level = logging.ERROR  # 40

# function aliases
critical = logging.critical
error = logging.error
warning = logging.warning
info = logging.info
debug = logging.debug

#################################
# Obsidian export to markdown and run `markdown-wrapper.py`
# on recent files
#################################


def export_obsidian(vault_dir: str, export_dir: str) -> None:
    """call obsidian-export on source; copy source's mtimes to target"""
    export_cmd = f"{OBS_EXPORT_BIN} {vault_dir} {export_dir}"
    debug(f"{export_cmd=}")
    print(f"exporting {vault_dir}")
    results = Popen((export_cmd), stdout=PIPE, stderr=PIPE, shell=True, text=True)
    results_out, results_sdterr = results.communicate()
    if results_sdterr:
        print(f"results_out = {results_out}\nresults_sdterr = {results_sdterr}")
    create_missing_html_files(export_dir)
    copy_mtime(vault_dir, export_dir)


def invoke_md_wrapper(files_to_process: list[str]) -> None:
    """
    Configure arguments for `markdown-wrapper.py and invoke to convert
    markdown file to HTML
    """

    for fn_md in files_to_process:
        info(f"updating fn_md {fn_md}")
        path_md = Path(fn_md)
        content = path_md.read_text()
        md_cmd = [MD_BIN]
        md_args = []
        # TODO: instead of this pass-through hack, use MD_BIN as a library
        if args.verbose > 0:
            md_args.extend([f"-{args.verbose * 'V'}"])
        tmp_body_fn = None  # temporary store body of MM HTML

        if "talks" in str(path_md):
            md_args.extend(["--presentation"])
            COURSES = ["/oc/", "/cda/"]
            if any(course in str(path_md) for course in COURSES):
                md_args.extend(["--partial-handout"])
            if "[@" in content:
                md_args.extend(["--bibliography"])
        elif "cc/" in str(path_md):
            md_args.extend(["--quash"])
            md_args.extend(["--number-elements"])
            md_args.extend(["--style-csl", "chicago-fullnote-nobib.csl"])
        elif "ob-" in str(path_md):
            md_args.extend(["--metadata", f"title={path_md.stem}"])
            md_args.extend(["--lua-filter", "obsidian-export.lua"])
            md_args.extend(
                [
                    "--include-after-body",
                    f"{TEMPLATES_FOLDER}/obsidian-footer.html",
                ]
            )
        else:
            md_args.extend(["-c", "https://reagle.org/joseph/2003/papers.css"])
        # check for a multimarkdown metadata line with extra build options
        match_md_opts = re.search("^md_opts_: (.*)", content, re.MULTILINE)
        if match_md_opts:
            md_opts = match_md_opts.group(1).strip().split(" ")
            debug(f"md_opts = {md_opts}")
            md_args.extend(md_opts)
        md_cmd.extend(md_args)
        md_cmd.extend([str(path_md)])
        md_cmd = list(filter(None, md_cmd))  # remove any empty strings
        call(md_cmd)
        if tmp_body_fn:
            Path(tmp_body_fn).unlink()


def find_convert_md(source_dir: str) -> None:
    """Find and convert any markdown file whose HTML file is older than it."""
    # TODO: have this work when output format is docx or odt.
    # 2020-03-11: attempted but difficult, need to:
    #     - ignore when a docx was converted to html (impossible?)
    #     - don't create outputs if they don't already exist
    #     - don't update where docx is newer than md, but older than html?
    # 2020-09-17: possible hack: always generate HTML in addition to docx

    source_path = Path(source_dir)
    files_to_process = []

    for fn_md in source_path.glob("**/*.md"):
        fn_html = fn_md.with_suffix(".html")
        if fn_html.exists():
            if fn_md.stat().st_mtime > fn_html.stat().st_mtime:
                debug(
                    f"""{fn_md} {fn_md.stat().st_mtime} """
                    + f"""> {fn_html} {fn_html.stat().st_mtime}"""
                )
                files_to_process.append(fn_md)

    info(f"{files_to_process=}")
    invoke_md_wrapper(files_to_process)


def create_missing_html_files(folder: str) -> None:
    """
    Walk a folder looking for markdown files. For each markdown file without a
    corresponding HTML file, create one, and set its mtime back so
    `find_convert_md_files` knows to process it.

    """
    folder_path = Path(folder)

    for md_file in folder_path.glob("**/*.md"):
        html_file = md_file.with_suffix(".html")

        if not html_file.exists():
            html_file.touch()
            os.utime(html_file, (0, 0))


#################################
# Utilities
#################################


def chmod_recursive(path, dir_perms, file_perms):
    """Fix permissions on a generated/exported tree if needed."""
    debug(f"changing perms to {dir_perms};{file_perms} on {path=}")
    for root, dirs, files in walk(path):
        for d in dirs:
            chmod(join(root, d), dir_perms)
        for f in files:
            chmod(join(root, f), file_perms)


def copy_mtime(source_dir: str, target_dir: str) -> None:
    """
    Copy mtime from source_dir to target_dir so that `find_convert_md_files`
    know what changed.
    """
    src_path = Path(source_dir)
    dst_path = Path(target_dir)

    if not src_path.is_dir() or not dst_path.is_dir():
        raise ValueError("Both arguments should be valid directory paths.")

    for src_fn in src_path.glob("**/*"):
        if src_fn.is_file():
            # Create a corresponding target file path
            relative_path = src_fn.relative_to(src_path)
            dst_fn = dst_path.joinpath(relative_path)

            if dst_fn.exists() and dst_fn.is_file():
                # find_convert_md_f time of the source file
                src_mtime = src_fn.stat().st_mtime

                # Apply the modified time to the destination file
                os.utime(dst_fn, (dst_fn.stat().st_atime, src_mtime))


##################################


if __name__ == "__main__":
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
        help=(
            "Forces sequential invocation of pandoc, rather than default"
            " behavior which is often parallel"
        ),
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
    arg_parser.add_argument("--version", action="version", version="1.0")
    args = arg_parser.parse_args()

    log_level = logging.ERROR  # 40
    if args.verbose == 1:
        log_level = logging.WARNING  # 30
    elif args.verbose == 2:
        log_level = logging.INFO  # 20
    elif args.verbose >= 3:
        log_level = logging.DEBUG  # 10
    LOG_FORMAT = "%(module).5s %(levelname).3s %(funcName).5s: %(message)s"
    if args.log_to_file:
        logging.basicConfig(
            filename="wiki-update.log",
            filemode="w",
            level=log_level,
            format=LOG_FORMAT,
        )
    else:
        logging.basicConfig(level=log_level, format=LOG_FORMAT)

    ## Obsidian vault ##

    # Private planning vault
    source_dir = HOME + "/joseph/plan/ob-plan/"
    target_dir = HOME + "/joseph/plan/ob-web"
    export_obsidian(source_dir, target_dir)

    # Public codex vault
    source_dir = HOME + "/joseph/ob-codex/"
    target_dir = HOME + "/joseph/ob-web/"
    export_obsidian(source_dir, target_dir)

    ## Markdown files via pandoc ##

    # Public markdown files
    source_dir = HOME + "/joseph/"
    find_convert_md(source_dir)

    # Private markdown files
    HOMEDIR = HOME + "/data/1work/"
    find_convert_md(HOMEDIR)
