"""A BioModels-ready deposit for the SABIO-RK Reaction 618 beta-glucosidase case.

This module builds a curated, annotated, submission-ready deposit for the one
concrete bundled case the maintainers chose: the SABIO-RK Reaction 618
beta-glucosidase hydrolysis of cellobiose to glucose (selected kinetic-law
EntryID 35622; Seshadri et al. 2009, *Plant Physiol.*). The deposit is:

- ``model.xml`` — SBML with SBO terms and MIRIAM annotations (ChEBI, EC, UniProt,
  KEGG, MetaNetX, NCBI Taxonomy, PubMed);
- ``<id>.omex`` — a COMBINE archive bundling the annotated SBML with a SED-ML
  time course;
- ``README.md`` — provenance, the identifiers used, explicit modelling
  assumptions, and BioModels submission instructions.

The kinetic parameters (Km, kcat) are taken verbatim from the curated SABIO-RK
kinetic record. The MIRIAM identifiers below are drawn from that record where
available (EC, UniProt, KEGG, MetaNetX, PubMed, organism) and completed with
standard database identifiers for the chemicals; they are curator-reviewable.
Initial concentrations are explicit modelling assumptions, not source data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, Quantity
from fungal_model.processes.assembly import (
    AssembledModel,
    AssemblyReport,
    ModelAssemblyContext,
)
from fungal_model.processes.homogeneous import HomogeneousMichaelisMentenProcess
from fungal_model.standards.combine import write_combine_archive
from fungal_model.standards.sbml import MiriamAnnotation, write_sbml

REACTION_618_MODEL_ID = "sabiork_reaction_618_beta_glucosidase"
REACTION_618_MODEL_NAME = "SABIO-RK Reaction 618 beta-glucosidase (cellobiose hydrolysis)"

_SOURCE = (
    "SABIO-RK Reaction 618 selected kinetic law (EntryID 35622); "
    "Seshadri et al. 2009, Plant Physiol. (PMID 19587102)."
)

# Curated MIRIAM annotations. EC, UniProt, KEGG, MetaNetX, PubMed, and organism
# come from the curated kinetic record; ChEBI identifiers are standard database
# identifiers for the chemicals. All are curator-reviewable.
REACTION_618_ANNOTATIONS: dict[str, list[MiriamAnnotation]] = {
    "model": [
        MiriamAnnotation("bqbiol:hasTaxon", ("https://identifiers.org/taxonomy:4530",)),
        MiriamAnnotation("bqmodel:isDescribedBy", ("https://identifiers.org/pubmed:19587102",)),
    ],
    "cellobiose": [MiriamAnnotation("bqbiol:is", ("https://identifiers.org/CHEBI:17057",))],
    "glucose": [MiriamAnnotation("bqbiol:is", ("https://identifiers.org/CHEBI:15903",))],
    "beta_glucosidase": [
        MiriamAnnotation("bqbiol:is", ("https://identifiers.org/uniprot:Q8L7J2",)),
        MiriamAnnotation("bqbiol:isVersionOf", ("https://identifiers.org/ec-code:3.2.1.21",)),
        MiriamAnnotation("bqbiol:hasTaxon", ("https://identifiers.org/taxonomy:4530",)),
    ],
    "beta_glucosidase_cellobiose_hydrolysis": [
        MiriamAnnotation(
            "bqbiol:is",
            (
                "https://identifiers.org/kegg.reaction:R00026",
                "https://identifiers.org/metanetx.reaction:MNXR146826",
            ),
        ),
        MiriamAnnotation("bqbiol:isVersionOf", ("https://identifiers.org/ec-code:3.2.1.21",)),
    ],
}

# Explicit modelling assumptions (not source data).
_INITIAL_CELLOBIOSE_MM = 20.0
_INITIAL_ENZYME_MM = 1.0e-5  # 10 nM, matching the bundled showcase enzyme dose
_SIMULATION_END_SECONDS = 3600.0
_SIMULATION_STEPS = 120


@dataclass(frozen=True)
class BioModelsDeposit:
    """Paths written by :func:`write_biomodels_deposit`."""

    directory: Path
    sbml_model: Path
    combine_archive: Path
    readme: Path


def build_reaction_618_model() -> tuple[AssembledModel, dict[str, Quantity]]:
    """Build the Reaction 618 enzyme-explicit Michaelis-Menten model.

    Returns the assembled model and its initial state. Km and kcat are the
    curated SABIO-RK values; initial concentrations are explicit assumptions.
    """

    process = HomogeneousMichaelisMentenProcess(
        name="beta_glucosidase_cellobiose_hydrolysis",
        substrate_state="cellobiose",
        km_symbol="Km_cellobiose",
        rate_units="millimolar/second",
        substrate_units="millimolar",
        product_state="glucose",
        enzyme_state="beta_glucosidase",
        enzyme_units="millimolar",
        kcat_symbol="kcat_cellobiose",
        product_coefficients={"glucose": 2.0},
        source=_SOURCE,
    )
    parameters = ParameterSet(
        [
            Parameter(
                name="Km for cellobiose",
                symbol="Km_cellobiose",
                value=15.3,
                units="millimolar",
                uncertainty=1.2,
                source=_SOURCE,
                confidence_level="medium",
                notes="Km for cellobiose from selected SABIO-RK Reaction 618 EntryID 35622.",
            ),
            Parameter(
                name="kcat for cellobiose",
                symbol="kcat_cellobiose",
                value=0.13,
                units="1/second",
                uncertainty=0.001,
                source=_SOURCE,
                confidence_level="medium",
                notes="Turnover number from selected SABIO-RK Reaction 618 EntryID 35622.",
            ),
        ]
    )
    context = ModelAssemblyContext()
    model = AssembledModel(
        processes=(process,),
        parameters=parameters,
        context=context,
        state_variables=tuple(process.state_variables),
        assumptions=(),
        validators=(),
        solver_settings=SolverSettings(),
        assembly_report=AssemblyReport(context=context),
    )
    initial_state: dict[str, Quantity] = {
        "cellobiose": Q_(_INITIAL_CELLOBIOSE_MM, "millimolar"),
        "glucose": Q_(0.0, "millimolar"),
        "beta_glucosidase": Q_(_INITIAL_ENZYME_MM, "millimolar"),
    }
    return model, initial_state


def write_biomodels_deposit(output_dir: str | Path) -> BioModelsDeposit:
    """Write the BioModels-ready deposit for the Reaction 618 case to ``output_dir``."""

    model, initial_state = build_reaction_618_model()
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    sbml_path = write_sbml(
        model,
        directory / "model.xml",
        initial_state=initial_state,
        model_id=REACTION_618_MODEL_ID,
        model_name=REACTION_618_MODEL_NAME,
        annotations=REACTION_618_ANNOTATIONS,
    )
    combine_path = write_combine_archive(
        model,
        directory / f"{REACTION_618_MODEL_ID}.omex",
        initial_state=initial_state,
        output_end_time=Q_(_SIMULATION_END_SECONDS, "second"),
        number_of_steps=_SIMULATION_STEPS,
        model_id=REACTION_618_MODEL_ID,
        model_name=REACTION_618_MODEL_NAME,
        annotations=REACTION_618_ANNOTATIONS,
    )
    readme_path = directory / "README.md"
    readme_path.write_text(_deposit_readme(), encoding="utf-8", newline="")

    return BioModelsDeposit(
        directory=directory,
        sbml_model=sbml_path,
        combine_archive=combine_path,
        readme=readme_path,
    )


def _deposit_readme() -> str:
    return f"""# {REACTION_618_MODEL_NAME}

