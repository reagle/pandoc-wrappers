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

from bs4 import BeautifulSoup  # type: ignore

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
# Export Obsidian markdown to standard markdown.
#################################


def export_obsidian(vault_dir: Path, export_dir: Path) -> None:
    """Call obsidian-export on source; copy source's mtimes to target."""

    export_cmd = f"{OBS_EXPORT_BIN} {vault_dir} {export_dir}"
    debug(f"{export_cmd=}")

    print(f"exporting {vault_dir}")
    results = Popen((export_cmd), stdout=PIPE, stderr=PIPE, shell=True, text=True)
    results_out, results_sdterr = results.communicate()
    if results_sdterr:
        debug(f"results_out = {results_out}\nresults_sdterr = {results_sdterr}")
    copy_mtime(vault_dir, export_dir)

    remove_empty_or_hidden_folders(export_dir)
    review_created_or_deleted_files(vault_dir, export_dir)
    if has_dir_changed(export_dir):
        warning(f"{dir=} has changed")
        create_index(vault_dir, export_dir)


def create_index(vault_path: Path, export_path: Path) -> None:
    """Create a new HTML index for the export vault."""
    # TODO: this seems to have problems when filenames have spaces
    #   2023-05-06: identified

    info(f"creating index for {vault_path}")
    vault_index_file = vault_path / "_index.md"
    export_index_file = export_path / "_index.md"
    with open(vault_index_file, "w") as output_file:
        output_file.write(f"# Index of {vault_path.name}\n")
        for path in vault_path.glob("**/*.md"):
            relative_path = path.relative_to(vault_path)
            link_text = f"[{relative_path.with_suffix('')}]({relative_path})"
            depth = len(relative_path.parts) - 1
            indentation = "  " * depth
            output_file.write(f"{indentation}- {link_text}\n")
    shutil.copy2(vault_index_file, export_index_file)
    info(f"created {output_file=} and {export_index_file=}")
    debug(
        f"""{vault_index_file} {vault_index_file.stat().st_mtime} """
        + f"""> {export_index_file} {export_index_file.stat().st_mtime}"""
    )


#################################
# Convert all new/modified markdown files to HTML via `markdown-wrapper.py`
#################################


def find_convert_md(source_path: Path) -> None:
    """Find and convert any markdown file whose HTML file is older than it."""
    # TODO: have this work when output format is docx or odt.
    #   2020-03-11: attempted but difficult, need to:
    #     - ignore when a docx was converted to html (impossible?)
    #     - don't create outputs if they don't already exist
    #     - don't update where docx is newer than md, but older than html?
    #   2020-09-17: possible hack: always generate HTML in addition to docx

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


