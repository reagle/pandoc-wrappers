#! /usr/bin/env python3
"""Document transformation wrapper."""

import logging as log
import os
import shutil
import textwrap
from pathlib import Path  # https://docs.python.org/3/library/pathlib.html
from subprocess import PIPE, Popen, call
from urllib.request import urlopen

HOME = Path.home()
TMP_DIR = Path(HOME) / "tmp" / ".pw"
TMP_DIR.mkdir(parents=True, exist_ok=True)
PANDOC_BIN = shutil.which("pandoc")
VISUAL = os.environ["VISUAL"]
if not all([HOME, VISUAL, PANDOC_BIN]):
    raise FileNotFoundError("Your environment is not configured correctly")


def rotate_files(file_path: Path | str, max_rot: int = 5) -> None:
    """Create at most {max_rot} rotating files."""
    path = Path(file_path)
    bare = path.parent / path.stem
    ext = path.suffix

    for counter in reversed(range(2, max_rot + 1)):
        old_file = Path(f"{bare}{counter-1}{ext}")
        new_file = Path(f"{bare}{counter}{ext}")
        if old_file.exists():
            old_file.rename(new_file)

    if path.exists():
        path.rename(f"{bare}1{ext}")


if __name__ == "__main__":
    import argparse  # http://docs.python.org/dev/library/argparse.html

    arg_parser = argparse.ArgumentParser(
        description=(
            "Document transformation wrapper which (by default) converts HTML to text"
        )
    )
    arg_parser.add_argument("input_arg", nargs=1, metavar="URL or FILE")
    arg_parser.add_argument(
        "-m",
        "--markdown",
        action="store_true",
        default=False,
        help="file2mdn via pandoc (quite busy with links)",
    )
    arg_parser.add_argument(
        "-p",
        "--plain",
        action="store_true",
        default=False,
        help="file2txt via pandoc",
    )
    arg_parser.add_argument(
        "-y",
        "--lynx",
        action="store_true",
        default=False,
        help="html2txt via lynx (nice formatting)",
    )
    arg_parser.add_argument(
        "-i",
        "--links",
        action="store_true",
        default=False,
        help="html2txt via links",
    )
    arg_parser.add_argument(
        "-3",
        "--w3m",
        action="store_true",
        default=False,
        help="html2txt via w3m",
    )
    arg_parser.add_argument(
        "-a",
        "--antiword",
        action="store_true",
        default=False,
        help="doc2txt  via antiword",
    )
    arg_parser.add_argument(
        "-d",
        "--docx2txt",
        action="store_true",
        default=False,
        help="docx2txt via docx2txt",
    )
    arg_parser.add_argument(
        "-t",
        "--pdftotext",
        action="store_true",
        default=False,
        help="pdf2txt via pdftotext",
    )
    arg_parser.add_argument(
        "-w", "--wrap", action="store_true", default=False, help="wrap text"
    )
    arg_parser.add_argument(
        "-q",
        "--quote",
        action="store_true",
        default=False,
        help="prepend '>' quote marks to lines",
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
    arg_parser.add_argument("--version", action="version", version="TBD")

    args = arg_parser.parse_args()

    log_level = (log.CRITICAL) - (args.verbose * 10)
    LOG_FORMAT = "%(levelname).4s %(funcName).10s:%(lineno)-4d| %(message)s"
    if args.log_to_file:
        print("logging to file")
        log.basicConfig(
            filename="markdown-wrapper.log",
            filemode="w",
            level=log_level,
            format=LOG_FORMAT,
        )
    else:
        log.basicConfig(level=log_level, format=LOG_FORMAT)
    log.info(args)

    input_arg = args.input_arg[0]
    log.info(f"** input_fp = {input_arg}")

    if input_arg.startswith("http"):
        url = input_arg
        if "docs.google.com" in url:
            url = url.replace("/edit", "/export")
        dst_file = TMP_DIR / "dt-result.txt"
        extension = "html"
    elif Path(input_arg).exists():
        file_path = Path(input_arg).resolve()
        log.info(f"path = {file_path}")
        url = f"file://{file_path}"
        extension = file_path.suffix[1:]
        dst_file = file_path.with_suffix(".txt")
    else:
        raise FileNotFoundError(f"Cannot find {input_arg}")

    log.info(f"** dst_file = {dst_file}")
    log.info(f"** extension = {extension}")
    log.info(f"** url = {url}")

    content = None
    rotate_files(dst_file)

    # default is lynx; args.catdoc now removed
    if not any(
        (
            args.lynx,
            args.plain,
            args.markdown,
            args.links,
            args.w3m,
            args.antiword,
            args.docx2txt,
            args.pdftotext,
        )
    ):
        args.lynx = True

    if extension == "md":
        extension = "markdown"
    extension = "html" if not extension else extension
    log.info(f"** extension = {extension}")

    # I prefer to use the programs native wrap if possible
    if args.markdown:
        content = urlopen(url).read()
        wrap = "" if args.wrap else "--wrap=none"
        columns = 70
        command = [
            PANDOC_BIN,
            "-f",
            f"{extension}",
            "-t",
            "markdown-simple_tables-pipe_tables-multiline_tables",
            "--reference-links",
            "--reference-location=block",
            "--columns",
            f"{columns}",
            "-o",
            dst_file,
        ]
    elif args.plain:
        content = urlopen(url).read()
        wrap = "" if args.wrap else "--wrap=none"
        columns = 70
        command = [
            PANDOC_BIN,
            "-f",
            f"{extension}",
            "-t",
            "plain",
            "--columns",
            f"{columns}",
            "-o",
            dst_file,
        ]
    elif args.lynx:
        wrap = "-width 70" if args.wrap else "-width 1024"
        command = [
            "lynx",
            "-dump",
            "-nonumbers",
            "-display_charset=utf-8",
            url,
        ]
    elif args.links:
        wrap = "-width 70" if args.wrap else "-width 512"
        command = ["links", "-dump", url]
    elif args.w3m:
        wrap = "-cols 70" if args.wrap else ""
        command = ["w3m", "-dump", "-cols", "70", url]
    elif args.antiword:
        wrap = "-w 70" if args.wrap else "-w 0"
        url = url[7:]  # remove 'file://'
        command = ["antiword", url]
    elif args.docx2txt:
        wrap = ""  # maybe use fold instead?
        command = ["docx2txt.pl", input_arg, "-"]
    elif args.pdftotext:
        wrap = ""
        command = ["pdftotext", "-layout", "-nopgbrk", input_arg, "-"]
    else:
        raise TypeError("Error: No conversion specified.")

    command[1:1] = wrap.split()  # insert wrap args after command
    print(f"** command = {command} on {url}")
    process = Popen(command, stdin=PIPE, stdout=open(dst_file, "w"))
    process.communicate(input=content)

    if args.wrap or args.quote:
        with open(dst_file) as f:
            new_content = []
            for line in f.readlines():
                if line.isspace():
                    line = "\n"
                if args.wrap and wrap == "":  # wrap if no native wrap
                    log.info("wrapping")
                    line = textwrap.fill(line, 70).strip() + "\n"
                if args.quote:
                    log.info("quoting")
                    line = line.replace("\n", "\n> ")
                new_content.append(line)
            content = "".join(new_content)
            if args.quote:
                content = "> " + content
        with open(dst_file, "w") as f:
            f.write(content)

    os.chmod(dst_file, 0o600)
    call([VISUAL, dst_file])
