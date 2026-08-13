"""Shared utilities for Obsidian vault processing.

Provides vault copying, wikilink conversion, and mtime-based build checking
used by both wiki_update (gardens) and pelican_build (blogs).

Test with:

uv run --with pytest pytest --doctest-modules src/pandoc_wrappers/obsidian_utils.py -v

"""

__author__ = "Joseph Reagle"
__copyright__ = "Copyright (C) 2009-2025 Joseph Reagle"
__license__ = "GLPv3"
__version__ = "1.0"

import logging
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# Wikilinks: [[target]] or [[target|display]] or ![[image.png]]
WIKILINK_RE = re.compile(
    r"""
    (!?)            # Group 1: Optional embed flag '!' (e.g., for images)
    \[\[            # Literal opening brackets '[['
    (               # Group 2: The link target (note name or filename)
      [^\]|]+       #   Match 1+ characters that are NOT ']' or '|'
    )
    (?:             # Non-capturing group for optional alias
      \|            #   Literal pipe separator '|'
      (             #   Group 3: The display text (alias)
        [^\]]+      #     Match 1+ characters that are NOT ']'
      )
    )?              # The alias group is optional
    \]\]            # Literal closing brackets ']]'
    """,
    re.VERBOSE,
)

# The target of any markdown link or image: the `](...)` portion
LINK_TARGET_RE = re.compile(r"\]\((?P<target>[^)\s]+)\)")

# Standard markdown links: [text](url)
MD_LINK_RE = re.compile(
    r"""
    \[              # Literal opening bracket '['
    (               # Group 1: Link text
      [^\]]+        #   Match 1+ characters that are NOT ']'
    )
    \]              # Literal closing bracket ']'
    \(              # Literal opening parenthesis '('
    (               # Group 2: URL or relative path
      [^)]+         #   Match 1+ characters that are NOT ')'
    )
    \)              # Literal closing parenthesis ')'
    """,
    re.VERBOSE,
)


# ─── mtime check ───────────────────────────────────────────────────────


def needs_build(
    source: Path,
    sentinel: Path,
    glob: str = "**/*.md",
) -> Path | None:
    """Return the first source file newer than sentinel, or None.

    The sentinel is an output file whose mtime represents "last build time".
    If any source file is newer than the sentinel, a rebuild is needed.
    Each site type picks its own sentinel via get_sentinel():
      - garden: newest .html in the export dir
      - blog: the Pelican index.html

    >>> import tempfile, time
    >>> with tempfile.TemporaryDirectory() as d:
    ...     src = Path(d) / "src"; src.mkdir()
    ...     sent = Path(d) / "out.html"
    ...     bool(needs_build(src, sent))  # no sentinel
    True
    >>> with tempfile.TemporaryDirectory() as d:
    ...     src = Path(d) / "src"; src.mkdir()
    ...     sent = Path(d) / "out.html"; sent.touch()
    ...     needs_build(src, sent) is None  # no source files
    True
    """
    if not sentinel.exists():
        return source  # sentinel missing, return source as trigger
    sentinel_mtime = sentinel.stat().st_mtime
    for f in source.rglob(glob):
        if f.stat().st_mtime > sentinel_mtime:
            return f
    return None


# ─── directory operations ──────────────────────────────────────────────


def clear_directory(dir_path: Path) -> None:
    """Remove and recreate a directory."""
    if dir_path.exists():
        log.info(f"Removing {dir_path}")
        shutil.rmtree(dir_path)
    log.info(f"Creating {dir_path}")
    dir_path.mkdir(parents=True)


def copy_vault(vault: Path, export_dir: Path) -> None:
    """Copy vault to export directory, excluding hidden files and Obsidian config."""
    log.info(f"Copying {vault} to {export_dir}")

    for src_path in vault.rglob("*"):
        if any(part.startswith(".") for part in src_path.parts):
            continue
        if src_path.is_symlink():
            continue  # e.g. the photo gallery: linked for Obsidian, not published here

        rel_path = src_path.relative_to(vault)
        dest_path = export_dir / rel_path

        if src_path.is_dir():
            dest_path.mkdir(parents=True, exist_ok=True)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)


def remove_empty_or_hidden_folders(path: Path, hide_prefix: str = "_") -> bool:
    """Remove empty or hidden folders in path.

    Pandoc chokes on Obsidian template files, so remove.
    """

    def is_empty(folder: Path) -> bool:
        return not any(folder.iterdir())

    log.info(f"check for empty or hidden folders {path=}")
    did_remove = False
    folders = sorted(path.rglob("**/"))
    for folder in folders:
        if is_empty(folder) or folder.name.startswith(hide_prefix):
            shutil.rmtree(folder)
            did_remove = True
            log.info(f"  Removed folder: {folder}")
    return did_remove


