These are wrappers for the wonderful [pandoc](http://johnmacfarlane.net/pandoc/) tool that I use for creating web pages, presentations, papers, and even books. I don't imagine they will be useful to others off-the-shelf but there might be handy techniques, particular the super simple, limited, but fast bibtex chunker in `mdn2bib`.

```
uv tool install https://github.com/reagle/pandoc-wrappers.git
```

## md2bib

Extract a subset of bibliographic keys from BIB_FILE (bib or yaml) using those keys found in a markdown file or specified in argument.

## markdown-wrapper

A wrapper script for pandoc that handles my own issues, including

1. associating the result with a particular style sheet;
2. replacing [@key] with hypertext'd refs from bibtex database;
3. creating handouts for students from slides;

## doc2txt

Create plain text versions of documents using other tools such as text-based browsers and pandoc.

## wiki-update

Build the static portions of my website by looking for source files newer than existing HTML files.

    ob-/* (obsidian) -> html
    *.md (pandoc)-> html

2023-05-05: Freeplane and Zim wiki builds have been removed for lack of use.