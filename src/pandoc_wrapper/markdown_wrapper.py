#! /usr/bin/env python3
# (c) Copyright 2008-2012 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

"""A wrapper script for pandoc that handles my own issues.

1. associates the result with a particular style sheet.
2. can replace [@key] with hypertext'd refs from bibliographic DB.
3. makes use of reveal.js for presentations.
"""

# TODO:
#  1. reduce redundant references: page only, if key already cited
#  2. replace square brackets with round when no URL.
#  3. restore move_punctuation_outside,
#     move each of these periods to right of quotation mark:
#     a. if using note style: "I do what I hate" [#@Paul2006r7].
#     b. all styles: "Testes Testes Testes."
# TODO 2020-12-16: support citations to links
#   (perhaps as variation to --presentation)
#   https://groups.google.com/g/pandoc-discuss/c/MTJDaCzjc0c
#   1. md2bib.py: ability to output `[@key]: URL`
#   2. markdown-wrapper.py:
#       a. `-f` argument to disable citations
#       b. append output of md2bib.py

__author__ = "Joseph Reagle"
__copyright__ = "Copyright (C) 2009-2025 Joseph Reagle"
__license__ = "GLPv3"
__version__ = "1.0"

import argparse
import codecs
import functools
import logging as log
import os
import re
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from lxml import etree as et

from pandoc_wrapper import md2bib

HOME = Path.home()
WEBROOT = HOME / "e/clear/data/2web/reagle.org"
BROWSER = os.environ["BROWSER"].replace("*", " ")
PANDOC_BIN = Path(shutil.which("pandoc"))  # type: ignore # test for None below
MD_BIN = Path(shutil.which("markdown-wrapper"))  # type: ignore # test for None below
if not all([HOME, BROWSER, PANDOC_BIN, MD_BIN]):
    raise FileNotFoundError("Your environment is not configured correctly")

FONTAWESOME_URL = "https://reagle.org/joseph/talks/_custom/fontawesome/css/all.min.css"
HANDOUTS_URL = "https://reagle.org/joseph/talks/_custom/class-handouts-201306.css"


def hyperize(cite_match: re.Match[str], bib_chunked: dict[str, dict[str, str]]) -> str:
    """Hyperize every non-overlapping occurrence and return to PARENS_KEY.sub."""
    cite_replacement = []
    url = None
    citation = cite_match.group(0)
    key = citation.split("@", 1)[1]
    log.info(f"**   processing key: {key}")
    reference = bib_chunked.get(key)
    if reference is None:
        print(f"WARNING: key {key} not found")
        return key
    else:
        log.info(reference.items())
    url = reference.get("url")
    url = url[1:-1] if url and url.startswith("<") and url.endswith(">") else url
    log.info(f"{url=}")
    title = reference.get("title-short")
    log.info(f"{title=}")
    last_name, year, _ = re.split(r"(\d\d\d\d)", key)
    if last_name.endswith("Etal"):
        last_name = last_name[0:-4] + " et al."

    if "original-date" in reference:
        year = f"{reference['original-date']}/{year}"
        log.info(f"!original_date={year}")
    if citation.startswith("-"):
        key_text = re.findall(r"\d\d\d\d.*", key)[0]  # year
    else:
        key_text = f"{last_name} {year}"

    log.debug(f"**   url = {url}")
    if url:
        cite_replacement.append(f"[{key_text}]({url})")
    elif title:
        title = title.replace("{", "").replace("}", "")
        cite_replacement.append(f'{key_text}, "{title}"')
    else:
        cite_replacement.append(f"{key_text}")
    log.debug(f"**   using {cite_replacement}=")
    return "".join(cite_replacement)


def make_parens(cite_match: re.Match[str]) -> str:
    """Convert to balanced parens."""
    return "(" + cite_match.group(0)[1:-1] + ")"


