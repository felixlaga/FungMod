# Citing FungMod

If you use FungMod in your research, please cite it. Citing software helps others
reproduce your work and gives credit to the people who build and maintain the
tools you depend on.

## Recommended citation

The canonical, machine-readable citation lives in
[`CITATION.cff`](https://github.com/felixlaga/FungMod/blob/main/CITATION.cff) at
the repository root. GitHub renders a "Cite this repository" button from it, and
tools such as [`cffconvert`](https://github.com/citation-file-format/cffconvert)
can convert it to BibTeX, EndNote, RIS, and other formats:

```bash
python -m pip install cffconvert
cffconvert --format bibtex     # BibTeX
cffconvert --format apalike    # APA-like plain text
```

Always cite the **version** you actually used (`fungmod.__version__`), and,
once available, the version DOI for that release.

## DOI and archival

Tagged releases are archived on [Zenodo](https://zenodo.org/), which mints a DOI
for every version plus a **concept DOI** that always resolves to the latest
archived release. Prefer the concept DOI for general references and the
version-specific DOI for exact reproducibility.

!!! note "Maintainer action"

    Zenodo archiving requires a one-time connection between the GitHub
    repository and a Zenodo account. Until the first release is archived, cite
    the version and repository URL. Once the DOI exists, add it to `CITATION.cff`
    (`doi:`) and the badges in the README. See the release checklist in
    [CONTRIBUTING.md](https://github.com/felixlaga/FungMod/blob/main/CONTRIBUTING.md).

## Scientific-integrity note when citing results

FungMod is an exploratory modelling engine. When you cite FungMod in a results
context, state the maturity of the capability you used (see the
[user guide](user-guide.md#maturity-labels)) and do not present software
verification as empirical validation. Report the parameters, provenance, seed,
and version so your run can be reproduced.