# ─── note index ────────────────────────────────────────────────────────


def build_note_index(export_dir: Path) -> dict[str, Path]:
    """Build index mapping note names (without extension) to their paths.

    Obsidian allows linking by filename alone, so we need this index
    to resolve wikilinks to actual file paths.
    """
    index: dict[str, Path] = {}

    for md_file in export_dir.rglob("*.md"):
        if md_file.name.startswith("_"):
            continue

        key = md_file.stem.lower()
        if key in index:
            log.warning(f"Duplicate note name: {md_file.stem}")
        index[key] = md_file

    log.info(f"Indexed {len(index)} notes")
    return index


# ─── wikilink helpers ──────────────────────────────────────────────────


def parse_wikilink_target(target: str) -> tuple[str, str]:
    """Parse a wikilink target into (note_name, anchor).

    >>> parse_wikilink_target("my-note")
    ('my-note', '')
    >>> parse_wikilink_target("my-note#section")
    ('my-note', '#section')
    >>> parse_wikilink_target("my-note#Section Title")
    ('my-note', '#section-title')
    >>> parse_wikilink_target("#just-anchor")
    ('', '#just-anchor')
    >>> parse_wikilink_target("  spaced  ")
    ('spaced', '')
    """
    anchor = ""
    if "#" in target:
        target, heading = target.split("#", 1)
        anchor = "#" + heading.lower().replace(" ", "-")
    return target.strip(), anchor


def note_path_to_url(rel_path: Path, base_url: str) -> str:
    """Convert a note's relative path to its URL.

    Lowercases the filename stem to match Pelican's `SLUGIFY_SOURCE =
    "basename"` setting, which always lowercases the slug regardless of
    the source file's own case.

    >>> note_path_to_url(Path("2023/my-note.md"), "https://example.com/blog")
    'https://example.com/blog/2023/my-note.html'
    >>> note_path_to_url(Path("note.md"), "https://example.com")
    'https://example.com/note.html'
    >>> note_path_to_url(Path("2026/Student-AI-Use.md"), "https://example.com")
    'https://example.com/2026/student-ai-use.html'
    """
    lowered = rel_path.with_name(rel_path.stem.lower() + rel_path.suffix)
    url_path = str(lowered).removesuffix(".md") + ".html"
    return f"{base_url}/{url_path}"


def resolve_wikilink(
    target: str,
    source_file: Path,
    export_dir: Path,
    note_index: dict[str, Path],
    base_url: str,
) -> str | None:
    """Resolve a wikilink target to an absolute URL path (for blogs)."""
    target, anchor = parse_wikilink_target(target)

    if not target:
        return anchor if anchor else None

    target_lower = target.lower()

    if target_lower in note_index:
        target_path = note_index[target_lower]
        rel_path = target_path.relative_to(export_dir)
        return note_path_to_url(rel_path, base_url) + anchor

    potential_path = source_file.parent / f"{target}.md"
    if potential_path.exists():
        rel_path = potential_path.relative_to(export_dir)
        return note_path_to_url(rel_path, base_url) + anchor

    log.debug(f"Could not resolve wikilink: {target}")
    return None


def resolve_wikilink_relative(
    target: str,
    source_file: Path,
    note_index: dict[str, Path],
) -> str | None:
    """Resolve a wikilink target to a relative .html path (for gardens).

    Returns a path relative to source_file's directory.
    """
    target, anchor = parse_wikilink_target(target)

    if not target:
        return anchor if anchor else None

    target_lower = target.lower()
    target_path = None

    if target_lower in note_index:
        target_path = note_index[target_lower]
    else:
        potential_path = source_file.parent / f"{target}.md"
        if potential_path.exists():
            target_path = potential_path

    if target_path:
        html_path = target_path.with_suffix(".html")
        rel = os.path.relpath(html_path, source_file.parent)
        return rel + anchor

    log.debug(f"Could not resolve wikilink: {target}")
    return None


def is_image_file(filename: str) -> bool:
    """Check if filename has an image extension.

    >>> is_image_file("photo.jpg")
    True
    >>> is_image_file("PHOTO.PNG")
    True
    >>> is_image_file("document.pdf")
    False
    >>> is_image_file("image.jpeg")
    True
    """
    return filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))


