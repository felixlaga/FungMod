"""Registry records for xylan, starch and chitin and their hydrolase classes (REGISTRY-002).

The enzyme classes ``endo_xylanase`` (EC 3.2.1.8; CAZy GH10, GH11),
``glucoamylase`` (EC 3.2.1.3; GH15) and ``chitinase`` (EC 3.2.1.14; GH18) are
categorical metadata from the IUBMB enzyme nomenclature and the CAZy family
descriptions: target bond classes, substrate classes and the one process law
that user data runs as an apparent law on a suspended solid. The substrates
``xylan``, ``starch`` and ``chitin`` are generic solid polymers; three product
maps record their complete-hydrolysis mass yields, which these tests recompute
from atomic weights. No kinetic value is shipped. The simulations below run on
illustrative estimates written by the tests (not measurements), in exploratory
mode only.
"""

from __future__ import annotations

import csv
import io
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from scipy.special import lambertw

from fungal_model import UserDataError, UserDataset, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import enzyme_class_acts_on
from fungal_model.capability import DIAGNOSTIC, CapabilityResolver, CazymeFamilyMap
from fungal_model.capability.uniprot import parse_uniprot_tsv, resolve_uniprot_proteome
from fungal_model.registry import FungModRegistry, RegistryResolver, load_registry
from fungal_model.registry.loaders import load_parameter_record_mapping
from fungal_model.registry.records import ParameterRecord

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
GENOME = FIXTURES / "genome_case"
UNIPROT = FIXTURES / "uniprot_case"
GENOME_ANNOTATION = "annotations/strain_g1_overview.txt"
UNIPROT_ANNOTATION = "annotations/strain_u1_uniprot.tsv"
FAMILY_MAP_SOURCE = "doi:10.1093/nar/gkab1045"

# Conventional atomic weights (IUPAC) used to recompute the product-map yields.
ATOMIC_WEIGHT = {"C": 12.011, "H": 1.008, "N": 14.007, "O": 15.999}

# record id -> (EC number, CAZy families, target bond classes, substrate classes)
CLASSES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "endo_xylanase": ("3.2.1.8", ("GH10", "GH11"), ("beta_1_4_xylosidic",), ("xylan",)),
    "glucoamylase": ("3.2.1.3", ("GH15",), ("alpha_1_4_glycosidic", "alpha_1_6_glycosidic"), ("starch",)),
    "chitinase": ("3.2.1.14", ("GH18",), ("beta_1_4_n_acetylglucosaminidic",), ("chitin",)),
}
# record id -> (bond classes, product, product map, monomer formula, anhydro-unit formula)
SUBSTRATES: dict[str, tuple[tuple[str, ...], str, str, str, str]] = {
    "xylan": (
        ("beta_1_4_xylosidic",),
        "D_xylose_equivalent",
        "xylan_to_d_xylose_equivalent_mass_yield",
        "C5H10O5",
        "C5H8O4",
    ),
    "starch": (
        ("alpha_1_4_glycosidic", "alpha_1_6_glycosidic"),
        "beta_D_glucose",
        "starch_to_beta_d_glucose_mass_yield",
        "C6H12O6",
        "C6H10O5",
    ),
    "chitin": (
        ("beta_1_4_n_acetylglucosaminidic",),
        "N_acetyl_D_glucosamine_equivalent",
        "chitin_to_n_acetyl_d_glucosamine_equivalent_mass_yield",
        "C8H15NO6",
        "C8H13NO5",
    ),
}
ENZYME_FOR_SUBSTRATE = {"xylan": "endo_xylanase", "starch": "glucoamylase", "chitin": "chitinase"}
EC_TERM = re.compile(r"^(?:EC\s+)?(\d+\.\d+\.\d+\.\d+)$")
SOLID_SUBSTRATE_HEADER = (
    "substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,amount_basis,product,"
    "product_yield,yield_basis,source"
)
KINETICS_HEADER = (
    "strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,"
    "sd,replicates"
)


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


