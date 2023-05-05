#! /usr/bin/env python3
"""
Build the static portions of my website by looking for source 
    files newer than existing HTML files.

ob-/* (obsidian) -> html
*.md (pandoc)-> html
"""

import logging
import os
import re
import shutil
from os import chmod
from os.path import join
from pathlib import Path
from subprocess import PIPE, Popen, call

from lxml import etree, html

BROWSER = Path(os.environ["BROWSER"])
HOME = Path.home()
MD_BIN = HOME / "bin/pw/markdown-wrapper.py"
OBS_EXPORT_BIN = HOME / "bin/obsidian-export"
PANDOC_BIN = Path(shutil.which("pandoc"))  # type: ignore ; tested below
TEMPLATES_FOLDER = HOME / ".pandoc/templates"

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
# Obsidian export to markdown and convert all new/modified markdown
# files to HTML via `markdown-wrapper.py`
#################################


def export_obsidian(vault_dir: Path, export_dir: Path) -> None:
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


def invoke_md_wrapper(files_to_process: list[Path]) -> None:
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


def find_convert_md(source_path: Path) -> None:
    """Find and convert any markdown file whose HTML file is older than it."""
    # TODO: have this work when output format is docx or odt.
    # 2020-03-11: attempted but difficult, need to:
    #     - ignore when a docx was converted to html (impossible?)
    #     - don't create outputs if they don't already exist
    #     - don't update where docx is newer than md, but older than html?
    # 2020-09-17: possible hack: always generate HTML in addition to docx

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


def create_missing_html_files(folder: Path) -> None:
    """
    Walk a folder looking for markdown files. For each markdown file without a
    corresponding HTML file, create one, and set its mtime back so
    `find_convert_md_files` knows to process it.

    """

    for md_file in folder.glob("**/*.md"):
        html_file = md_file.with_suffix(".html")

        if not html_file.exists():
            html_file.touch()
            os.utime(html_file, (0, 0))


#################################
# Utilities
#################################


def create_index(root_folder: Path) -> None:
    with open(root_folder / "_index.md", "w") as output_file:
        output_file.write(f"# Index of {root_folder.name}\n")
        for path in root_folder.glob("**/*"):
            if "dog" in str(path).lower():
                print(f"{path=}")
            if path.is_file() and path.suffix == ".md":
                relative_path = path.relative_to(root_folder)
                link_text = f"[{relative_path.with_suffix('')}]({relative_path})"
                depth = len(relative_path.parts) - 1
                indentation = "  " * depth
                output_file.write(f"{indentation}- {link_text}\n")


def chmod_recursive(
    path: Path, dir_perms: int = 0o755, file_perms: int = 0o744
) -> None:
    """Fix permissions on a generated/exported tree if needed."""
    debug(f"changing perms to {dir_perms};{file_perms} on {path=}")
    for root, dirs, files in os.walk(path):  # does os.walk accept Path?
        for d in dirs:
            chmod(join(root, d), dir_perms)
        for f in files:
            chmod(join(root, f), file_perms)


def copy_mtime(src_path: Path, dst_path: Path) -> None:
    """
    Copy mtime from source_dir to target_dir so that `find_convert_md_files`
    know what changed.
    """
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


def replace_xpath(
    receiving_page: Path,
    source_page: Path,
    receiving_xpath: str,
    source_xpath: str,
) -> str:
    content_receiving = Path(receiving_page).read_text().strip()
    content_source = Path(source_page).read_text().strip()

    tree_receiving = html.fromstring(content_receiving)
    tree_source = html.fromstring(content_source)

    element_source = tree_source.xpath(source_xpath)
    element_receiving_container = tree_receiving.xpath(receiving_xpath)

    # Remove all outdated children
    receiving_parent = element_receiving_container[0]
    for child in receiving_parent.getchildren():
        receiving_parent.remove(child)
    # Embed the target element from source page into the parent
    receiving_parent.append(element_source[0])

    return etree.tostring(tree_receiving, pretty_print=True, method="html").decode(
        "utf-8"
    )


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
    export_obsidian(HOME / "joseph/plan/ob-plan/", HOME / "joseph/plan/ob-web")
    create_index(HOME / "joseph/plan/ob-plan/")

    # Public codex vault
    export_obsidian(HOME / "joseph/ob-codex/", HOME / "joseph/ob-web")
    create_index(HOME / "joseph/ob-codex/")

    ## Markdown files ##

    # Private markdown files
    find_convert_md(HOME / "data/1work/")

    # Public markdown files
    find_convert_md(HOME / "joseph/")

    # Transclude Obsidian home into my planning page
    planning_page = HOME / "joseph/plan/index.html"
    modified_html = replace_xpath(
        receiving_page=planning_page,
        source_page=HOME / "joseph/plan/ob-web/Home.html",
        receiving_xpath='//*[@id="embed-here"]',
        source_xpath='//header[@id="title-block-header"]/following-sibling::*[1]',
    )
    if modified_html:
        with open(planning_page, "w") as f:
            f.write(modified_html)