def link_citations(line: str, bib_chunked: dict[str, dict[str, str]]) -> str:
    """Turn pandoc/markdown citations into links within parenthesis.

    Used only with citations in presentations.
    """
    # TODO: harmonize within markdown-wrapper.py and with md2bib.py 2021-06-25
    PARENS_KEY = re.compile(
        r"""
        (-?@        # at-sign with optional negative
        (?<!\\@)    # negative look behind for escape slash
        [\w|-]+)    # one or more alphanumerics or hyphens
        """,
        re.VERBOSE,
    )  # -@Clark-Flory2010fpo

    # TODO: harmonize within markdown-wrapper.py and with md2bib.py 2021-06-25
    PARENS_BRACKET_PAIR = re.compile(
        r"""
        \[[^\]]*    # opening bracket follow by 0+ non-closing bracket
        [-#\\]?@    # at-sign preceded by optional hyphen or pound or escape
        [^\]]+\]    # chars up to closing bracket
        """,
        re.VERBOSE,
    )

    line = PARENS_BRACKET_PAIR.sub(make_parens, line)
    log.debug(f"{line}")
    line = PARENS_KEY.sub(lambda match_obj: hyperize(match_obj, bib_chunked), line)
    log.debug(f"{line}")
    return line


def process_commented_citations(args: argparse.Namespace, line: str) -> str:
    """Match stuff within a bracket that has no other brackets within."""
    # TODO 2021-06-18: replace this with a pandoc filter?

    # TODO: harmonize within markdown-wrapper.py and with md2bib.py 2021-06-25
    PARENS_BRACKET_PAIR = re.compile(
        r"""
        [ |^]       # space or caret
        \[[^\[]+    # open_bracket followed by 1+ non-open_brackets
        [-#]?@      # at-sign preceded by optional hyphen or pound
        [^\]]+\]    # 1+ non-closing-brackets, closing bracket
        """,
        re.VERBOSE,
    )

    # Create a partial function with args bound to it
    quash_with_args = functools.partial(quash, args=args)
    # Pass the partial function to subn
    # log.debug(f"old_line = {line}")
    new_line = PARENS_BRACKET_PAIR.subn(quash_with_args, line)[0]
    # log.debug(f"new_line = {new_line}")
    # If I quashed a citation completely, I might have a period after a quote
    if args.quash_citations and ("]." in line and '".' in new_line):  # imperfect test
        new_line = new_line.replace('".', '."')
    return new_line


def quash(cite_match: re.Match[str], args: argparse.Namespace) -> str:
    """Collect and rewrite citations.

    if args.quash_citations drop commented citations, eg [#@Reagle2012foo]
    else uncomment
    """
    citation = cite_match.group(0)
    log.debug(f"citation = '{citation}'")
    prefix = "^" if citation[0] == "^" else " "
    chunks = citation[2:-1].split(";")  # isolate chunks from ' [' + ']'
    log.debug(f"chunks = {chunks}")
    citations_keep = []
    for chunk in chunks:
        log.debug(f"  chunk = '{chunk}'")
        if "#@" in chunk:
            if args.quash_citations:
                log.debug("  quashed")
            else:
                chunk = chunk.replace("#@", "@")
                log.debug(f"  keeping chunk = '{chunk}'")
                citations_keep.append(chunk)
        else:
            citations_keep.append(chunk)

    if citations_keep:
        log.debug(f"citations_keep = '{citations_keep}'")
        return f"{prefix}[" + ";".join(citations_keep) + "]"
    else:
        return ""


def em_mask(matchobj) -> str:
    """Replace emphasis with underscores that pandoc will ignore."""
    log.debug("return replace function")
    return "&#95;" * len(matchobj.group(0))


def make_relpath(path_to: Path | str, path_from: Path | str) -> str:
    """Return relative path that works on filesystem and server.

    >>> make_relpath('https://reagle.org/joseph/2003/papers.css',
    ... '/Users/reagle/joseph/2021/pc/' )
    '../../2003/papers.css'
    >>> make_relpath('https://reagle.org/joseph/2003/papers.css',
    ... '/Users/reagle/joseph/2021/pc/pc-syllabus-SP.html' )
    '../../2003/papers.css'
    """
    log.debug(f"arguments {path_to=} {path_from=}")
    if isinstance(path_to, str):
        if path_to.startswith("http"):
            path_to = WEBROOT / urlparse(path_to).path.lstrip("/")
        else:
            path_to = Path(path_to)
    log.debug(f"final {path_to=}")

    log.debug(f"argument {path_from=}")
    if isinstance(path_from, str):
        path_from = Path(path_from)
    if path_from.is_file():
        log.debug(f"is_file: {path_from=}")
        path_from = path_from.parent
    elif path_from.is_dir():
        log.debug(f"is_dir: {path_from=}")
    else:
        raise OSError(f"{path_from=} I don't know what this is path_from is.")

    path_from = path_from.resolve()
    log.debug(f"final {path_from=}")

    try:
        result = path_to.relative_to(path_from, walk_up=True)
    except ValueError:
        # Pathlib path_to fails, convert to strings and use os.path.relpath
        result = Path(os.path.relpath(str(path_to), str(path_from)))

    log.info(f"{result=}")
    return str(result)


