#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pyyaml",
# ]
# ///

"""Merge multiple markdown chapters with metadata into a single file.

This script combines a book metadata YAML file with multiple chapter
markdown files, stripping individual YAML headers and converting titles
to chapter headings. Optionally adds page breaks between chapters.
"""

import argparse
import sys
from pathlib import Path

import yaml


def extract_title_from_yaml(yaml_content: str) -> str | None:
    """Extract title from YAML header content."""
    try:
        data = yaml.safe_load(yaml_content)
        return data.get("title") if data else None
    except yaml.YAMLError:
        # Fallback to simple string parsing if YAML parsing fails
        for line in yaml_content.split("\n"):
            if line.strip().startswith("title:"):
                title = line.split("title:", 1)[1].strip()
                # Remove quotes if present
                return title.strip("\"'")
    return None


def process_chapter(
    chapter_path: Path, chapter_num: int, add_page_break: bool, output_format: str
) -> str:
    """Process a single chapter file.

    Extracts title from YAML header if present, converts to heading,
    and optionally adds page break before chapter.
    """
    if not chapter_path.exists():
        print(f"Warning: Chapter file not found: {chapter_path}", file=sys.stderr)
        return ""

    content = chapter_path.read_text(encoding="utf-8")
    output_parts = []

    # Add page break before chapter (except first)
    if chapter_num > 0 and add_page_break:
        page_break = {
            "docx": "\\newpage",
            "latex": "\\newpage",
            "html": '<div style="page-break-before: always;"></div>',
            "markdown": "\\newpage",  # Pandoc will handle this
        }.get(output_format, "\\newpage")
        output_parts.append(f"{page_break}\n\n")

    # Process YAML header if present
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            yaml_section = parts[1]
            body_content = parts[2].lstrip()

            # Extract and convert title to heading
            title = extract_title_from_yaml(yaml_section)
            if title:
                output_parts.append(f"# {title}\n\n")

            output_parts.append(body_content)
        else:
            # Malformed YAML block, include as-is
            output_parts.append(content)
    else:
        # No YAML header, include content as-is
        # Check if first line might be a title that needs converting
        lines = content.split("\n", 1)
        if lines and not lines[0].startswith("#"):
            # If first line isn't already a heading, make it one
            # This is optional behavior - remove if not desired
            pass
        output_parts.append(content)

    # Ensure chapter ends with newlines for separation
    output_parts.append("\n\n")

    return "".join(output_parts)


def merge_chapters(
    metadata_file: Path | None,
    chapter_files: list[Path],
    output_file: Path,
    page_breaks: bool = False,
    output_format: str = "markdown",
) -> None:
    """Merge metadata and chapters into single markdown file."""
    metadata_used = False  # Track if metadata was actually used

    with output_file.open("w", encoding="utf-8") as out:
        # Write metadata if provided
        if metadata_file and metadata_file.exists():
            metadata_content = metadata_file.read_text(encoding="utf-8")

            # Ensure metadata is properly formatted with YAML delimiters
            if not metadata_content.startswith("---"):
                out.write("---\n")
            out.write(metadata_content)
            if not metadata_content.rstrip().endswith("---"):
                if not metadata_content.endswith("\n"):
                    out.write("\n")
                out.write("---\n")
            out.write("\n\n")  # Separate metadata from content
            metadata_used = True  # Set flag when metadata is actually used
        elif metadata_file:
            print(
                f"Warning: Metadata file not found: {metadata_file}",
                file=sys.stderr,
            )

        # Process each chapter
        for i, chapter_path in enumerate(chapter_files):
            chapter_content = process_chapter(
                chapter_path,
                chapter_num=i,
                add_page_break=page_breaks,
                output_format=output_format,
            )
            out.write(chapter_content)

    # Only report metadata if it was actually used
    print(f"Successfully merged {len(chapter_files)} chapters into {output_file}")
    if metadata_used:
        print(f"  with metadata from: {metadata_file}")


def process_args(argv: list[str]) -> argparse.Namespace:
    """Process command line arguments."""
    parser = argparse.ArgumentParser(
        description="Merge multiple markdown chapters with optional metadata into a single file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Chapters only, no metadata
  %(prog)s -c chapter1.md chapter2.md chapter3.md -o combined.md

  # Merge with metadata and with page breaks for docx output
  %(prog)s -m _book-metadata.yaml -c intro.md ch1.md ch2.md -o book.md  -p -f docx

  # Using stdin for chapter list
  find . -name "ch*.md" | sort | xargs %(prog)s -c -o book.md
        """,
    )

    parser.add_argument(
        "-m",
        "--metadata",
        type=Path,
        default="_book-metadata.yaml",
        help="Path to book metadata YAML file",
    )

    parser.add_argument(
        "-c",
        "--chapters",
        nargs="+",
        type=Path,
        required=True,
        help="Ordered list of chapter markdown files",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output file path for merged content",
    )

    parser.add_argument(
        "-p",
        "--page-breaks",
        action="store_true",
        help="Add page breaks between chapters",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "html", "docx", "latex"],
        default="markdown",
        help="Output format for page break syntax (default: markdown)",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    parser.add_argument("--version", action="version", version="%(prog)s 1.0")

    return parser.parse_args(argv)


def main() -> int:
    """Exnter main."""
    try:
        args = process_args(sys.argv[1:])

        if args.verbose:
            print(f"Metadata file: {args.metadata}")
            print(f"Chapter files: {', '.join(str(c) for c in args.chapters)}")
            print(f"Output file: {args.output}")
            print(f"Page breaks: {args.page_breaks}")
            print(f"Format: {args.format}")

        # Validate chapter files exist
        missing_chapters = [c for c in args.chapters if not c.exists()]
        if missing_chapters:
            print("Error: Missing chapter files:", file=sys.stderr)
            for chapter in missing_chapters:
                print(f"  - {chapter}", file=sys.stderr)
            return 1

        # Perform the merge
        merge_chapters(
            metadata_file=args.metadata,
            chapter_files=args.chapters,
            output_file=args.output,
            page_breaks=args.page_breaks,
            output_format=args.format,
        )

        return 0

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
