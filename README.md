
These are wrappers for the wonderful [pandoc](http://johnmacfarlane.net/pandoc/) tool that I use for creating web pages, presentations, papers, and even my book. I don't imagine they will be useful to others off-the-shelf but there might be handy techniques, particular the super simple, limited, but fast bibtex parser in `mdn2bib`.

## mdn2bib.py

A set of bibtex utilities for parsing and manipulating bibtex files, 
especially in the context of my pandoc wrappers

## md.py

A wrapper script for pandoc that handles my own issues:

1. associates the result with a particular style sheet.
2. can replace [@key] with hypertext'd refs from bibtex database.
3. makes use of DZSlides for presentations.

## bd.py

Build a PDF (article or book) based on markdown source using pandoc.

## bdh.py

Like `bd`, but will build HTML using [htlatex](http://www.tug.org/applications/tex4ht/mn-commands.html).

## wiki-update.py

Build the static portions of my website by looking for source files newer than existing HTML files.

    *.mm (freemind)-> html
    *.md (pandoc)-> html
    zim/* (zim-wiki) -> html