def create_handout(args: argparse.Namespace, ori_md_f: Path, intermedia_md_f: Path):
    """Create handout version of the slide."""
    log.info("HANDOUT START")
    log.info(f"{ori_md_f=}")
    log.info(f"{intermedia_md_f=}")
    EM_RE = re.compile(r"(?<! _)_([^_]+?)_ ")

    md_dir = ori_md_f.parent
    log.info(f"{md_dir=}")
    if "/talks" in str(ori_md_f):
        handout_f = Path(str(ori_md_f).replace("/talks/", "/handouts/"))
        handout_dir = handout_f.parent
        log.info(f"{handout_dir=}")
        if not handout_dir.exists():
            handout_dir.mkdir(parents=True)
        skip_to_next_header = False
        with handout_f.open("w") as handout_fd:
            handout_content = intermedia_md_f.read_text()
            log.info(f"md_dir = '{md_dir}', handout_dir = '{handout_dir}'")
            relpath_prefix = make_relpath(md_dir, handout_dir)
            log.info(f"media_relpath = '{relpath_prefix}'")
            handout_content = (
                handout_content.replace(" data-src=", " src=")
                .replace("](media/", f"]({relpath_prefix}/media/")
                .replace('="media/', f'="{relpath_prefix}/media/')
            )
            for line in handout_content.split("\n"):
                if args.partial_handout:
                    line = line.replace("### ", " ")
                    if line.startswith(("# ", "## ")):
                        skip_to_next_header = " _" in line
                        handout_fd.write(line)
                    elif not skip_to_next_header:
                        line = EM_RE.subn(em_mask, line)[0]
                        log.debug(f"line = '{line}'")
                        handout_fd.write(line)
                    else:
                        handout_fd.write("\n")
                else:
                    handout_fd.write(line)
                handout_fd.write("\n")  # new line at end of line
            deck_link = f"{relpath_prefix}/{ori_md_f.with_suffix('.html').name}"
            deck_link_markup = f"[▶]({deck_link}){{.decklink}}\n"
            handout_fd.write(deck_link_markup)
        md_cmd = [
            MD_BIN,
            "--divs",
            "--toc",
            "-w",
            "html",
            "-c",
            HANDOUTS_URL,
            str(handout_f),
        ]
        log.info(f" handout {md_cmd=}")
        subprocess.run(md_cmd)
        if not args.keep_tmp:
            handout_f.unlink()
    log.info("HANDOUT DONE")


def number_elements(content: str) -> str:
    """Add section and paragraph marks to content which is parsed as HTML."""
    log.info("parsing without comments")
    parser = et.HTMLParser(remove_comments=True, remove_blank_text=True)
    doc = et.parse(StringIO(content), parser)

    log.debug("add heading marks")
    # Cast to list of Element objects
    headings = cast(
        list[et._Element], doc.xpath("//*[name()='h2' or name()='h3' or name()='h4']")
    )
    heading_num = 1
    for heading in headings:
        span = et.Element("span")  # prepare span element for section #
        span.set("class", "headingnum")
        h_id = heading.get("id")  # grab id of existing a element
        span.tail = heading.text
        a = et.SubElement(span, "a", href=f"#{h_id}")
        heading.text = None  # this has become the tail of the span
        a.text = "§" + str(heading_num) + "\u00a0"  # &nbsp;
        heading.insert(0, span)  # insert span at beginning of parent
        heading_num += 1

    log.debug("add paragraph marks")
    # Cast to list of Element objects
    paras = cast(list[et._Element], doc.xpath("/html/body/p | /html/body/blockquote"))
    para_num = 1
    for para in paras:
        para_num_str = f"{para_num:0>2}"
        span = et.Element("span")
        span.set("class", "paranum")
        span.tail = para.text
        a_id = "p" + str(para_num_str)
        a = et.SubElement(span, "a", id=a_id, name=a_id, href=f"#{a_id}")
        a.text = "p" + str(para_num_str) + "\u00a0"  # &nbsp;
        para.text = None
        para.insert(0, span)
        para_num += 1

    content = et.tostring(
        doc.getroot(),
        method="xml",
        encoding="utf-8",
        pretty_print=True,
    ).decode("utf-8")

    return content


