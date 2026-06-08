from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.registry import (
    AmbiguousResolutionError,
    RegistryResolver,
    ResolutionError,
    load_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_resolver_resolves_exact_fungus_id() -> None:
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    resolved = resolver.resolve_fungus("sabiork_beta_glucosidase_source")

    assert resolved.record_id == "sabiork_beta_glucosidase_source"
    assert resolved.matched_field == "record_id"
    assert resolved.confidence == "exact"


def test_resolver_resolves_fungus_alias() -> None:
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    resolved = resolver.resolve_fungus("beta-glucosidase source")

    assert resolved.record_id == "sabiork_beta_glucosidase_source"
    assert resolved.matched_field in {"display_name", "alias"}


def test_resolver_resolves_case_insensitive_alias() -> None:
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    resolved = resolver.resolve_fungus("BETA-GLUCOSIDASE SOURCE")

    assert resolved.record_id == "sabiork_beta_glucosidase_source"
    assert resolved.confidence == "case_insensitive_exact"


def test_resolver_resolves_substrate_exact_id_and_alias() -> None:
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    assert resolver.resolve_substrate("cellobiose").record_id == "cellobiose"
    assert resolver.resolve_substrate("cellobiose substrate").record_id == "cellobiose"


def test_resolver_resolves_environment_exact_id_and_alias() -> None:
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    assert (
        resolver.resolve_environment("sabiork_reaction_618_selected_conditions").record_id
        == "sabiork_reaction_618_selected_conditions"
    )
    assert resolver.resolve_environment("30C_pH5_assay").record_id == "sabiork_reaction_618_selected_conditions"


def test_resolver_resolves_enzyme_class_and_ec_number() -> None:
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    assert resolver.resolve_enzyme_class("beta_glucosidase").record_id == "beta_glucosidase"
    assert resolver.resolve_enzyme_class("EC 3.2.1.21").record_id == "beta_glucosidase"
    assert resolver.resolve_enzyme_class("3.2.1.21").record_id == "beta_glucosidase"


def test_unknown_name_raises_resolution_error_with_known_terms() -> None:
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    with pytest.raises(ResolutionError, match="Known substrate terms include") as exc_info:
        resolver.resolve_substrate("not in registry")

    assert exc_info.value.record_type == "substrate"
    assert "cellobiose" in exc_info.value.known_terms


def test_ambiguous_alias_raises_with_candidates(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    fungi_path = registry_dir / "fungi" / "fungi.yml"
    data = _yaml_mapping(fungi_path)
    records = cast(list[dict[str, Any]], data["records"])
    for record in records[:2]:
        aliases = list(record.get("aliases") or [])
        aliases.append("shared source alias")
        record["aliases"] = aliases
    fungi_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    resolver = RegistryResolver(load_registry(registry_dir / "registry_index.yml"))

    with pytest.raises(AmbiguousResolutionError, match="shared source alias") as exc_info:
        resolver.resolve_fungus("shared source alias")

    candidate_ids = {candidate.record_id for candidate in exc_info.value.candidates}
    assert candidate_ids == {"toy_fungus_alpha", "generic_cellulase_source"}


def test_resolve_any_returns_only_unambiguous_registry_record() -> None:
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    resolved = resolver.resolve_any("30C_pH5_assay")

    assert resolved.record_type == "environment"
    assert resolved.record_id == "sabiork_reaction_618_selected_conditions"


def test_resolver_does_not_perform_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_urlopen(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("resolver must not call external APIs")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden_urlopen)
    resolver = RegistryResolver(load_registry(REGISTRY_INDEX))

    assert resolver.resolve_substrate("cellobiose substrate").record_id == "cellobiose"


def test_resolver_does_not_mutate_registry_records() -> None:
    registry = load_registry(REGISTRY_INDEX)
    before = registry.to_dict()
    resolver = RegistryResolver(registry)

    resolver.resolve_fungus("beta-glucosidase source")
    resolver.resolve_substrate("cellobiose substrate")
    resolver.resolve_environment("30C_pH5_assay")

    assert registry.to_dict() == before


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