def _molar_mass(formula: str) -> float:
    total = 0.0
    for element, count in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        total += ATOMIC_WEIGHT[element] * (int(count) if count else 1)
    return total


def _complete_hydrolysis_yield(substrate: str) -> float:
    """Grams of monomer per gram of anhydro units: M(monomer) / M(monomer - H2O)."""

    _bonds, _product, _map, monomer, anhydro = SUBSTRATES[substrate]
    return _molar_mass(monomer) / _molar_mass(anhydro)


# ---------------------------------------------------------------------------
# Records


@pytest.mark.parametrize("record_id", sorted(CLASSES))
def test_enzyme_class_records_are_categorical_metadata_without_kinetics(
    base_registry: FungModRegistry, record_id: str
) -> None:
    ec_number, families, bonds, substrate_classes = CLASSES[record_id]
    record = base_registry.enzyme_classes[record_id]
    assert record.validate().passed
    assert record.ec_number == ec_number
    assert f"EC {ec_number}" in record.aliases
    assert record.maturity == "literature_metadata"
    assert record.target_bond_classes == bonds
    assert record.compatible_substrate_classes == substrate_classes
    assert record.compatible_processes == ("homogeneous_michaelis_menten",)
    source = record.provenance["source"]
    assert "ExplorEnz" in source and f"EC {ec_number}" in source and FAMILY_MAP_SOURCE in source
    assert all(family in source for family in families)
    assert record.provenance["confidence_level"] == "literature_curated"
    assert "No kinetic value is recorded or implied" in record.provenance["notes"]
    # No kinetics anywhere: no parameter, compatibility or case-template record names the class.
    assert not any(parameter.enzyme_class == record_id for parameter in base_registry.parameters.values())
    assert not any(item.enzyme_class == record_id for item in base_registry.process_compatibility.values())
    # The curated CAZy family map is unchanged and resolves to these ids.
    family_map = CazymeFamilyMap.load()
    for family in families:
        (mapping,) = family_map.for_family(family)
        assert (mapping.enzyme_class, mapping.specificity) == (record_id, DIAGNOSTIC)


@pytest.mark.parametrize("record_id", sorted(SUBSTRATES))
def test_substrate_records_are_generic_solid_polymers(base_registry: FungModRegistry, record_id: str) -> None:
    bonds, product, _map, _monomer, _anhydro = SUBSTRATES[record_id]
    record = base_registry.substrates[record_id]
    assert record.validate().passed
    assert (record.substrate_class, record.physical_state) == (record_id, "solid_polymer")
    assert record.bond_classes == bonds
    assert record.products == (product,)
    assert dict(record.properties) == {}
    assert record.maturity == "exploratory_metadata"
    assert record.provenance["source"].startswith("Generic polysaccharide definition")
    assert "Not a characterized preparation" in record.provenance["source"]
    assert record.provenance["notes"].startswith("Composition varies by source")
    assert not any(parameter.substrate_id == record_id for parameter in base_registry.parameters.values())
    assert not any(item.substrate_class == record_id for item in base_registry.process_compatibility.values())


def test_each_class_acts_on_its_own_polymer_only(base_registry: FungModRegistry) -> None:
    """The categorical rule of the registry: a class acts on a substrate through a shared bond class."""

    acting = {
        (class_id, substrate_id)
        for class_id, enzyme in base_registry.enzyme_classes.items()
        for substrate_id, substrate in base_registry.substrates.items()
        if substrate_id in SUBSTRATES or class_id in CLASSES
        if enzyme_class_acts_on(
            target_bond_classes=enzyme.target_bond_classes,
            compatible_substrate_classes=enzyme.compatible_substrate_classes,
            substrate_class=substrate.substrate_class,
            bond_classes=substrate.bond_classes,
        )
    }
    assert acting == {(enzyme, substrate) for substrate, enzyme in ENZYME_FOR_SUBSTRATE.items()} | {("lytic_polysaccharide_monooxygenase", "chitin")}
    starch = base_registry.substrates["starch"]
    glucoamylase = base_registry.enzyme_classes["glucoamylase"]
    assert enzyme_class_acts_on(
        target_bond_classes=glucoamylase.target_bond_classes,
        compatible_substrate_classes=glucoamylase.compatible_substrate_classes,
        substrate_class=starch.substrate_class,
        bond_classes=starch.bond_classes,
    ) == ("alpha_1_4_glycosidic", "alpha_1_6_glycosidic")