def stylize_names(content: str) -> str:
    """Use regex to stylize r/forums, u/usernames, and p/pseudonyms.

    Note: This regex assumes names do not contain consecutive hyphens.
    This aligns with Reddit's naming conventions (subreddits cannot have
    hyphens; usernames cannot have consecutive hyphens) and ensures proper
    handling of markdown en dashes (--) and em dashes (---).

    >>> stylize_names("Did you read r/Python. What about /r/python? Okay!")
    'Did you read `r/Python`. What about `/r/python`? Okay!'
    >>> stylize_names("u/code_master posted in r/learnpython.")
    '`u/code_master` posted in `r/learnpython`.'
    >>> stylize_names("Multiple u/user1 and r/sub1 and p/user-2.")
    'Multiple `u/user1` and `r/sub1` and `p/user-2`.'
    >>> stylize_names("Works with u/dot.user and r/dot.sub.")
    'Works with `u/dot.user` and `r/dot.sub`.'
    >>> stylize_names("Preserve https://www.reddit.com/r/reddit.com/comments/lghsk/ .")
    'Preserve https://www.reddit.com/r/reddit.com/comments/lghsk/ .'
    >>> stylize_names("The user/operator manual explains both roles.")
    'The user/operator manual explains both roles.'
    >>> stylize_names("The subreddit---r/AITAH---is funny.")
    'The subreddit---`r/AITAH`---is funny.'
    """
    NAME_PATTERN = re.compile(
        r"""
        (?:                     # Non-capturing group for URLs and more
            (?<=\s)             # Preceded by whitespace (fixed-width: 1)
            |                   # OR
            (?<=^)              # At start of string (fixed-width: 0)
            |                   # OR
            (?<=[^\w/])         # Preceded by non-word char that's not / (fixed-width: 1)
        )
        (                       # Group 1: Prefix (u/, r/, or p/)
            /?                  # Optional starting slash, e.g., /r/foo
            \b                  # Word boundary to avoid matching mid-word
            [urp]               # Match 'u', 'r', or 'p' (user, reddit, or pseudo)
            /                   # Required forward slash after the letter
        )
        (                       # Group 2: The actual name
            \w                  # Must start with a word character
            (?:                 # Non-capturing group for the middle part
                [\w]            # More word characters
                |               # OR
                (?:             # Non-capturing group
                    [-.]        # Hyphen or dot
                    (?=\w)      # ...but only if followed by a word char
                )
            )*                  # Zero or more of these
        )
        """,
        re.VERBOSE,
    )
    return NAME_PATTERN.sub(r"`\1\2`", content)


