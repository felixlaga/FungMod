"""Genome-derived enzymatic capability resolution.

Answers which capabilities an organism plausibly encodes, never at what rate,
from a dbCAN genome annotation or a UniProt proteome export.
"""

from .dbcan import (
    GENE_ID_COLUMN,
    TOOL_COLUMNS,
    DbcanOverview,
    OverviewGene,
    annotation_from_overview,
    families_from_overview,
    parse_overview,
)
from .resolution import (
    DIAGNOSTIC,
    POLYSPECIFIC,
    SPECIFICITY_LEVELS,
    CapabilityResolution,
    CapabilityResolutionError,
    CapabilityResolver,
    CazymeAnnotation,
    CazymeFamilyMap,
    FamilyMapping,
    ResolvedCapability,
    default_family_map_path,
)
from .uniprot import (
    UNIPROT_COLUMNS,
    UNIPROT_EVIDENCE_COLUMNS,
    EcCazyDisagreement,
    ProteomeClassSupport,
    ProteomeResolution,
    UniprotEntry,
    UniprotProteome,
    decode_uniprot_tsv,
    parse_uniprot_tsv,
    resolve_uniprot_proteome,
)

__all__ = [
    "GENE_ID_COLUMN",
    "TOOL_COLUMNS",
    "DbcanOverview",
    "OverviewGene",
    "annotation_from_overview",
    "families_from_overview",
    "parse_overview",
    "default_family_map_path",
    "DIAGNOSTIC",
    "POLYSPECIFIC",
    "SPECIFICITY_LEVELS",
    "CapabilityResolution",
    "CapabilityResolutionError",
    "CapabilityResolver",
    "CazymeAnnotation",
    "CazymeFamilyMap",
    "FamilyMapping",
    "ResolvedCapability",
    "UNIPROT_COLUMNS",
    "UNIPROT_EVIDENCE_COLUMNS",
    "EcCazyDisagreement",
    "ProteomeClassSupport",
    "ProteomeResolution",
    "UniprotEntry",
    "UniprotProteome",
    "decode_uniprot_tsv",
    "parse_uniprot_tsv",
    "resolve_uniprot_proteome",
]