def invoke_md_wrapper(files_to_process: list[Path]) -> None:
    """
    Configure arguments for `markdown-wrapper.py and invoke to convert
    markdown file to HTML.
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
        md_cmd.extend([path_md])
        md_cmd = list(filter(None, md_cmd))  # remove any empty strings
        call(md_cmd)
        if tmp_body_fn:
            Path(tmp_body_fn).unlink()


#################################
# XML/HTML utilities
#################################


def remove_chunks(soup, selectors: list[str]) -> None:
    """Remove chunks of HTML give CSS selectors"""
    for selector in selectors:
        chunks = soup.select(selector)
        for chunk in chunks:
            chunk.extract()


def transclude(
    receiving_page: Path,
    receiving_selector: str,
    source_page: Path,
    source_selector: str,
    remove_selectors: list[str],
) -> str:
    """Transclude the source_page into the receiving_page using CSS selectors."""

    content_receiving = Path(receiving_page).read_text().strip()
    content_source = Path(source_page).read_text().strip()
    receiving_soup = BeautifulSoup(content_receiving, "html.parser")
    source_soup = BeautifulSoup(content_source, "html.parser")

    # Remove Obsidian header and footer
    remove_chunks(source_soup, remove_selectors)

    # Get chunk to be transcluded and location of embed
    source_body_contents: list = source_soup.select(source_selector)
    embed_here_div = receiving_soup.select_one(receiving_selector)

    if source_body_contents and embed_here_div:
        embed_here_div.clear()
        for content in source_body_contents:
            embed_here_div.append(content.extract())
    else:
        raise RuntimeError("There was no embeddable content or location found.")

    return str(receiving_soup)


#################################
# Filesystem utilities
#################################


def has_dir_changed(path: Path) -> bool:
    """
    Check if content of folder has changed.
    """
    info(f"{path=}")
    if not path.is_dir():
        raise NotADirectoryError(f"{path} is not a directory")

    checksum_file = path / ".dirs.md5sum"
    checksum = Popen(
        ["ls -R %s | md5sum" % path], shell=True, stdout=PIPE
    ).communicate()[0]
    checksum = checksum.split()[0].decode("utf-8")

    if not checksum_file.exists():
        with checksum_file.open("w") as file:
            file.write(checksum)
        debug(f"checksum created {checksum}")
        return True
    else:
        debug(f"{checksum_file=}")
        state = checksum_file.read_text()
        debug(f"{state=}")
        if checksum == state:
            debug("checksum == state")
            return False
        else:
            with checksum_file.open("w") as file:
                file.write(checksum)
            debug("checksum updated")
            return True


def remove_empty_or_hidden_folders(path: Path, hide_prefix: str = "_") -> bool:
    """Remove empty or hidden folders in path.

    Pandoc chokes on Obsidian template files, so remove."""

    def is_empty(folder: Path) -> bool:
        return not any(folder.iterdir())

    info(f"check for empty or hidden folders {path=}")
    did_remove = False
    folders = sorted(path.rglob("**/"))  # returns all descendant folders
    for folder in folders:
        if is_empty(folder) or folder.name.startswith(hide_prefix):
            shutil.rmtree(folder)
            did_remove = True
            info(f"  Removed folder: {folder}")
    return did_remove


def review_created_or_deleted_files(src_path: Path, dst_path: Path) -> bool:
    """
    Check dst_path and create or delete HTML files based on the
    presence of their corresponding markdown in src_path.
    Created HTML is set with an early mtime so find_convert_md_files()
    knows to process it.
    (Renamed files are simply deleted and created.)
    """

    has_changed = False
    info(f"checking for new markdown files in {dst_path}")
    for md_file in dst_path.glob("**/*.md"):
        html_file = md_file.with_suffix(".html")
        if not html_file.exists():
            html_file.touch()
            os.utime(html_file, (0, 0))
            info(f"created {html_file}")
            has_changed = True

    info(f"checking for deleted markdown files in {src_path}")
    for dst_md_file in dst_path.glob("**/*.md"):
        src_md_file = src_path / dst_md_file.relative_to(dst_path)
        if not src_md_file.exists():
            dst_md_file.unlink()
            dst_md_file.with_suffix(".html").unlink()
            info(f"deleted {dst_md_file}")
            has_changed = True

    return has_changed


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
    debug("copying mtimes")
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


def reset_folder(folder_path):
    """Remove and recreate a folder."""
    info(f"removing/recreating {folder_path=}")
    shutil.rmtree(folder_path)
    folder_path.mkdir(parents=True, exist_ok=True)


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
        help="Force fresh build of Obsidian export.",
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

    if args.force_update:
        reset_folder(HOME / "joseph/ob-web")
        reset_folder(HOME / "joseph/plan/ob-web")

    # Private planning vault
    export_obsidian(HOME / "joseph/plan/ob-plan/", HOME / "joseph/plan/ob-web")

    # Public codex vault
    export_obsidian(HOME / "joseph/ob-codex/", HOME / "joseph/ob-web")

    ## Markdown files ##

    # Private markdown files
    find_convert_md(HOME / "data/1work/")

    # Public markdown files
    find_convert_md(HOME / "joseph/")

    # Transclude Obsidian Home.html into my planning page
    planning_page = HOME / "joseph/plan/index.html"
    modified_html = transclude(
        receiving_page=planning_page,
        receiving_selector="div#embed-here",
        source_page=HOME / "joseph/plan/ob-web/Home.html",
        source_selector="body > *",
        remove_selectors=["div#obsidian-footer", "header"],
    )
    if modified_html:
        with open(planning_page, "w") as f:
            f.write(modified_html)