def pre_pandoc_processing(
    abs_fn: Path,
    args: argparse.Namespace,
    base_ext: str,
    base_fn: Path,
    bib_chunked: dict[str, dict[str, str]],
    pandoc_opts: list,
):
    """Perform textual processing before pandoc."""
    bib_subset_tmp_fn = None  # a subset of main biblio
    target_sufix = "." + args.write_format
    fn_tmp_1 = Path(f"{base_fn}-1{base_ext}")  # as read
    fn_tmp_2 = Path(f"{base_fn}-2{base_ext}")  # pre-pandoc
    fn_tmp_3 = Path(f"{base_fn}-3{target_sufix}")  # post-pandoc copy
    fn_result = base_fn.with_suffix(target_sufix)
    cleanup_tmp_fns = [fn_tmp_1, fn_tmp_2, fn_tmp_3]
    pandoc_opts.extend(["-o", fn_result])
    pandoc_opts.extend(["--mathjax"])
    if args.style_csl:
        if args.bibtex:
            bib_fn = HOME / "joseph/readings.bib"
            bib_ext = ".bib"
            parse_func = md2bib.chunk_bibtex
            subset_func = md2bib.subset_bibtex
            emit_subset_func = md2bib.emit_bibtex_subset
        else:
            bib_fn = HOME / "joseph/readings.yaml"
            bib_ext = ".yaml"
            parse_func = md2bib.chunk_yaml
            subset_func = md2bib.subset_yaml
            emit_subset_func = md2bib.emit_yaml_subset

        pandoc_opts.extend([f"--csl={args.style_csl[0]}"])
        log.info("generate temporary subset bib for speed")
        bib_subset_tmp_fn = base_fn.with_suffix(bib_ext)
        cleanup_tmp_fns.append(bib_subset_tmp_fn)
        keys = md2bib.get_keys_from_file(abs_fn)
        log.debug(f"keys = {keys}")
        if keys:
            entries = parse_func(bib_fn.read_text().splitlines())
            subset = subset_func(entries, keys)
            emit_subset_func(subset, bib_subset_tmp_fn.open(mode="w"))
            pandoc_opts.extend(
                [
                    f"--bibliography={bib_subset_tmp_fn}",
                    "--citeproc",
                ]
            )
    shutil.copyfile(abs_fn, fn_tmp_1)
    content = fn_tmp_1.read_text(encoding="UTF-8", errors="replace")
    if content[0] == codecs.BOM_UTF8.decode("utf8"):
        content = content[1:]
    new_lines = []
    for line in content.split("\n"):
        # TODO: fix Wikicommons relative network-path references
        # so the URLs work on local file system (i.e.,'file:///')
        line = line.replace('src="//', 'src="http://')
        # TODO: encode ampersands in URLs
        line = process_commented_citations(args, line)
        if args.stylize_names:
            line = stylize_names(line)
        if args.bibliography:  # create hypertext refs from bib db
            line = link_citations(line, bib_chunked)
            # log.debug(f"\n** line is now {line}")
        # Color some revealjs top of column slides
        if args.presentation and line.startswith("# ") and "{data-" not in line:
            line = line.strip() + ' {data-background="LightBlue"}\n'
        # log.debug(f"END line: '{line}'")
        new_lines.append(line)

    fn_tmp_2.write_text("\n".join(new_lines), encoding="UTF-8", errors="replace")

    return cleanup_tmp_fns, fn_result, fn_tmp_2, fn_tmp_3


def set_pandoc_options(args: argparse.Namespace, fn_path: Path):  # noqa: C901
    """Configure pandoc configuration based on arguments."""
    pandoc_inputs = []
    pandoc_opts = ["-w", args.write_format]
    if "html" not in args.write_format:
        print(
            f"[WARNING] MW: writing to non-HTML format "
            f"'{args.write_format}' for '{fn_path.name}'"
        )
    # if args.write_format == 'markdown-citations':
    #     pandoc_opts.extend(['--csl=sage-harvard.csl',
    #         '--bibliography=/home/reagle/joseph/readings.yaml'])
    pandoc_opts.extend(
        [
            "--defaults",
            "base.yaml",  # include tab stop, lang, etc.
            "--standalone",
            "--lua-filter",
            "pandoc-quotes.lua",  # specify quote marks and lang
            "--filter",
            "pandoc-plot",  # generate plots and figures, e.g., mermaid, dot
            "--strip-comments",
            "--wrap=auto",
            "--columns=100",
            "-c",
            make_relpath(
                FONTAWESOME_URL,
                fn_path,
            ),
        ]
    )

    if args.pantable:
        pandoc_opts.extend(
            [
                "-F",
                "pantable",  # allows tables as CSV, slows by 50%
            ]
        )
    if args.presentation:
        args.validate = False
        args.css = False
        pandoc_opts.extend(
            [
                "-c",
                "../_custom/reveal4js.css",
                "-t",
                "revealjs",
                "--slide-level=2",
                "-V",
                "revealjs-url=../_reveal4.js",
                "-V",
                "theme=beige",
                "-V",
                "transition=linear",
                "-V",
                "history=true",
                "-V",
                "zoomKey=shift",
                # '--no-highlight', # conflicts with reveal's highlight.js
            ]
        )
    elif args.write_format.startswith("html") and args.css:
        # ?DO NOT use relpath as this is a commandline argument?
        # pandoc_opts.extend(["-c", args.css])
        pandoc_opts.extend(["-c", make_relpath(args.css, fn_path)])

    elif args.write_format.startswith("docx"):
        if args.reference_doc:
            pandoc_opts.extend(["--reference-doc", args.reference_doc])
        else:
            pandoc_opts.extend(
                ["--reference-doc", HOME / ".pandoc/custom-reference.docx"]
            )
    if args.condensed:
        pandoc_opts.extend(
            [
                "-c",
                make_relpath(
                    "https://reagle.org/joseph/2003/papers-condensed.css",
                    fn_path,
                ),
            ]
        )
    if args.toc:
        pandoc_opts.extend(["--toc"])
        if args.toc_depth:
            pandoc_opts.extend([f"--toc-depth={args.toc_depth[0]}"])
    if args.embed_resources:
        pandoc_opts.extend(["--embed-resources"])
    if args.extract_media:
        pandoc_opts.extend(["--extract-media=media"])
    if args.divs:
        pandoc_opts.extend(["--section-divs"])
    if args.include_after_body:
        pandoc_opts.extend([f"--include-after-body={args.include_after_body[0]}"])
    if args.lua_filter:
        pandoc_opts.extend(["--lua-filter", args.lua_filter[0]])
    if args.metadata:
        pandoc_opts.extend(["--metadata", args.metadata[0]])
    if args.style_chicago:
        args.style_csl = ["chicago-author-date.csl"]
    return pandoc_inputs, pandoc_opts


