"""Pelican blog configuration and build function.

Canonical blog configurations and the build_blog() function used by
wiki_update to generate Pelican static sites from Obsidian vaults.

Test with:

uv run --with pytest pytest --doctest-modules src/pandoc_wrappers/pelican_build.py -v

"""

__author__ = "Joseph Reagle"
__copyright__ = "Copyright (C) 2009-2026 Joseph Reagle"
__license__ = "GLPv3"
__version__ = "3.0.0"

import logging
import subprocess
from pathlib import Path

from pandoc_wrappers.obsidian_utils import (
    build_note_index,
    build_photo_index,
    clear_directory,
    copy_vault,
    needs_build,
    process_blog_files,
)

log = logging.getLogger(__name__)

WEB_ROOT = Path.home() / "data/2web"

type BlogConfig = dict[str, Path | str]

BLOG_CONFIGS: dict[str, BlogConfig] = {
    "codex": {
        "source": WEB_ROOT / "reagle.org/joseph/bl-codex",
        "export_dir": WEB_ROOT / "reagle.org/joseph/bl-codex-tmp-export",
        "pelican_config": WEB_ROOT / "pelican/codex-pelicanconf.py",
        "cache_path": WEB_ROOT / "pelican/codex-cache",
        "base_url": "https://reagle.org/joseph/pelican",
        "output": WEB_ROOT / "reagle.org/joseph/pelican/index.html",
    },
    "goatee": {
        "source": WEB_ROOT / "goatee.net/bl-goatee",
        "export_dir": WEB_ROOT / "goatee.net/bl-goatee-tmp-export",
        "pelican_config": WEB_ROOT / "pelican/goatee-pelicanconf.py",
        "cache_path": WEB_ROOT / "pelican/goatee-cache",
        "base_url": "https://goatee.net/blog",
        "output": WEB_ROOT / "goatee.net/blog/index.html",
        # vault symlink to the gallery, and the URL it publishes as
        "photo_dir": "photo",
        "photo_url": "https://goatee.net/photo/gallery",
    },
}


def build_blog(config: dict[str, Path | str], *, force: bool = False) -> bool:
    """Build a single Pelican blog from its config.

    Returns True if the blog was built, False if skipped.
    """
    source = Path(config["source"])
    output = Path(config["output"])
    export_dir = Path(config["export_dir"])
    pelican_config = Path(config["pelican_config"])
    cache_path = Path(config["cache_path"])
    base_url = str(config["base_url"])

    if not force and not needs_build(source, output):
        log.info(f"Skipping blog, no changes in {source}")
        return False

    if not source.is_dir():
        log.error(f"Vault directory not found: {source}")
        return False

    clear_directory(export_dir)
    copy_vault(source, export_dir)

    note_index = build_note_index(export_dir)
    photo_dir = str(config["photo_dir"]) if "photo_dir" in config else None
    photo_url = str(config["photo_url"]) if "photo_url" in config else None
    photo_index = (
        build_photo_index(source / photo_dir, photo_dir) if photo_dir else None
    )
    process_blog_files(
        export_dir,
        base_url,
        note_index,
        photo_dir=photo_dir,
        photo_url=photo_url,
        photo_index=photo_index,
    )

    # Pass path and cache explicitly so a config that has drifted (e.g. a
    # stale PATH pointing at the vault instead of the export dir, which
    # silently publishes unrewritten photo paths) can't override us.
    log.info(f"Running pelican with {pelican_config}")
    subprocess.run(
        [
            "pelican",
            "-s",
            str(pelican_config),
            "--cache-path",
            str(cache_path),
            str(export_dir),
        ],
        text=True,
        check=True,
    )

    return True