def format_md_link(display: str, url: str) -> str:
    """Format a standard markdown link.

    >>> format_md_link("click here", "https://example.com")
    '[click here](https://example.com)'
    """
    return f"[{display}]({url})"


def format_md_image(alt: str, src: str) -> str:
    """Format a markdown image.

    >>> format_md_image("my photo", "image.jpg")
    '![my photo](image.jpg)'
    """
    return f"![{alt}]({src})"


# ─── photo path conversion ────────────────────────────────────────────


def photo_src_to_url(src: str, photo_dir: str, photo_url: str) -> str | None:
    """Map a vault-relative photo path to its hosted URL, or None if not one.

    The vault holds a symlink (photo_dir) to the photo gallery so that
    Obsidian renders embeds locally; published pages need the hosted URL.

    >>> URL = "https://goatee.net/photo/gallery"
    >>> photo_src_to_url("../photo/2026/08/train.jpg", "photo", URL)
    'https://goatee.net/photo/gallery/2026/08/train.jpg'
    >>> photo_src_to_url("photo/2026/08/train.jpg", "photo", URL)
    'https://goatee.net/photo/gallery/2026/08/train.jpg'
    >>> photo_src_to_url("https://example.com/train.jpg", "photo", URL) is None
    True
    >>> photo_src_to_url("../attachments/diagram.png", "photo", URL) is None
    True
    """
    if urlparse(src).scheme:
        return None
    parts = [part for part in PurePosixPath(src).parts if part not in ("..", ".", "/")]
    if len(parts) < 2 or parts[0] != photo_dir:
        return None
    return f"{photo_url.rstrip('/')}/{'/'.join(parts[1:])}"


def build_photo_index(photo_root: Path, photo_dir: str) -> dict[str, str]:
    """Map image filenames to vault paths, so `![[photo.jpg]]` embeds resolve.

    Obsidian's picker inserts an embed by filename alone ("shortest"
    link format). Resolving to a vault path lets convert_photo_paths do
    the URL rewriting for both syntaxes. Thumbnails are skipped so a name
    shared with its thumb resolves to the full-size image.
    """
    index: dict[str, str] = {}
    for path in photo_root.rglob("*"):
        if "thumbs" in path.parts or not is_image_file(path.name):
            continue
        rel = path.relative_to(photo_root).as_posix()
        index[path.name.lower()] = f"{photo_dir}/{rel}"
    log.info(f"Indexed {len(index)} photos under {photo_root}")
    return index


def convert_photo_paths(content: str, photo_dir: str, photo_url: str) -> str:
    """Rewrite vault-relative photo paths to hosted URLs.

    Applies to both image sources and link targets, so an image wrapped
    in a link to its gallery works. Anything else is left alone.

    >>> URL = "https://goatee.net/photo/gallery"
    >>> convert_photo_paths("![train](../photo/2026/08/t.jpg)", "photo", URL)
    '![train](https://goatee.net/photo/gallery/2026/08/t.jpg)'
    >>> convert_photo_paths("[gallery](../photo/2026/index.html)", "photo", URL)
    '[gallery](https://goatee.net/photo/gallery/2026/index.html)'
    >>> convert_photo_paths("![x](https://elsewhere.net/x.jpg)", "photo", URL)
    '![x](https://elsewhere.net/x.jpg)'
    """

    def replace_target(match: re.Match) -> str:
        url = photo_src_to_url(match.group("target"), photo_dir, photo_url)
        return f"]({url})" if url else match.group(0)

    return LINK_TARGET_RE.sub(replace_target, content)


# ─── wikilink conversion ──────────────────────────────────────────────


def convert_wikilinks(
    content: str,
    source_file: Path,
    export_dir: Path,
    note_index: dict[str, Path],
    base_url: str,
    *,
    photo_index: dict[str, str] | None = None,
) -> str:
    """Convert Obsidian wikilinks to absolute-URL markdown links (for blogs).

    A photo_index resolves image embeds inserted by filename alone to a
    vault path; convert_photo_paths then makes it a URL.
    """

    def replace_wikilink(match: re.Match) -> str:
        embed, target, display = match.groups()
        display = display or target.split("#")[0]

        if embed == "!":
            if is_image_file(target):
                path = (photo_index or {}).get(target.lower())
                return format_md_image(display, path if path else target)
            url = resolve_wikilink(
                target, source_file, export_dir, note_index, base_url
            )
            return format_md_link(display, url) if url else match.group(0)

        url = resolve_wikilink(target, source_file, export_dir, note_index, base_url)
        return format_md_link(display, url) if url else match.group(0)

    return WIKILINK_RE.sub(replace_wikilink, content)