def pandoc_processing(
    abs_fn: Path,
    args: argparse.Namespace,
    fn_tmp_2: Path,
    pandoc_inputs: list,
    pandoc_opts: list,
):
    """Execute pandoc."""
    pandoc_cmd = [
        PANDOC_BIN,
        "-r",
        f"{args.read}",
    ]
    pandoc_cmd.extend(pandoc_opts)
    pandoc_inputs.insert(0, fn_tmp_2)
    pandoc_cmd.extend(pandoc_inputs)
    pandoc_cmd_str = " ".join(str(item) for item in pandoc_cmd)
    log.warning(pandoc_cmd_str)
    pandoc_result = subprocess.run(pandoc_cmd, capture_output=True, text=True)
    # I want pandoc stderr warnings in addition to failures
    if pandoc_result.returncode != 0:
        raise ValueError(
            f"pandoc returned {pandoc_result.returncode}: {pandoc_result.stderr}"
            f"\non {pandoc_cmd_str}"
        )
    elif pandoc_result.stderr:
        log.critical(f"pandoc stderr:\n{pandoc_result.stderr}\non {pandoc_cmd_str}")
    log.info("done pandoc_cmd")
    if args.presentation:
        create_handout(args, abs_fn, fn_tmp_2)


def post_pandoc_html_processing(
    args: argparse.Namespace, base_fn: Path, fn_result: Path, fn_tmp_3: Path
) -> Path:
    """Complete HTML processing after pandoc."""
    if args.write_format != "html":
        return fn_result
    else:
        # final tweaks html file
        shutil.copyfile(fn_result, fn_tmp_3)  # copy of html for debugging
        content_html = fn_tmp_3.read_text()
        if not content_html:
            raise ValueError("post-pandoc content_html is empty")

        # text alterations
        if args.british_quotes:  # swap double/single quotes
            content_html = content_html.replace('"', "&ldquo;").replace('"', "&rdquo;")
            single_quote_re = re.compile(r"(\W)'(.{2,40}?)'(\W)")
            content_html = single_quote_re.sub(r'\1"\2"\3', content_html)
            content_html = content_html.replace("&ldquo;", r"'").replace("&rdquo;", "'")
        # correct bibliography
        content_html = content_html.replace(" Vs. ", " vs. ")

        if args.presentation:
            # convert to data-src for lazy loading
            lazy_elements_re = re.compile(r"""(\<img|<iframe|<video)(.*?) src=""")
            content_html = lazy_elements_re.sub(r"\1\2 data-src=", content_html)

        # HTML alterations
        if args.number_elements:
            content_html = number_elements(content_html)

        resulting_html_f = base_fn.with_suffix(".html")
        log.info(f"result_fn = '{resulting_html_f}'")
        if args.output:
            resulting_html_f = args.output[0]
        resulting_html_f.write_text(content_html)

        if args.validate:
            subprocess.run(
                [
                    "tidy",
                    "-utf8",
                    "-q",
                    "-i",
                    "-m",
                    "-w",
                    "0",
                    "-asxhtml",
                    resulting_html_f,
                ]
            )
        return resulting_html_f