def test_source_backed_mechanism_records_exist_but_other_classes_remain_absent(base_registry: FungModRegistry) -> None:
    assert base_registry.enzyme_classes["endoglucanase"].compatible_processes == ("chain_endo_scission",)
    assert base_registry.enzyme_classes["lytic_polysaccharide_monooxygenase"].compatible_processes == ("peroxide_oxidative_cleavage",)
    for absent in ("laccase", "alpha_amylase"):
        assert absent not in base_registry.enzyme_classes


def test_no_ec_number_is_carried_by_two_classes(base_registry: FungModRegistry) -> None:
    """The UniProt route treats an EC number on two classes as ambiguous; every registry EC names one class."""

    holders: dict[str, set[str]] = {}
    for record_id, record in base_registry.enzyme_classes.items():
        terms = [record.ec_number, *record.aliases] if record.ec_number else list(record.aliases)
        for term in terms:
            match = EC_TERM.fullmatch(term.strip())
            if match:
                holders.setdefault(match.group(1), set()).add(record_id)
    assert {ec: classes for ec, classes in holders.items() if len(classes) > 1} == {}
    for record_id, (ec_number, *_rest) in CLASSES.items():
        assert holders[ec_number] == {record_id}


# ---------------------------------------------------------------------------
# Name resolution


@pytest.mark.parametrize(
    ("query", "record_id"),
    [
        ("endo_xylanase", "endo_xylanase"),
        ("endo-1,4-beta-xylanase", "endo_xylanase"),
        ("Xylanase", "endo_xylanase"),
        ("endoxylanase", "endo_xylanase"),
        ("3.2.1.8", "endo_xylanase"),
        ("EC 3.2.1.8", "endo_xylanase"),
        ("glucoamylase", "glucoamylase"),
        ("glucan 1,4-alpha-glucosidase", "glucoamylase"),
        ("amyloglucosidase", "glucoamylase"),
        ("EC 3.2.1.3", "glucoamylase"),
        ("chitinase", "chitinase"),
        ("endochitinase", "chitinase"),
        ("3.2.1.14", "chitinase"),
    ],
)
def test_enzyme_class_names_aliases_and_ec_numbers_resolve(
    base_registry: FungModRegistry, query: str, record_id: str
) -> None:
    resolver = RegistryResolver(base_registry)
    assert resolver.resolve_enzyme_class(query).record_id == record_id
    assert resolver.resolve_any(query).record_id == record_id


@pytest.mark.parametrize(
    ("query", "record_id"),
    [
        ("xylan", "xylan"),
        ("Generic insoluble xylan", "xylan"),
        ("generic xylan", "xylan"),
        ("starch", "starch"),
        ("Generic solid starch", "starch"),
        ("chitin", "chitin"),
        ("generic chitin", "chitin"),
    ],
)
def test_substrate_names_and_aliases_resolve(base_registry: FungModRegistry, query: str, record_id: str) -> None:
    resolver = RegistryResolver(base_registry)
    assert resolver.resolve_substrate(query).record_id == record_id
    assert resolver.resolve_any(query).record_id == record_id


# ---------------------------------------------------------------------------
# Product maps