def convert_wikilinks_relative(
    content: str,
    source_file: Path,
    note_index: dict[str, Path],
) -> str:
    """Convert Obsidian wikilinks to relative .html markdown links (for gardens)."""

    def replace_wikilink(match: re.Match) -> str:
        embed, target, display = match.groups()
        display = display or target.split("#")[0]

        if embed == "!":
            if is_image_file(target):
                return format_md_image(display, target)
            url = resolve_wikilink_relative(
                target, source_file, note_index
            )
            return format_md_link(display, url) if url else match.group(0)

        url = resolve_wikilink_relative(
            target, source_file, note_index
        )
        return format_md_link(display, url) if url else match.group(0)

    return WIKILINK_RE.sub(replace_wikilink, content)


# ─── relative link conversion ─────────────────────────────────────────


def resolve_link(path_str: str, source_file: Path, export_dir: Path) -> Path | None:
    """Resolve a relative path string to a path within the export folder."""
    try:
        link_path = (source_file.parent / path_str).resolve()
        return link_path.relative_to(export_dir.resolve())
    except ValueError:
        return None


def is_internal_md_link(path: str) -> bool:
    """Check if path is an internal markdown link (relative, ends with .md).

    >>> is_internal_md_link("other.md")
    True
    >>> is_internal_md_link("/absolute/path.md")
    False
    >>> is_internal_md_link("style.css")
    False
    >>> is_internal_md_link("")
    False
    >>> is_internal_md_link("subdir/note.md")
    True
    """
    return bool(path) and not path.startswith("/") and path.endswith(".md")


def convert_relative_links(
    content: str, base_url: str, source_file: Path, export_dir: Path
) -> str:
    """Convert relative markdown links to full URLs."""

    def replace_link(match: re.Match) -> str:
        text, raw_url = match.groups()
        parsed = urlparse(raw_url)

        if parsed.scheme in ("http", "https"):
            if not raw_url.startswith(base_url):
                return match.group(0)
            path_part = raw_url.removeprefix(base_url).lstrip("/")
        else:
            path_part = parsed.path

        if not is_internal_md_link(path_part):
            return match.group(0)

        if not (relative_path := resolve_link(path_part, source_file, export_dir)):
            return match.group(0)

        url = note_path_to_url(relative_path, base_url)
        anchor = "#" + parsed.fragment if parsed.fragment else ""
        return format_md_link(text, url + anchor)

    return MD_LINK_RE.sub(replace_link, content)


# ─── batch processing ─────────────────────────────────────────────────


def process_blog_files(
    export_dir: Path,
    base_url: str,
    note_index: dict[str, Path],
    *,
    photo_dir: str | None = None,
    photo_url: str | None = None,
    photo_index: dict[str, str] | None = None,
) -> int:
    """Process all markdown files for blogs: wikilinks to absolute URLs.

    When photo_dir and photo_url are given, vault-relative photo paths
    are also rewritten to hosted URLs, as are `![[photo.jpg]]` embeds
    found in photo_index.
    """
    log.info(f"Processing blog files with base URL {base_url}")
    modified_count = 0

    for md_file in export_dir.rglob("*.md"):
        if md_file.name.startswith("_"):
            continue

        content = md_file.read_text(encoding="utf-8")
        original = content

        content = convert_wikilinks(
            content, md_file, export_dir, note_index, base_url, photo_index=photo_index
        )
        content = convert_relative_links(content, base_url, md_file, export_dir)
        if photo_dir and photo_url:
            content = convert_photo_paths(content, photo_dir, photo_url)

        if content != original:
            md_file.write_text(content, encoding="utf-8")
            log.debug(f"Modified: {md_file.name}")
            modified_count += 1

    log.info(f"Converted {modified_count} files")
    return modified_count


def process_garden_files(export_dir: Path, note_index: dict[str, Path]) -> int:
    """Process all markdown files for gardens: wikilinks to relative .html paths."""
    log.info(f"Processing garden files in {export_dir}")
    modified_count = 0

    for md_file in export_dir.rglob("*.md"):
        if md_file.name.startswith("_"):
            continue

        content = md_file.read_text(encoding="utf-8")
        original = content

        content = convert_wikilinks_relative(content, md_file, note_index)

        if content != original:
            md_file.write_text(content, encoding="utf-8")
            log.debug(f"Modified: {md_file.name}")
            modified_count += 1

    log.info(f"Converted {modified_count} files")
    return modified_count
