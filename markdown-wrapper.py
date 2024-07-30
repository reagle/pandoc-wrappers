#! /usr/bin/env python3
# (c) Copyright 2008-2012 by Joseph Reagle
# Licensed under the GPLv3, see <http://www.gnu.org/licenses/gpl-3.0.html>

"""A wrapper script for pandoc that handles my own issues:
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

import codecs
import logging
import os
import re
import shutil
import sys

# from sh import chmod # http://amoffat.github.com/sh/
from io import StringIO
from os import environ, makedirs, remove
from os.path import (
    abspath,
    exists,
    expanduser,
    isdir,
    isfile,
    realpath,
    relpath,
    split,
    splitext,
)
from pathlib import Path
from subprocess import Popen, call
from urllib.parse import urlparse

# from lxml.etree import *
import lxml.etree as et  # type: ignore
from lxml.html import tostring  # type: ignore

import md2bib

HOME = expanduser("~")
WEBROOT = f"{HOME}/e/clear/data/2web/reagle.org"
BROWSER = environ["BROWSER"].replace("*", " ")
PANDOC_BIN = shutil.which("pandoc")
MD_BIN = shutil.which("markdown-wrapper.py")
if not all([HOME, BROWSER, PANDOC_BIN, MD_BIN]):
    raise FileNotFoundError("Your environment is not configured correctly")

log_level = logging.ERROR  # 40

# function aliases
critical = logging.critical
error = logging.error
warning = logging.warning
info = logging.info
debug = logging.debug


def link_citations(line, bib_chunked):
    """Turn pandoc/markdown citations into links within parenthesis.
    Used only with citations in presentations.
    """
    # TODO: harmonize within markdown-wrapper.py and with md2bib.py 2021-06-25
    PARENS_KEY = re.compile(
        r"""
        (-?@        # at-sign with optional negative
        (?<!\\@)    # negative look behind for escape slash
        [\w|-]+)    # one or more alhanumberics or hyphens
        """,
        re.VERBOSE,
    )  # -@Clark-Flory2010fpo

    def hyperize(cite_match):
        """Hyperize every non-overlapping occurrence
        and return to PARENS_KEY.sub
        """
        cite_replacement = []
        url = None
        citation = cite_match.group(0)
        key = citation.split("@", 1)[1]
        info("**   processing key: %s" % key)
        reference = bib_chunked.get(key)
        if reference is None:
            print("WARNING: key %s not found" % key)
            return key
        else:
            info(reference.keys())
        url = reference.get("url")
        info(f"{url=}")
        title = reference.get("title-short")
        info(f"{title=}")
        last_name, year, _ = re.split(r"(\d\d\d\d)", key)
        if last_name.endswith("Etal"):
            last_name = last_name[0:-4] + " et al."

        if "original-date" in reference:
            year = f"{reference['original-date']}/{year}"
            info("original-date!")
        if citation.startswith("-"):
            key_text = re.findall(r"\d\d\d\d.*", key)[0]  # year
        else:
            key_text = f"{last_name} {year}"

        debug("**   url = %s" % url)
        if url:
            cite_replacement.append(f"[{key_text}]({url})")
        elif title:
            title = title.replace("{", "").replace("}", "")
            cite_replacement.append(f'{key_text}, "{title}"')
        else:
            cite_replacement.append(f"{key_text}")
        debug(f"**   using {cite_replacement}=")
        return "".join(cite_replacement)

    # TODO: harmonize within markdown-wrapper.py and with md2bib.py 2021-06-25
    PARENS_BRACKET_PAIR = re.compile(
        r"""
        \[[^\]]*    # opening bracket follow by 0+ non-closing bracket
        [-#\\]?@    # at-sign preceded by optional hyphen or pound or escape
        [^\]]+\]    # chars up to closing bracket
        """,
        re.VERBOSE,
    )

    def make_parens(cite_match):
        """Convert to balanced parens"""
        return "(" + cite_match.group(0)[1:-1] + ")"

    line = PARENS_BRACKET_PAIR.sub(make_parens, line)
    debug(f"{line}")
    line = PARENS_KEY.sub(hyperize, line)
    debug(f"{line}")
    return line


def process_commented_citations(line):
    """Match stuff within a bracket (beginning with ' ' or '^') that
    has no other brackets within
    """
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

    def quash(cite_match):
        """Collect and rewrite citations.
        if args.quash_citations drop commented citations, eg [#@Reagle2012foo]
        else uncomment
        """
        citation = cite_match.group(0)
        debug(f"citation = '{citation}'")
        prefix = "^" if citation[0] == "^" else " "
        chunks = citation[2:-1].split(";")  # isolate chunks from ' [' + ']'
        debug(f"chunks = {chunks}")
        citations_keep = []
        for chunk in chunks:
            debug(f"  chunk = '{chunk}'")
            if "#@" in chunk:
                if args.quash_citations:
                    debug("  quashed")
                else:
                    chunk = chunk.replace("#@", "@")
                    debug(f"  keeping chunk = '{chunk}'")
                    citations_keep.append(chunk)
            else:
                citations_keep.append(chunk)

        if citations_keep:
            debug(f"citations_keep = '{citations_keep}'")
            return f"{prefix}[" + ";".join(citations_keep) + "]"
        else:
            return ""

    debug(f"old_line = {line}")
    new_line = PARENS_BRACKET_PAIR.subn(quash, line)[0]
    debug(f"new_line = {new_line}")
    # if I quashed a citation completely, I might have a period after a quote
    if args.quash_citations:
        if "]." in line and '".' in new_line:  # imperfect test
            new_line = new_line.replace('".', '."')
    return new_line


def create_talk_handout(abs_fn: str, tmp2_fn: str) -> None:
    """If a talk, create a (partial) handout"""
    info("HANDOUT START")
    EM_RE = re.compile(r"(?<! _)_([^_]+?)_ ")

    def em_mask(matchobj):
        """Replace emphasis with underscores"""
        debug("return replace function")
        # underscore that pandoc will ignore
        return "&#95;" * len(matchobj.group(0))

    abs_path = Path(abs_fn)
    tmp2_path = Path(tmp2_fn)
    fn_path = abs_path.parent
    info(f"{fn_path=}")
    info(f"{abs_fn=}")
    info(f"{tmp2_fn=}")
    md_dir = abs_path.parent
    handout_fn = ""
    if "/talks" in abs_fn:
        handout_fn = str(abs_path).replace("/talks/", "/handouts/")
        handout_path = Path(handout_fn)
        handout_dir = handout_path.parent
        info(f"{handout_dir=}")
        if not handout_dir.exists():
            handout_dir.mkdir(parents=True)
        info("creating handout")
        skip_to_next_header = False
        with handout_path.open("w") as handout_f, tmp2_path.open() as tmp2_f:
            content = tmp2_f.read()
            info(f"md_dir = '{md_dir}', handout_dir = '{handout_dir}'")
            media_relpath = relpath(md_dir, handout_dir)
            info(f"media_relpath = '{media_relpath}'")
            content = content.replace(" data-src=", " src=")
            content = content.replace("](media/", f"]({media_relpath}/media/")
            content = content.replace('="media/', f'="{media_relpath}/media/')
            lines = [line + "\n" for line in content.split("\n")]
            for line in lines:
                if args.partial_handout:
                    info(f"args.partial_handout = '{args.partial_handout}'")
                    line = line.replace("### ", " ")
                    if line.startswith(("# ", "## ")):
                        if " _" in line:
                            skip_to_next_header = True
                        else:
                            skip_to_next_header = False
                        handout_f.write(line)
                    elif not skip_to_next_header:
                        line = EM_RE.subn(em_mask, line)[0]
                        debug(f"line = '{line}'")
                        handout_f.write(line)
                    else:
                        handout_f.write("\n")
                else:
                    handout_f.write(line)
            deck_link = f"[deck]({abs_fn}){{.decklink}}"
            handout_f.write(deck_link)
        md_cmd = [
            MD_BIN,
            "--divs",
            "--toc",
            "-w",
            "html",
            "-c",
            "https://reagle.org/joseph/talks/_custom/class-handouts-201306.css",
            str(handout_path),
        ]
        info("handout md_cmd = %s" % " ".join(md_cmd))
        call(md_cmd)
        if not args.keep_tmp:
            handout_path.unlink()
    info("HANDOUT DONE")


def number_elements(content):
    """Add section and paragraph marks to content which is parsed as HTML"""
    info("parsing without comments")
    parser = et.HTMLParser(remove_comments=True, remove_blank_text=True)
    doc = et.parse(StringIO(content), parser)

    debug("add heading marks")
    headings = doc.xpath("//*[name()='h2' or name()='h3' or name()='h4']")
    heading_num = 1
    for heading in headings:
        span = et.Element("span")  # prepare span element for section #
        span.set("class", "headingnum")
        h_id = heading.get("id")  # grab id of existing a element
        span.tail = heading.text
        a = et.SubElement(span, "a", href="#%s" % h_id)
        heading.text = None  # this has become the tail of the span
        a.text = "§" + str(heading_num) + "\u00a0"  # &nbsp;
        heading.insert(0, span)  # insert span at beginning of parent
        heading_num += 1

    debug("add paragraph marks")
    paras = doc.xpath("/html/body/p | /html/body/blockquote")
    para_num = 1
    for para in paras:
        para_num_str = f"{para_num:0>2}"
        span = et.Element("span")
        span.set("class", "paranum")
        span.tail = para.text
        a_id = "p" + str(para_num_str)
        a = et.SubElement(span, "a", id=a_id, name=a_id, href="#%s" % a_id)
        a.text = "p" + str(para_num_str) + "\u00a0"  # &nbsp;
        para.text = None
        para.insert(0, span)
        para_num += 1

    content = tostring(
        doc,
        method="xml",
        encoding="utf-8",
        pretty_print=True,
        include_meta_content_type=True,
    ).decode("utf-8")

    return content


def make_relpath(path_to, path_from):
    """Return relative path that works on filesystem and server

    >>> make_relpath('https://reagle.org/joseph/2003/papers.css',
    ... '/Users/reagle/joseph/2021/pc/' )
    '../../2003/papers.css'
    >>> make_relpath('https://reagle.org/joseph/2003/papers.css',
    ... '/Users/reagle/joseph/2021/pc/pc-syllabus-SP.html' )
    '../../2003/papers.css'
    """
    # TODO: fix the bug when relpath fails to work when command is invoked
    # from different directory 2023-08-10

    # wiki- DEB invok: md_opts=['--toc', '--quash-citations', '--style-csl', 'apa.csl', '-w', 'html', '--embed-resources']
    # markd INF proce: args.files = '['/Users/reagle/joseph/2023/aoc/advice-of-crowds.md']'
    # markd INF proce: in_file = '/Users/reagle/joseph/2023/aoc/advice-of-crowds.md'
    # markd INF proce: abs_fn = '/Users/reagle/joseph/2023/aoc/advice-of-crowds.md'
    # markd INF proce: base_fn = '/Users/reagle/joseph/2023/aoc/advice-of-crowds'
    # markd INF proce: fn_path = '/Users/reagle/joseph/2023/aoc'
    # markd INF make_: argument path_to='https://reagle.org/joseph/talks/_custom/fontawesome/css/all.min.css'
    # markd INF make_: realpath path_to='/Users/reagle/e/clear/data/2web/reagle.org/joseph/talks/_custom/fontawesome/css/all.min.css'
    # markd INF make_: path_from='/Users/reagle/joseph/2023/aoc' is a directory!
    # markd INF make_: final   path_from='/Users/reagle/e/clear/data/2web/reagle.org/joseph/2023/aoc'
    # markd INF make_: result='../../talks/_custom/fontawesome/css/all.min.css'
    # markd INF make_: argument path_to='https://reagle.org/joseph/2003/papers.css'
    # markd INF make_: realpath path_to='/Users/reagle/e/clear/data/2web/reagle.org/joseph/2003/papers.css'
    # markd INF make_: path_from='/Users/reagle/joseph/2023/aoc' is a directory!
    # markd INF make_: final   path_from='/Users/reagle/e/clear/data/2web/reagle.org/joseph/2023/aoc'
    # markd INF make_: result='../../2003/papers.css'
    # markd INF proce: generate temporary subset bib for speed
    # md2bi DEB get_k: filename = '/Users/reagle/joseph/2023/aoc/advice-of-crowds.md'

    info(f"argument {path_to=}")
    if path_to.startswith("http"):
        path_to = realpath(f"{WEBROOT}{urlparse(path_to).path}")
    info(f"realpath {path_to=}")

    if isfile(path_from):
        info(f"{path_from=} is a file, splitting!")
        path_from, _ = split(path_from)
    elif isdir(path_from):
        info(f"{path_from=} is a directory!")
    else:
        info(f"{path_from=} I don't know what path_from is")
    path_from = realpath(path_from)
    info(f"final   {path_from=}")

    result = relpath(path_to, path_from)
    info(f"{result=}")
    return result


def process(args):
    if args.bibliography:
        bib_fn = HOME + "/joseph/readings.yaml"
        bib_chunked = md2bib.chunk_yaml(open(bib_fn).readlines())
        debug("bib_chunked = %s" % (bib_chunked))

    info("args.files = '%s'" % args.files)
    for in_file in args.files:
        if not in_file:
            continue
        info("in_file = '%s'" % in_file)
        abs_fn = abspath(in_file)
        info("abs_fn = '%s'" % (abs_fn))

        base_fn, base_ext = splitext(abs_fn)
        info("base_fn = '%s'" % (base_fn))

        fn_path = os.path.split(abs_fn)[0]
        info("fn_path = '%s'" % (fn_path))

        ##############################
        # initial pandoc configuration based on arguments
        ##############################

        pandoc_inputs = []
        pandoc_opts = ["-w", args.write]
        # if args.write == 'markdown-citations':
        #     pandoc_opts.extend(['--csl=sage-harvard.csl',
        #         '--bibliography=/home/reagle/joseph/readings.yaml'])

        pandoc_opts.extend(
            [
                "--defaults",
                "base.yaml",  # include tab stop, lang, etc.
                "--standalone",
                "--lua-filter",
                "pandoc-quotes.lua",  # specify quote marks and lang
                "--strip-comments",
                "--wrap=auto",
                "--columns=120",
                "-c",
                make_relpath(
                    "https://reagle.org/joseph/talks/_custom/"
                    + "fontawesome/css/all.min.css",
                    fn_path,
                ),
            ]
        )

        # npm install --global mermaid-filter
        if args.mermaid:
            pandoc_opts.extend(
                [
                    "-F",
                    "mermaid-filter",  # creates png/svg
                    # "--lua-filter",  # does not work presently
                    # "mermaid-figure.lua",  # uses fig and figcaption
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
        elif args.write.startswith("html") and args.css:
            # ?DO NOT use relpath as this is a commandline argument?
            # pandoc_opts.extend(["-c", args.css])
            pandoc_opts.extend(["-c", make_relpath(args.css, fn_path)])

        elif args.write.startswith("docx"):
            pandoc_opts.extend(
                ["--reference-doc", HOME + "/.pandoc/reference-mit-press.docx"]
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
                pandoc_opts.extend(["--toc-depth=%s" % args.toc_depth[0]])
        if args.embed_resources:
            pandoc_opts.extend(["--embed-resources"])
        if args.divs:
            pandoc_opts.extend(["--section-divs"])
        if args.include_after_body:
            pandoc_opts.extend(["--include-after-body=%s" % args.include_after_body[0]])
        if args.lua_filter:
            pandoc_opts.extend(["--lua-filter", args.lua_filter[0]])
        if args.metadata:
            pandoc_opts.extend(["--metadata", args.metadata[0]])
        if args.style_chicago:
            args.style_csl = ["chicago-author-date.csl"]

        ##############################
        # pre pandoc
        ##############################

        bib_subset_tmp_fn = None  # fn of subset of main biblio
        fn_tmp_1 = f"{base_fn}-1{base_ext}"  # as read
        fn_tmp_2 = f"{base_fn}-2{base_ext}"  # pre-pandoc
        fn_tmp_3 = f"{base_fn}-3.{args.write}"  # post-pandoc copy
        fn_result = base_fn + "." + args.write
        cleanup_tmp_fns = [fn_tmp_1, fn_tmp_2, fn_tmp_3]

        pandoc_opts.extend(["-o", fn_result])
        pandoc_opts.extend(["--mathjax"])

        if args.style_csl:
            if args.bibtex:
                bib_fn = HOME + "/joseph/readings.bib"
                bib_ext = ".bib"
                parse_func = md2bib.parse_bibtex
                subset_func = md2bib.subset_bibtex
                emit_subset_func = md2bib.emit_bibtex_subset
            else:
                bib_fn = HOME + "/joseph/readings.yaml"
                bib_ext = ".yaml"
                parse_func = md2bib.chunk_yaml
                subset_func = md2bib.subset_yaml
                emit_subset_func = md2bib.emit_yaml_subset

            pandoc_opts.extend(["--csl=%s" % args.style_csl[0]])
            info("generate temporary subset bib for speed")
            bib_subset_tmp_fn = base_fn + bib_ext
            cleanup_tmp_fns.append(bib_subset_tmp_fn)
            keys = md2bib.get_keys_from_file(abs_fn)
            debug("keys = %s" % keys)
            if keys:
                entries = parse_func(open(bib_fn).readlines())
                subset = subset_func(entries, keys)
                emit_subset_func(subset, open(bib_subset_tmp_fn, "w"))
                pandoc_opts.extend(
                    [
                        "--bibliography=%s" % bib_subset_tmp_fn,
                    ]
                )
                pandoc_opts.extend(
                    [
                        "--citeproc",
                    ]
                )

        shutil.copyfile(abs_fn, fn_tmp_1)
        f1 = codecs.open(fn_tmp_1, "r", "UTF-8", "replace")
        content = f1.read()
        if content[0] == codecs.BOM_UTF8.decode("utf8"):
            content = content[1:]
        f2 = codecs.open(fn_tmp_2, "w", "UTF-8", "replace")

        # print(f"{abs_fn=}")

        lines = content.split("\n")
        new_lines = []

        for line in lines:
            # TODO: fix Wikicommons relative network-path references
            # so the URLs work on local file system (i.e.,'file:///')
            line = line.replace('src="//', 'src="http://')
            # TODO: encode ampersands in URLs
            line = process_commented_citations(line)
            if args.bibliography:  # create hypertext refs from bib db
                line = link_citations(line, bib_chunked)
                debug("\n** line is now %s" % line)
            if args.presentation:  # color some revealjs top of column slides
                if line.startswith("# ") and "{data-" not in line:
                    line = line.strip() + ' {data-background="LightBlue"}\n'
            debug("END line: '%s'" % line)
            new_lines.append(line)
        f1.close()
        f2.write("\n".join(new_lines))
        f2.close()

        ##############################
        # pandoc
        ##############################

        pandoc_cmd = [
            PANDOC_BIN,
            "-r",
            f"{args.read}",
        ]
        pandoc_cmd.extend(pandoc_opts)
        pandoc_inputs.insert(0, fn_tmp_2)
        pandoc_cmd.extend(pandoc_inputs)
        # print("joined pandoc_cmd: " + " ".join(pandoc_cmd) + "\n")
        call(pandoc_cmd)  # , stdout=open(fn_tmp_3, 'w')
        info("done pandoc_cmd")

        if args.presentation:
            create_talk_handout(abs_fn, fn_tmp_2)

        ##############################
        # post pandoc content
        ##############################

        if args.write == "html":
            # final tweaks html file
            shutil.copyfile(fn_result, fn_tmp_3)  # copy of html for debugging
            content_html = open(fn_tmp_3).read()
            if not content_html:
                raise ValueError("post-pandoc content_html is empty")

            # text alterations
            if args.british_quotes:  # swap double/single quotes
                content_html = content_html.replace('"', "&ldquo;").replace(
                    '"', "&rdquo;"
                )
                single_quote_re = re.compile(r"(\W)'(.{2,40}?)'(\W)")
                content_html = single_quote_re.sub(r'\1"\2"\3', content_html)
                content_html = content_html.replace("&ldquo;", r"'").replace(
                    "&rdquo;", "'"
                )
            # correct bibliography
            content_html = content_html.replace(" Vs. ", " vs. ")

            if args.presentation:
                # convert to data-src for lazy loading
                lazy_elements_re = re.compile(r"""(\<img|<iframe|<video)(.*?) src=""")
                content_html = lazy_elements_re.sub(r"\1\2 data-src=", content_html)

            # HTML alterations
            if args.number_elements:
                content_html = number_elements(content_html)

            result_fn = "%s.html" % (base_fn)
            info("result_fn = '%s'" % (result_fn))
            if args.output:
                result_fn = args.output[0]
            open(result_fn, "w").write(content_html)

            if args.validate:
                call(
                    [
                        "tidy",
                        "-utf8",
                        "-q",
                        "-i",
                        "-m",
                        "-w",
                        "0",
                        "-asxhtml",
                        result_fn,
                    ]
                )
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
        description="Markdown wrapper with slide and bibliographic options",
        #  formatter_class=argparse.RawTextHelpFormatter,
    )
    arg_parser.add_argument("files", nargs="+", metavar="FILE")
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
    arg_parser.add_argument("-o", "--output", nargs=1, help="output file path")
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
        "--mermaid",
        action="store_true",
        default=False,
        help="use mermaid filter",
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
        "--write",
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
        help="increase verbosity (specify multiple times for more)",
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
            filename="markdown-wrapper.log",
            filemode="w",
            level=log_level,
            format=LOG_FORMAT,
        )
    else:
        logging.basicConfig(level=log_level, format=LOG_FORMAT)
    if args.tests:
        import doctest

        doctest.testmod()
        sys.exit()
    process(args)