@pytest.mark.parametrize("substrate", sorted(SUBSTRATES))
def test_product_map_yields_match_the_atomic_mass_computation(base_registry: FungModRegistry, substrate: str) -> None:
    _bonds, product, map_id, monomer, anhydro = SUBSTRATES[substrate]
    record = base_registry.get_product_map(map_id)
    assert record.validate().passed
    assert record.product_map_type == "stoichiometric"
    assert dict(record.reactants) == {substrate: 1.0}
    assert set(record.products) == {product}
    expected = _complete_hydrolysis_yield(substrate)
    # Stored to six decimals.
    assert record.products[product] == pytest.approx(expected, abs=5e-7)
    assert record.provenance["yield_basis"] == "g/g"
    formula = record.provenance["formula"]
    assert f"M({monomer}) / M({anhydro})" in formula
    assert f"{_molar_mass(monomer):.3f} / {_molar_mass(anhydro):.3f}" in formula
    used = {element for element in ATOMIC_WEIGHT if element in monomer}
    assert all(f"{element} {ATOMIC_WEIGHT[element]}" in record.provenance["source"] for element in used)
    assert "No simulation route reads this map automatically" in record.notes
    assert record.to_product_release_map().products == {product: record.products[product]}
    # The map names the registry substrate and the product the substrate declares.
    assert product in base_registry.substrates[substrate].products
    assert map_id in base_registry.substrates[substrate].notes


def test_the_three_yields_are_the_monomer_to_anhydro_unit_mass_ratios() -> None:
    """Glucose 180.156/162.141, xylose 150.130/132.115, GlcNAc 221.209/203.194 g/mol."""

    formulas = {
        "glucose": "C6H12O6",
        "anhydroglucose": "C6H10O5",
        "xylose": "C5H10O5",
        "anhydroxylose": "C5H8O4",
        "glcnac": "C8H15NO6",
        "anhydro_glcnac": "C8H13NO5",
    }
    masses = {name: _molar_mass(formula) for name, formula in formulas.items()}
    water = _molar_mass("H2O")
    for monomer, anhydro in (("glucose", "anhydroglucose"), ("xylose", "anhydroxylose"), ("glcnac", "anhydro_glcnac")):
        assert masses[monomer] - masses[anhydro] == pytest.approx(water, abs=1e-9)
    assert _complete_hydrolysis_yield("starch") == pytest.approx(1.1111, abs=5e-5)
    assert _complete_hydrolysis_yield("xylan") == pytest.approx(1.1364, abs=5e-5)
    assert _complete_hydrolysis_yield("chitin") == pytest.approx(1.0887, abs=5e-5)


# ---------------------------------------------------------------------------
# Genome and UniProt routes


def _copy(tmp_path: Path, source: Path, edits: Mapping[str, str]) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    for name, text in edits.items():
        (target / name).write_text(text, encoding="utf-8")
    return target


def _records(dataset: UserDataset, record_type: str) -> dict[str, Mapping[str, Any]]:
    return {str(mapping["record_id"]): mapping for mapping in dataset.records[record_type]}


def _parameter(dataset: UserDataset, record_id: str) -> ParameterRecord:
    return load_parameter_record_mapping(_records(dataset, "parameter_records")[record_id])


def _registry_row(registry: FungModRegistry, substrate: str, *, substrate_id: str | None = None) -> str:
    """A substrates.csv row referencing a registry polymer with its product map's yield as the stated yield."""

    _bonds, product, map_id, _monomer, _anhydro = SUBSTRATES[substrate]
    coefficient = registry.get_product_map(map_id).products[product]
    return (
        f"{substrate_id or substrate},{substrate},,,,,dry_mass,{product},{coefficient!r},g/g,"
        f"Complete-hydrolysis mass yield of registry product map {map_id}"
    )


