"""Build static portions of website.

Config-driven site builder that handles three types of sites:
- garden: Obsidian vault → wikilink conversion → markdown-wrapper → HTML
- blog: Obsidian vault → wikilink conversion → Pelican → HTML
- markdown: plain markdown → markdown-wrapper → HTML

Each site is checked for changes (mtime) before building.
"""

__author__ = "Joseph Reagle"
__copyright__ = "Copyright (C) 2009-2026 Joseph Reagle"
__license__ = "GLPv3"
__version__ = "3.0"

import argparse
import logging as log
import os
import re
import shutil
from pathlib import Path
from subprocess import call

from bs4 import BeautifulSoup  # type: ignore

from pandoc_wrappers.obsidian_utils import (
    build_note_index,
    clear_directory,
    copy_vault,
    needs_build,
    process_garden_files,
    remove_empty_or_hidden_folders,
)
from pandoc_wrappers.pelican_build import BLOG_CONFIGS, build_blog

HOME = Path.home()
BROWSER = Path(os.environ["BROWSER"])
MD_BIN = "markdown-wrapper"
PANDOC_BIN = Path(shutil.which("pandoc"))  # type: ignore ; tested below
TEMPLATES_FOLDER = HOME / ".pandoc/templates"
WEB_ROOT = HOME / "data/2web"

if not all([HOME, BROWSER, PANDOC_BIN, MD_BIN, TEMPLATES_FOLDER]):
    raise FileNotFoundError("Your environment is not configured correctly")


# ─── Site configurations ───────────────────────────────────────────────

SITE_CONFIGS: dict[str, dict] = {
    "plan-garden": {
        "type": "garden",
        "source": HOME / "joseph/plan/ob-plan",
        "output": HOME / "joseph/plan/ob-web",
    },
    "codex-garden": {
        "type": "garden",
        "source": HOME / "joseph/ob-codex",
        "output": HOME / "joseph/ob-web",
    },
}

# Derive blog site configs from canonical BLOG_CONFIGS (between gardens and markdown)
for _blog_name, _blog_cfg in BLOG_CONFIGS.items():
    SITE_CONFIGS[f"{_blog_name}-blog"] = {"type": "blog", **_blog_cfg}

SITE_CONFIGS.update(
    {
        "work-markdown": {
            "type": "markdown",
            "source": HOME / "data/1work",
        },
        "joseph-markdown": {
            "type": "markdown",
            "source": HOME / "joseph",
        },
    }
)

# Post-build hooks run after specific sites
POST_BUILD_HOOKS: dict[str, str] = {
    "plan-garden": "transclude_planning_page",
}


# ─── Garden building ──────────────────────────────────────────────────


def build_garden(
    _name: str, config: dict, args: argparse.Namespace, *, trigger: Path | None = None
) -> str:
    """Build a garden site: copy vault, convert wikilinks, then markdown-wrapper."""
    source = Path(config["source"])
    output = Path(config["output"])

    if args.force_update:
        clear_directory(output)

    copy_vault(source, output)
    remove_empty_or_hidden_folders(output)

    note_index = build_note_index(output)
    wikilinks_converted = process_garden_files(output, note_index)

    review_created_or_deleted_files(source, output)
    create_index(source, output)

    n_files = find_convert_md(args, output)

    parts = []
    if wikilinks_converted:
        parts.append(f"{wikilinks_converted} wikilinks converted")
    if n_files:
        parts.append(f"{n_files} files via markdown-wrapper")
    else:
        why = f"triggered by {trigger.name}" if trigger else "forced"
        parts.append(f"nothing to convert ({why})")
    return ", ".join(parts)


def create_index(vault_path: Path, export_path: Path) -> None:
    """Create a new HTML index for the export vault."""
    log.info(f"creating index for {vault_path}")
    vault_index_file = vault_path / "_index.md"
    export_index_file = export_path / "_index.md"

    with vault_index_file.open("w") as output_file:
        output_file.write(f"# Index of {vault_path.name}\n")
        for path in vault_path.glob("**/*.md"):
            relative_path = path.relative_to(vault_path)
            link_text = f"[{relative_path.with_suffix('')}]({relative_path})"
            depth = len(relative_path.parts) - 1
            indentation = "  " * depth
            output_file.write(f"{indentation}- {link_text}\n")

    shutil.copy2(vault_index_file, export_index_file)
    log.info(f"created {output_file=} and {export_index_file=}")


def review_created_or_deleted_files(src_path: Path, dst_path: Path) -> bool:
    """Review for created or deleted files.

    Check dst_path and create or delete HTML files based on the presence of
    their corresponding markdown in src_path.
    Created HTML is set with an early mtime so find_convert_md() knows
    to process it.
    """
    has_changed = False
    log.info(f"checking for new markdown files in {dst_path}")
    for dst_md_file in dst_path.glob("**/*.md"):
        log.debug(f"  {dst_md_file=}")
        html_file = dst_md_file.with_suffix(".html")
        if not html_file.exists():
            html_file.touch()
            os.utime(html_file, (0, 0))
            log.debug(f"created {html_file}")
            has_changed = True

    log.info(f"checking for deleted markdown files in {src_path}")
    for dst_md_file in dst_path.glob("**/*.md"):
        src_md_file = src_path / dst_md_file.relative_to(dst_path)
        if not src_md_file.exists():
            dst_md_file.unlink()
            dst_md_file.with_suffix(".html").unlink()
            log.debug(f"deleted {dst_md_file}")
            has_changed = True

    return has_changed