def process(args: argparse.Namespace):
    """Process files."""
    if args.bibliography:
        bib_fn = HOME / "joseph/readings.yaml"
        bib_chunked = md2bib.chunk_yaml(bib_fn.read_text().splitlines())
    else:
        bib_chunked = {"": {"": ""}}

    log.info(f"args.files = '{args.files}'")
    for in_file in args.files:
        if not in_file:
            continue
        log.info(f"in_file = '{in_file}'")
        abs_fn = in_file.resolve()
        log.info(f"abs_fn = '{abs_fn}'")

        # base_fn, base_ext = splitext(abs_fn)
        base_fn, base_ext = abs_fn.with_suffix(""), abs_fn.suffix
        log.info(f"base_fn = '{base_fn}'")

        # os.path.split(abs_fn)[0]
        fn_path = abs_fn.with_suffix("")
        log.info(f"fn_path = '{fn_path}'")

        pandoc_inputs, pandoc_opts = set_pandoc_options(args, abs_fn)
        cleanup_tmp_fns, fn_result, fn_tmp_2, fn_tmp_3 = pre_pandoc_processing(
            abs_fn, args, base_ext, base_fn, bib_chunked, pandoc_opts
        )
        pandoc_processing(abs_fn, args, fn_tmp_2, pandoc_inputs, pandoc_opts)
        result_fn = post_pandoc_html_processing(args, base_fn, fn_result, fn_tmp_3)

        if args.write_format == "html" and args.launch_browser:
            log.info(f"launching {result_fn}")
            subprocess.run([BROWSER, result_fn])

        if not args.keep_tmp:
            log.info("removing tmp files")
            for cleanup_fn in cleanup_tmp_fns:
                if Path(cleanup_fn).exists():
                    Path(cleanup_fn).unlink()