def _with_registry_polymers(source: Path, registry: FungModRegistry) -> str:
    """The fixture's substrates.csv with the amount_basis column and the three registry polymers."""

    rows = list(csv.DictReader((source / "substrates.csv").read_text(encoding="utf-8").splitlines()))
    buffer = io.StringIO()
    fieldnames = [str(column) for column in SOLID_SUBSTRATE_HEADER.split(",")]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "amount_basis": ""})
    return buffer.getvalue() + "".join(f"{_registry_row(registry, name)}\n" for name in sorted(SUBSTRATES))


def test_genome_gh10_gh15_and_gh18_genes_become_gaps_on_the_registry_polymers(
    base_registry: FungModRegistry, tmp_path: Path
) -> None:
    overview = (GENOME / GENOME_ANNOTATION).read_text(encoding="utf-8")
    overview += "synthetic_g011\t3.2.1.14\tGH18(25-410)\tGH18_e9\tGH18\t3\n"
    dataset = load_user_dataset(
        _copy(
            tmp_path,
            GENOME,
            {"substrates.csv": _with_registry_polymers(GENOME, base_registry), GENOME_ANNOTATION: overview},
        ),
        registry=base_registry,
    )
    resolved = {item["enzyme_class"]: item for item in dataset.genome_resolved_classes}
    assert {"endo_xylanase", "glucoamylase", "chitinase"} <= set(resolved)
    assert resolved["endo_xylanase"]["families"] == ["GH10"]
    assert resolved["glucoamylase"]["families"] == ["GH15"]
    assert resolved["chitinase"]["families"] == ["GH18"]
    assert {item["enzyme_class"] for item in dataset.unmodellable_enzyme_classes} == {"laccase"}
    # Registry substrates are referenced, not copied: only the fixture's user-defined maltose has a record.
    assert set(_records(dataset, "substrates")) == {"genome_demo__maltose"}

    names = {"endo_xylanase": "Endo-1,4-beta-xylanase", "glucoamylase": "Glucoamylase", "chitinase": "Chitinase"}
    families = {"endo_xylanase": "GH10", "glucoamylase": "GH15", "chitinase": "GH18"}
    parameters = _records(dataset, "parameter_records")
    for substrate, enzyme in ENZYME_FOR_SUBSTRATE.items():
        prefix = f"genome_demo__strain_g1__{enzyme}__{substrate}__c30_ph5__"
        note = f"; the class was inferred from the dbCAN annotation (families {families[enzyme]})."
        for quantity in ("km", "kcat", "substrate_initial_concentration", "enzyme_concentration"):
            record = _parameter(dataset, f"{prefix}{quantity}__gap")
            assert record.value.is_unknown
            assert record.maturity == "user_dataset_gap"
            assert record.provenance["measurement_request"].endswith(note)
        km = _parameter(dataset, f"{prefix}km__gap")
        substrate_name = base_registry.substrates[substrate].name
        assert km.provenance["measurement_request"] == (
            f"Measure km of {names[enzyme]} from Genome-annotated strain G1 on {substrate_name} at 30 degC, pH 5.0 "
            f"(dry mass per volume, for example g/L){note}"
        )
        # Each class acts on its own polymer only.
        for other in set(ENZYME_FOR_SUBSTRATE) - {substrate}:
            assert not any(key.startswith(f"genome_demo__strain_g1__{enzyme}__{other}__") for key in parameters)
        report = virtual_experiment(
            fungi="strain_g1", substrates=substrate, environments="c30_ph5", user_data=dataset
        ).preflight(mode="exploratory")[0]
        assert report.status == "underparameterized"
        assert all(text.endswith(note) for text in report.suggested_experiments)