# ─── Markdown building ────────────────────────────────────────────────


def build_markdown(
    _name: str, config: dict, args: argparse.Namespace, *, trigger: Path | None = None
) -> str:
    """Build markdown sites: convert changed .md → .html via markdown-wrapper."""
    source = Path(config["source"])
    n_files = find_convert_md(args, source)
    if n_files:
        return f"{n_files} files via markdown-wrapper"
    why = f"triggered by {trigger.name}" if trigger else "forced"
    return f"nothing to convert ({why})"


def find_convert_md(args: argparse.Namespace, source_path: Path) -> int:
    """Find and convert any markdown file whose HTML file is older than it.

    Returns the number of files processed.
    """
    files_to_process = []

    for fn_md in source_path.glob("**/*.md"):
        fn_html = fn_md.with_suffix(".html")
        if fn_html.exists() and fn_md.stat().st_mtime > fn_html.stat().st_mtime:
            log.debug(
                f"""{fn_md} {fn_md.stat().st_mtime} """
                + f"""> {fn_html} {fn_html.stat().st_mtime}"""
            )
            files_to_process.append(fn_md)

    log.info(f"{files_to_process=}")
    invoke_md_wrapper(args, files_to_process)
    return len(files_to_process)


def invoke_md_wrapper(args: argparse.Namespace, files_to_process: list[Path]) -> None:
    """Configure arguments for `markdown-wrapper.py` and invoke."""
    for fn_md in files_to_process:
        log.info(f"updating fn_md {fn_md}")
        path_md = Path(fn_md)
        content = path_md.read_text()
        md_cmd = [MD_BIN]
        md_args = []
        if args.verbose > 0:
            md_args.extend([f"-{args.verbose * 'V'}"])
        tmp_body_fn = None

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
        match_md_opts = re.search('^md_opts_: "?(.*)"?', content, re.MULTILINE)
        if match_md_opts:
            md_opts = match_md_opts.group(1).strip().split(" ")
            if len(md_opts) != len(set(md_opts)):
                raise ValueError(
                    f"Duplicate options specified in md_opts_ {md_opts} {fn_md}"
                )
            log.debug(f"{md_opts=}")
            md_args.extend(md_opts)
        md_cmd.extend(md_args)
        md_cmd.extend([str(path_md)])
        md_cmd = list(filter(None, md_cmd))
        log.warning(f"{md_cmd=}")
        call(md_cmd, cwd=path_md.parent)
        if tmp_body_fn:
            Path(tmp_body_fn).unlink()


# ─── Blog building (delegates to pelican_build) ──────────────────────


def build_blog_site(
    _name: str, config: dict, _args: argparse.Namespace, *, trigger: Path | None = None
) -> str:
    """Build a blog site via pelican_build."""
    build_blog(config, force=True)  # needs_build already checked in dispatch
    return (
        f"rebuilt via pelican (triggered by {trigger.name})"
        if trigger
        else "rebuilt via pelican"
    )


# ─── HTML utilities (transclusion) ───────────────────────────────────


def remove_chunks(soup, selectors: list[str]) -> None:
    """Remove chunks of HTML given CSS selectors."""
    for selector in selectors:
        chunks = soup.select(selector)
        for chunk in chunks:
            chunk.extract()


def rewrite_relative_urls(soup, container_selector: str, base_url: str) -> None:
    """Prefix relative URLs in transcluded content with base_url."""
    for tag in soup.select(f"{container_selector} [href], {container_selector} [src]"):
        for attr in ("href", "src"):
            val = tag.get(attr)
            if val and not val.startswith(
                ("http://", "https://", "mailto:", "data:", "#", "/")
            ):
                tag[attr] = base_url + val


def transclude(
    receiving_page: Path,
    receiving_selector: str,
    source_page: Path,
    source_selector: str,
    remove_selectors: list[str],
    base_url: str = "",
) -> str:
    """Transclude the source_page into the receiving_page using CSS selectors.

    If base_url is provided, relative URLs in the transcluded content are
    rewritten with this prefix, replacing the need for a <base> element.
    """
    content_receiving = Path(receiving_page).read_text().strip()
    content_source = Path(source_page).read_text().strip()
    receiving_soup = BeautifulSoup(content_receiving, "html.parser")
    source_soup = BeautifulSoup(content_source, "html.parser")

    remove_chunks(source_soup, remove_selectors)

    source_body_contents: list = source_soup.select(source_selector)
    embed_here_div = receiving_soup.select_one(receiving_selector)

    if source_body_contents and embed_here_div:
        embed_here_div.clear()
        for content in source_body_contents:
            embed_here_div.append(content.extract())
    else:
        raise RuntimeError("There was no embeddable content or location found.")

    if base_url:
        rewrite_relative_urls(receiving_soup, receiving_selector, base_url)

    return str(receiving_soup)