A BioModels-ready deposit generated by FungMod for the SABIO-RK Reaction 618
beta-glucosidase case.

## Model

Enzyme-explicit Michaelis-Menten hydrolysis of cellobiose to glucose:

    rate = kcat * [beta_glucosidase] * [cellobiose] / (Km + [cellobiose])
    cellobiose -> 2 glucose

## Provenance

- Source: {_SOURCE}
- Reference: Seshadri S, Akiyama T, Opassiri R, Kuaprasert B, Cairns JK (2009),
  *Plant Physiol.* (PMID 19587102); enzyme Os3BGlu6 from *Oryza sativa*.

## Parameters (curated, verbatim from SABIO-RK)

| Symbol | Value | Units | SBO |
| --- | --- | --- | --- |
| Km_cellobiose | 15.3 | mM | SBO:0000027 |
| kcat_cellobiose | 0.13 | 1/s | SBO:0000025 |

## Explicit modelling assumptions (not source data)

- Initial cellobiose: {_INITIAL_CELLOBIOSE_MM} mM.
- Initial glucose: 0 mM.
- Enzyme concentration: {_INITIAL_ENZYME_MM} mM (10 nM), matching the bundled
  showcase enzyme dose. kcat requires an explicit enzyme concentration.
- Water is treated as an implicit constant solvent (omitted, standard practice).
- Well-mixed unit-compartment representation (see the SBML model notes).

## MIRIAM annotations (curator-reviewable)

| Element | Qualifier | Identifier |
| --- | --- | --- |
| cellobiose | bqbiol:is | CHEBI:17057 |
| glucose | bqbiol:is | CHEBI:15903 |
| beta_glucosidase | bqbiol:is | uniprot:Q8L7J2 |
| beta_glucosidase | bqbiol:isVersionOf | ec-code:3.2.1.21 |
| reaction | bqbiol:is | kegg.reaction:R00026, metanetx.reaction:MNXR146826 |
| model | bqbiol:hasTaxon | taxonomy:4530 (*Oryza sativa*) |
| model | bqmodel:isDescribedBy | pubmed:19587102 |

## Submitting to BioModels

1. Review and adjust the MIRIAM identifiers above if needed.
2. Validate `model.xml` (e.g. with the SBML online validator) and the
   `{REACTION_618_MODEL_ID}.omex` COMBINE archive.
3. Submit the COMBINE archive at <https://www.ebi.ac.uk/biomodels/submit>.

## Scientific-integrity note

A successful simulation of this model proves the configured software contract
executed. Km and kcat are curated single-entry SABIO-RK values; the initial
concentrations are explicit assumptions. This is not a calibrated,
whole-organism, or empirically validated prediction.
"""


__all__ = [
    "REACTION_618_ANNOTATIONS",
    "REACTION_618_MODEL_ID",
    "REACTION_618_MODEL_NAME",
    "BioModelsDeposit",
    "build_reaction_618_model",
    "write_biomodels_deposit",
]