def test_a_uniprot_row_with_gh11_and_ec_3_2_1_8_agrees(base_registry: FungModRegistry) -> None:
    tsv = (
        "Entry\tEC number\tCAZy\n"
        "X0POLY01\t3.2.1.8\tGH11;\n"
        "X0POLY02\t3.2.1.8\tGH10;CBM1;\n"
        "X0POLY03\t3.2.1.3\tGH15;\n"
        "X0POLY04\t3.2.1.14\tGH18;\n"
        "X0POLY05\t3.2.1.3\tGH11;\n"
    )
    resolution = resolve_uniprot_proteome(
        parse_uniprot_tsv(tsv, source="hand-written routing export"),
        capability_resolver=CapabilityResolver(
            family_map=CazymeFamilyMap.load(), registry_enzyme_classes=tuple(sorted(base_registry.enzyme_classes))
        ),
        registry=base_registry,
        organism="Synthetic format-fixture organism",
        proteome_source="hand-written routing export",
        annotation_tool="UniProt",
        annotation_tool_version="routing test",
        annotation_date="not recorded",
    )
    supports = {item.enzyme_class: dict(item.accessions_by_basis) for item in resolution.capabilities}
    assert supports["endo_xylanase"]["cazy_and_ec"] == ("X0POLY01", "X0POLY02")
    assert supports["glucoamylase"]["cazy_and_ec"] == ("X0POLY03",)
    assert supports["chitinase"]["cazy_and_ec"] == ("X0POLY04",)
    assert resolution.unresolved_ec_numbers == {}
    # GH11 names endo_xylanase and EC 3.2.1.3 names glucoamylase: a disagreement that supports neither.
    (disagreement,) = resolution.disagreements
    assert (disagreement.accession, disagreement.contested_classes) == ("X0POLY05", ("endo_xylanase", "glucoamylase"))


def test_a_proteome_resolved_endo_xylanase_is_a_gap_on_registry_xylan(
    base_registry: FungModRegistry, tmp_path: Path
) -> None:
    tsv = (UNIPROT / UNIPROT_ANNOTATION).read_text(encoding="utf-8") + (
        "X0POLY01\tSYNP1_XTEST\tSynthetic protein P1 (format fixture)\tsynthp1\tSynthetic format-fixture organism\t0\t"
        "3.2.1.8\tGH11;\treviewed\t221\n"
    )
    dataset = load_user_dataset(
        _copy(
            tmp_path,
            UNIPROT,
            {"substrates.csv": _with_registry_polymers(UNIPROT, base_registry), UNIPROT_ANNOTATION: tsv},
        ),
        registry=base_registry,
    )
    resolved = {item["enzyme_class"]: item for item in dataset.genome_resolved_classes}
    assert resolved["endo_xylanase"]["accessions_by_basis"] == {"cazy_and_ec": ["X0POLY01"], "cazy": [], "ec": []}
    assert resolved["endo_xylanase"]["ec_numbers"] == ["3.2.1.8"]
    record = _parameter(dataset, "uniprot_demo__strain_u1__endo_xylanase__xylan__c30_ph5__km__gap")
    assert record.provenance["measurement_request"] == (
        "Measure km of Endo-1,4-beta-xylanase from Proteome-annotated strain U1 on Generic insoluble xylan at "
        "30 degC, pH 5.0 (dry mass per volume, for example g/L); the class was inferred from UniProt proteome "
        "UP000000000 (accessions X0POLY01; CAZy families GH11; EC 3.2.1.8; 1 of 1 reviewed in Swiss-Prot)."
    )
    # X0TEST09 (GH15, EC 3.2.1.3) gives the glucoamylase gaps on registry starch.
    starch = _parameter(dataset, "uniprot_demo__strain_u1__glucoamylase__starch__c30_ph5__km__gap")
    assert "(accessions X0TEST09; CAZy families GH15; EC 3.2.1.3; 0 of 1 reviewed in Swiss-Prot)" in (
        starch.provenance["measurement_request"]
    )


# ---------------------------------------------------------------------------
# End to end: user estimates on a registry polymer, apparent Michaelis-Menten in mass units