def transclude_planning_page() -> None:
    """Transclude Obsidian Home.html into the planning page."""
    planning_page = HOME / "joseph/plan/index.html"
    modified_html = transclude(
        receiving_page=planning_page,
        receiving_selector="div#embed-here",
        source_page=HOME / "joseph/plan/ob-web/Home.html",
        source_selector="body > *",
        remove_selectors=["div#obsidian-footer", "header"],
        base_url="ob-web/",
    )
    if modified_html:
        planning_page.write_text(modified_html)


# ─── Utilities ────────────────────────────────────────────────────────


def _find_newest(directory: Path, glob: str = "*.html") -> Path:
    """Find the newest file matching glob in directory.

    Returns a nonexistent path if no files found (triggers build).
    """
    newest = None
    newest_mtime = 0.0
    for f in directory.rglob(glob):
        try:
            mtime = f.stat().st_mtime
        except FileNotFoundError, OSError:
            continue
        if mtime > newest_mtime:
            newest = f
            newest_mtime = mtime
    return newest if newest else directory / ".no-sentinel"


def get_sentinel(config: dict) -> Path:
    """Return an output file whose mtime represents "last build time" for this site.

    needs_build() compares source .md files against this sentinel to decide
    whether a rebuild is needed. Each site type uses a different sentinel:
      - garden: newest .html in the export output dir
      - blog: Pelican's index.html (regenerated on every blog build)
      - markdown: newest .html in source tree (sits alongside .md files)
    """
    site_type = config["type"]
    if site_type == "garden":
        return _find_newest(Path(config["output"]), "*.html")
    elif site_type == "blog":
        return Path(config["output"])
    else:  # markdown
        return _find_newest(Path(config["source"]), "*.html")


def chmod_recursive(
    path: Path, dir_perms: int = 0o755, file_perms: int = 0o644
) -> None:
    """Fix permissions on a generated/exported tree if needed."""
    log.debug(f"changing perms to {dir_perms:o};{file_perms:o} on {path=}")
    for item in path.rglob("*"):
        if item.is_dir():
            item.chmod(dir_perms)
        elif item.is_file():
            item.chmod(file_perms)


# ─── Dispatch ─────────────────────────────────────────────────────────

BUILD_FN = {
    "garden": build_garden,
    "blog": build_blog_site,
    "markdown": build_markdown,
}


def main():
    """Provide main entry point."""
    arg_parser = argparse.ArgumentParser(
        description="Build static HTML versions of various sites"
    )
    arg_parser.add_argument(
        "sites",
        nargs="*",
        metavar="SITE",
        help=f"Sites to build (default: all). Choices: {', '.join(SITE_CONFIGS)}",
    )
    arg_parser.add_argument(
        "-f",
        "--force-update",
        action="store_true",
        default=False,
        help="Force rebuild even if no files changed",
    )
    arg_parser.add_argument(
        "-n",
        "--notes-handout",
        action="store_true",
        default=False,
        help="Force creation of notes handout even if not class slide",
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
        help="increase verbosity from critical though error, warning, info, and debug",
    )
    arg_parser.add_argument("--version", action="version", version=__version__)
    args = arg_parser.parse_args()

    SCRIPT_STEM = Path(__file__).stem
    log_level = log.ERROR - (args.verbose * 10)
    LOG_FORMAT = "%(levelname).4s %(funcName).10s:%(lineno)-4d| %(message)s"
    log_config = {"level": log_level, "format": LOG_FORMAT}
    if args.log_to_file:
        log_config.update({"filename": f"{SCRIPT_STEM}.log", "filemode": "w"})
        print(f"Logging to file: {SCRIPT_STEM}.log")
    log.basicConfig(**log_config)

    # Select sites to build
    if args.sites:
        unknown = set(args.sites) - set(SITE_CONFIGS)
        if unknown:
            arg_parser.error(
                f"Unknown sites: {', '.join(unknown)}. "
                f"Choices: {', '.join(SITE_CONFIGS)}"
            )
        selected = {name: SITE_CONFIGS[name] for name in args.sites}
    else:
        selected = SITE_CONFIGS

    skipped = []
    for name, config in selected.items():
        source = Path(config["source"])
        sentinel = get_sentinel(config)
        # For markdown sites, only consider .md files that have a .html sibling
        sibling = ".html" if config["type"] == "markdown" else ""
        trigger = needs_build(source, sentinel, require_sibling=sibling)

        if not args.force_update and not trigger:
            skipped.append(name)
            continue

        build_fn = BUILD_FN[config["type"]]
        summary = build_fn(name, config, args, trigger=trigger)
        print(f"  {name}: {summary}")

        # Run post-build hooks
        hook_name = POST_BUILD_HOOKS.get(name)
        if hook_name:
            hook_fn = globals()[hook_name]
            hook_fn()

    if skipped:
        print(f"  skipped (no changes): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
