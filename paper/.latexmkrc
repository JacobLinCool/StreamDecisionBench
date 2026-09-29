# latexmk configuration: pdflatex + bibtex, auxiliary files in build/, PDFs next to the sources.
# `latexmk` builds both versions of main.tex: submission.pdf (anonymous review) and preprint.pdf.
$pdf_mode = 1;
$bibtex_use = 2;
$aux_dir = 'build';
$out_dir = '.';
$emulate_aux = 1;
@default_files = ('submission.tex', 'preprint.tex');
$pdflatex = 'pdflatex -interaction=nonstopmode -halt-on-error -file-line-error %O %S';