# substrate -> (enzyme term in enzymes.csv, km g/L, kcat g/(mg*h), S0 g/L, enzyme mg/L); illustrative estimates.
RUNS: dict[str, tuple[str, float, float, float, float]] = {
    "xylan": ("EC 3.2.1.8", 8.0, 0.6, 10.0, 0.5),
    "starch": ("amyloglucosidase", 5.0, 1.2, 20.0, 0.25),
    "chitin": ("chitinase", 12.0, 0.2, 15.0, 2.0),
}


def _dataset_tables(registry: FungModRegistry, substrate: str, *, product_yield: str | None = None) -> dict[str, str]:
    enzyme_term, km, kcat, s0, enzyme = RUNS[substrate]
    enzyme_class = ENZYME_FOR_SUBSTRATE[substrate]
    substrate_row = _registry_row(registry, substrate)
    if product_yield is not None:
        cells = substrate_row.split(",")
        cells[8] = product_yield
        substrate_row = ",".join(cells)
    source = "Illustrative estimates for the REGISTRY-002 tests; not measurements"
    case = f"strain_p2,{enzyme_class},{substrate},c40_ph5"
    return {
        "user_dataset.yml": (
            f"dataset_id: {substrate}_registry_demo\ncontributor: FungMod maintainers\ndate: 2026-10-07\n"
            f"source: {source}\n"
            "simulation:\n  duration: 48\n  units: hour\n  points: 49\n"
        ),
        "strains.csv": "strain_id,name,scientific_name,aliases\nstrain_p2,Polysaccharide-route strain P2,,\n",
        "enzymes.csv": f"strain_id,enzyme_class,evidence,source\nstrain_p2,{enzyme_term},activity assay,LN-21 p. 1\n",
        "substrates.csv": f"{SOLID_SUBSTRATE_HEADER}\n{substrate_row}\n",
        "conditions.csv": "condition_id,temperature,temperature_units,ph,notes\nc40_ph5,40,degC,5,\n",
        "kinetics.csv": (
            f"{KINETICS_HEADER}\n"
            f"{case},km,{km},,,g/L,estimate,,LN-21 p. 2 (illustrative),,\n"
            f"{case},kcat,{kcat},,,g/(mg*h),estimate,,LN-21 p. 2 (illustrative),,\n"
            f"{case},substrate_initial_concentration,{s0},,,g/L,design,experimental design,LN-21 p. 3,,\n"
            f"{case},enzyme_concentration,{enzyme},,,mg/L,design,experimental design,LN-21 p. 3,,\n"
        ),
    }


def _write(directory: Path, tables: Mapping[str, str]) -> Path:
    directory.mkdir(parents=True)
    for name, text in tables.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def _lambert_w_substrate(times: np.ndarray, *, vmax: float, km: float, s0: float) -> np.ndarray:
    """Integrated Michaelis-Menten: Km ln(S0/S) + (S0 - S) = V t, so S = Km W((S0/Km) exp((S0 - V t)/Km))."""

    return km * np.real(lambertw((s0 / km) * np.exp((s0 - vmax * times) / km)))