def main():
    """Parse arguments and hand to functions."""
    import argparse  # http://docs.python.org/dev/library/argparse.html

    arg_parser = argparse.ArgumentParser(
        description="Markdown wrapper with slide and bibliographic options",
        #  formatter_class=argparse.RawTextHelpFormatter,
    )
    arg_parser.add_argument("files", nargs="*", metavar="FILE", type=Path)
    arg_parser.add_argument(
        "-b",
        "--bibliography",
        action="store_true",
        default=False,
        help="turn citations into hypertext w/out CSL",
    )
    arg_parser.add_argument(
        "--bibtex",
        action="store_true",
        default=False,
        help="use .bib file instead of YAML bibliography",
    )
    arg_parser.add_argument(
        "-B",
        "--british-quotes",
        action="store_true",
        default=False,
        help="swap single and double quotes",
    )
    arg_parser.add_argument(
        "-c",
        "--css",
        default="https://reagle.org/joseph/2003/papers.css",
        help="apply non-default CSS",
    )
    arg_parser.add_argument(
        "--condensed",
        action="store_true",
        default=False,
        help="use condensed line spacing CSS",
    )
    arg_parser.add_argument(
        "-d",
        "--divs",
        action="store_true",
        default=False,
        help="use pandoc's --section-divs",
    )
    arg_parser.add_argument(
        "--lua-filter",
        nargs=1,
        help="lua filter (pandoc pass-through)",
    )
    arg_parser.add_argument(
        "--include-after-body",
        nargs=1,
        metavar="FILE",
        help="include at end of body (pandoc pass-through)",
    )
    arg_parser.add_argument(
        "-k",
        "--keep-tmp",
        action="store_true",
        default=False,
        help="keep temporary/intermediary files",
    )
    arg_parser.add_argument(
        "-l",
        "--launch-browser",
        action="store_true",
        default=False,
        help="launch browser to see results",
    )
    arg_parser.add_argument(
        "--metadata",
        nargs=1,
        help="metadata (pandoc pass-through)",
    )
    arg_parser.add_argument(
        "-o", "--output", nargs=1, help="output file path", type=Path
    )
    arg_parser.add_argument(
        "-n",
        "--number-elements",
        action="store_true",
        default=False,
        help="number sections and paragraphs",
    )
    arg_parser.add_argument(
        "-p",
        "--presentation",
        action="store_true",
        default=False,
        help="create presentation with reveal.js",
    )
    arg_parser.add_argument(
        "--pantable",
        action="store_true",
        default=False,
        help="use pantable filter",
    )
    arg_parser.add_argument(
        "--partial-handout",
        action="store_true",
        default=False,
        help="presentation handout is partial/redacted",
    )
    arg_parser.add_argument(
        "-q",
        "--quash-citations",
        action="store_true",
        default=False,
        help="quash citations that begin with hash, e.g., (#@Reagle2012foo)",
    )
    arg_parser.add_argument(
        "-r",
        "--read",
        default="markdown+autolink_bare_uris+mmd_title_block",
        help="reader format and extensions (default: %(default)s). ",
        # TODO: for short _md_opts_, implement diff extension specification
        # "Use '=' to specify +/- extensions to default value "
        # "(e.g., '--read=-bracketed_spans)"
    )
    arg_parser.add_argument(
        "-s",
        "--style-chicago",
        action="store_true",
        default=False,
        help="use CSL chicago-author-date.csl",
    )
    arg_parser.add_argument(
        "-S",
        "--style-csl",
        nargs=1,
        help="specify CSL style (e.g., chicago-fullnote-bibliography.csl)",
    )
    arg_parser.add_argument(
        "--embed-resources",
        action="store_true",
        default=False,
        help="incorporate links: scripts, images, & CSS (pandoc pass-through)",
    )
    arg_parser.add_argument(
        "--extract-media",
        action="store_true",
        default=False,
        help="extract internally specified media, e.g., diagrams, to files (pandoc pass-through)",
    )
    arg_parser.add_argument(
        "--reference-doc",
        nargs=1,
        help="path to a custom-reference.docx file",
    )
    arg_parser.add_argument(
        "--stylize-names",
        action="store_true",
        default=False,
        help="stylize subreddit and user names",
    )
    arg_parser.add_argument(
        "--toc",
        action="store_true",
        default=False,
        help="create table of contents (pandoc pass-through)",
    )
    arg_parser.add_argument(
        "--toc-depth",
        nargs=1,
        help="table of contents depth (pandoc pass-through)",
    )
    arg_parser.add_argument(
        "-v",
        "--validate",
        action="store_true",
        default=False,
        help="validate and tidy HTML",
    )
    arg_parser.add_argument(
        "-w",
        "--write_format",
        default="html",
        help="write format and extensions (default: %(default)s). ",
        # TODO: for short _md_opts_, implement diff extension specification
        # "Use '=' to specify +/- extensions to default value "
        # "(e.g., '--write=-bracketed_spans)"
    )
    arg_parser.add_argument(
        "-L",
        "--log-to-file",
        action="store_true",
        default=False,
        help="log to file PROGRAM.log",
    )
    arg_parser.add_argument(
        "-T", "--tests", action="store_true", default=False, help="run tests"
    )
    arg_parser.add_argument(
        "-V",
        "--verbose",
        action="count",
        default=0,
        help="increase verbosity from critical though error, warning, info, and debug",
    )
    arg_parser.add_argument("--version", action="version", version="1.0")
    args = arg_parser.parse_args()

    SCRIPT_STEM = Path(__file__).stem
    # LOG_FORMAT https://loguru.readthedocs.io/en/stable/api/logger.html#record
    log_level = log.ERROR - (args.verbose * 10)
    LOG_FORMAT = "%(levelname).4s %(funcName).10s:%(lineno)-4d| %(message)s"
    log_config: dict[str, Any] = {"level": log_level, "format": LOG_FORMAT}
    if args.log_to_file:
        log_config.update({"filename": f"{SCRIPT_STEM}.log", "filemode": "w"})
        print(f"Logging to file: {SCRIPT_STEM}.log")
    log.basicConfig(**log_config)

    if args.tests:
        import doctest

        doctest.testmod()
        sys.exit()
    process(args)


if __name__ == "__main__":
    main()
