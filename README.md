
These are wrappers for the wonderful [pandoc](http://johnmacfarlane.net/pandoc/) tool that I use for creating web pages, presentations, papers, and even books. I don't imagine they will be useful to others off-the-shelf but there might be handy techniques, particular the super simple, limited, but fast bibtex parser in `mdn2bib`.

## md2bib.py

A set of bibtex utilities for parsing and manipulating bibtex files, especially in the context of my pandoc wrappers

## markdown-wrapper.py

A wrapper script for pandoc that handles my own issues:

1. associates the result with a particular style sheet;
2. can replace [@key] with hypertext'd refs from bibtex database;
3. can create partial handouts for students for slides.

## doc2txt.py

Wraps many tools for converting documents to text.

## wiki-update.py

Build the static portions of my website by looking for source files newer than existing HTML files.

    *.mm (freemind)-> html
    *.md (pandoc)-> html
    zim/* (zim-wiki) -> html