@pytest.mark.parametrize("substrate", sorted(RUNS))
def test_user_estimates_on_a_registry_polymer_run_in_exploratory_mode_with_mass_closure(
    base_registry: FungModRegistry, tmp_path: Path, substrate: str
) -> None:
    _term, km, kcat, s0, enzyme = RUNS[substrate]
    enzyme_class = ENZYME_FOR_SUBSTRATE[substrate]
    _bonds, product, map_id, _monomer, _anhydro = SUBSTRATES[substrate]
    yield_value = base_registry.get_product_map(map_id).products[product]
    dataset = load_user_dataset(
        _write(tmp_path / "data", _dataset_tables(base_registry, substrate)), registry=base_registry
    )
    assert dataset.records["substrates"] == ()  # the registry polymer is referenced, not copied
    prefix = f"{substrate}_registry_demo"
    template = _records(dataset, "case_templates")[f"{prefix}__{enzyme_class}__{substrate}__homogeneous_mm_template"]
    assert template["product_map"]["stoichiometric_yield"] == yield_value
    assert template["process_state_metadata"]["config_mode"] == "exploratory"
    assert any("suspended solid_polymer substrate (dry-mass basis)" in text for text in template["limitations"])
    copy = _records(dataset, "enzyme_classes")[f"{prefix}__{enzyme_class}"]
    assert copy["provenance"]["registry_parent_enzyme_class"] == enzyme_class

    study = virtual_experiment(
        fungi="strain_p2", substrates=substrate, environments="c40_ph5", user_data=dataset, registry=base_registry
    )
    assert study.preflight(mode="exploratory")[0].status in {"modelable", "exploratory"}
    assert study.preflight(mode="scientific")[0].status != "modelable"
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    result = study.simulate(mode="exploratory", n_samples=1, seed=4, output_dir=tmp_path / "run", quicklook=False)

    rows = result.time_series()
    substrate_rows = [row for row in rows if row["state_role"] == "substrate"]
    product_rows = [row for row in rows if row["state_role"] == "product"]
    assert {row["units"] for row in substrate_rows} == {row["units"] for row in product_rows} == {"gram / liter"}
    assert {row["time_units"] for row in substrate_rows} == {"hour"}
    times = np.array([float(row["time"]) for row in substrate_rows])
    substrate_values = np.array([float(row["value"]) for row in substrate_rows])
    product_values = np.array([float(row["value"]) for row in product_rows])
    assert substrate_values[0] == pytest.approx(s0)
    assert 0.0 < substrate_values[-1] < s0
    # The apparent law in mass units: Vmax = kcat x E in g/L/h, integrated in closed form.
    expected = _lambert_w_substrate(times, vmax=kcat * enzyme, km=km, s0=s0)
    np.testing.assert_allclose(substrate_values, expected, rtol=1e-6, atol=1e-9)
    # Mass closure through the yield: P = Y (S0 - S) at every time point.
    np.testing.assert_allclose(product_values, yield_value * (s0 - substrate_values), rtol=1e-6, atol=1e-9)

    config = yaml.safe_load(Path(result.screen_result.case_results[0].samples[0].config_path).read_text(encoding="utf-8"))
    (entity,) = config["entities"]["substrates"]
    assert (entity["loader"], entity["data"]["physical_state"]) == ("generic_solid", "solid_polymer")
    assert entity["data"]["bond_types"] == list(SUBSTRATES[substrate][0])
    assert [item["name"] for item in entity["data"]["degradation_products"]] == [product]


def test_the_stated_yield_is_the_users_and_is_not_replaced_by_the_registry_map(
    base_registry: FungModRegistry, tmp_path: Path
) -> None:
    """The registry product map is reference data: the user's stated g/g yield is used as written."""

    dataset = load_user_dataset(
        _write(tmp_path / "data", _dataset_tables(base_registry, "xylan", product_yield="0.9")), registry=base_registry
    )
    template = _records(dataset, "case_templates")["xylan_registry_demo__endo_xylanase__xylan__homogeneous_mm_template"]
    assert template["product_map"]["stoichiometric_yield"] == 0.9


def test_a_product_the_registry_polymer_does_not_declare_is_refused(
    base_registry: FungModRegistry, tmp_path: Path
) -> None:
    """Free xylose is not the product of an endo-xylanase on xylan; the registry declares xylose equivalents."""

    tables = _dataset_tables(base_registry, "xylan")
    tables["substrates.csv"] = tables["substrates.csv"].replace(",D_xylose_equivalent,", ",D_xylose,")
    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(_write(tmp_path / "data", tables), registry=base_registry)
    messages = [
        issue["message"]
        for issue in excinfo.value.issues
        if (issue["file"], issue["row"], issue["column"]) == ("substrates.csv", 2, "product")
    ]
    assert messages and "declares products ['D_xylose_equivalent']" in messages[0]
