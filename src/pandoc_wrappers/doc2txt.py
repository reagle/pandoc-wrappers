#! /usr/bin/env python3
"""Create plain text versions of documents using other tools such as text-based browsers and pandoc."""

__author__ = "Joseph Reagle"
__copyright__ = "Copyright (C) 2009-2025 Joseph Reagle"
__license__ = "GLPv3"
__version__ = "1.0"

import argparse
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
VISUAL = os.environ.get("VISUAL")
if not all([HOME, VISUAL, PANDOC_BIN]):
    raise FileNotFoundError("Your environment is not configured correctly")


def rotate_files(file_path: Path | str, max_rot: int = 5) -> None:
    """Create at most {max_rot} rotating files.

    >>> rotate_files(Path("/tmp/test.txt"), 3)  # Creates /tmp/test1.txt if test.txt exists
    """
    path = Path(file_path)
    bare = path.parent / path.stem
    ext = path.suffix

    for counter in reversed(range(2, max_rot + 1)):
        old_file = Path(f"{bare}{counter - 1}{ext}")
        new_file = Path(f"{bare}{counter}{ext}")
        if old_file.exists():
            old_file.rename(new_file)

    if path.exists():
        path.rename(f"{bare}1{ext}")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments and return namespace."""
    arg_parser = argparse.ArgumentParser(
        description=(
            "Create plain text versions of documents using other tools such as text-based browsers and pandoc."
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

    return arg_parser.parse_args()


def setup_logging(args: argparse.Namespace) -> None:
    """Configure logging based on command line arguments."""
    SCRIPT_STEM = Path(__file__).stem
    # LOG_FORMAT https://loguru.readthedocs.io/en/stable/api/logger.html#record
    log_level = log.ERROR - (args.verbose * 10)
    LOG_FORMAT = "%(levelname).4s %(funcName).10s:%(lineno)-4d| %(message)s"
    log_config = {"level": log_level, "format": LOG_FORMAT}
    if args.log_to_file:
        log_config.update({"filename": f"{SCRIPT_STEM}.log", "filemode": "w"})
        print(f"Logging to file: {SCRIPT_STEM}.log")
    log.basicConfig(**log_config)
    log.info(args)


def process_input(input_arg: str) -> tuple[str, Path, str]:
    """Process input argument and return URL, destination file, and extension."""
    if input_arg.startswith("http"):
        url = input_arg
        if "docs.google.com" in url:
            url = url.replace("/edit", "/export")
        dst_file = TMP_DIR / "dt-result.txt"
        extension = "html"
    elif (file_path := Path(input_arg)).exists():
        log.info(f"path = {file_path}")
        url = f"file://{file_path.resolve()}"
        extension = file_path.suffix[1:]
        dst_file = file_path.with_suffix(".txt")
    else:
        raise FileNotFoundError(f"Cannot find {input_arg}")

    log.info(f"** dst_file = {dst_file}")
    log.info(f"** extension = {extension}")
    log.info(f"** url = {url}")

    return url, dst_file, extension


def get_command(
    args: argparse.Namespace, url: str, dst_file: Path, extension: str, input_arg: str
) -> tuple[list[str], bytes | None, str]:
    """Generate command for document conversion based on arguments."""
    content = None
    wrap_option = ""

    # default is lynx if no conversion option specified
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

    # Normalize extension
    extension = "markdown" if extension == "md" else extension
    extension = extension if extension else "html"
    log.info(f"** extension = {extension}")

    # Configure command based on selected conversion options
    if args.markdown:
        content = urlopen(url).read()
        wrap_option = "" if args.wrap else "--wrap=none"
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
            str(dst_file),
        ]
    elif args.plain:
        content = urlopen(url).read()
        wrap_option = "" if args.wrap else "--wrap=none"
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
            str(dst_file),
        ]
    elif args.lynx:
        wrap_option = "-width 70" if args.wrap else "-width 1024"
        command = ["lynx", "-dump", "-nonumbers", "-display_charset=utf-8", url]
    elif args.links:
        wrap_option = "-width 70" if args.wrap else "-width 512"
        command = ["links", "-dump", url]
    elif args.w3m:
        wrap_option = "-cols 70" if args.wrap else ""
        command = ["w3m", "-dump", "-cols", "70", url]
    elif args.antiword:
        wrap_option = "-w 70" if args.wrap else "-w 0"
        url_no_prefix = url[7:]  # remove 'file://'
        command = ["antiword", url_no_prefix]
    elif args.docx2txt:
        wrap_option = ""  # maybe use fold instead?
        command = ["docx2txt.pl", input_arg, "-"]
    elif args.pdftotext:
        wrap_option = ""
        command = ["pdftotext", "-layout", "-nopgbrk", input_arg, "-"]
    else:
        raise TypeError("Error: No conversion specified.")

    # Insert wrap options after command
    if wrap_option:
        command[1:1] = wrap_option.split()

    return command, content, wrap_option


def post_process(
    args: argparse.Namespace, dst_file: Path, wrap_option: str = ""
) -> None:
    """Apply additional text transformations if needed."""
    if not (args.wrap or args.quote):
        return

    with dst_file.open() as f:
        new_content = []
        for line in f.readlines():
            # Replace whitespace-only lines with newlines
            line = "\n" if line.isspace() else line

            # Apply wrapping if needed and no native wrapping available
            if args.wrap and not wrap_option:  # wrap if no native wrap
                log.info("wrapping")
                line = textwrap.fill(line, 70).strip() + "\n"

            # Add quote marks if requested
            if args.quote:
                log.info("quoting")
                line = line.replace("\n", "\n> ")

            new_content.append(line)

        content = "".join(new_content)

        # Add initial quote mark if quoting
        if args.quote:
            content = "> " + content

    with dst_file.open("w") as f:
        f.write(content)


def main(args: argparse.Namespace | None = None) -> None:
    """Execute the main document transformation workflow."""
    if args is None:
        args = parse_arguments()

    setup_logging(args)

    input_arg = args.input_arg[0]
    log.info(f"** input_fp = {input_arg}")

    url, dst_file, extension = process_input(input_arg)

    rotate_files(dst_file)

    command, content, wrap_option = get_command(
        args, url, dst_file, extension, input_arg
    )

    print(f"** command = {command} on {url}")

    # Use context manager for file operations
    with dst_file.open("w") as output_file:
        process = Popen(command, stdin=PIPE, stdout=output_file)
        process.communicate(input=content)

    post_process(args, dst_file, wrap_option)

    # Set permissions and open in editor
    dst_file.chmod(0o600)
    if VISUAL is not None:  # Ensure VISUAL is not None before using it
        call([VISUAL, str(dst_file)])
    else:
        log.warning("VISUAL environment variable is None, skipping opening editor")


if __name__ == "__main__":
    main()
