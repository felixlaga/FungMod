from __future__ import annotations

from fungal_model.core.validators import LimitingCase, LimitingCaseSuite, ValidationResult


def test_limiting_case_suite_runs_registered_cases() -> None:
    suite = LimitingCaseSuite(
        [
            LimitingCase(
                name="identity",
                description="A minimal case used to verify suite plumbing.",
                run=lambda: 1,
                validate=lambda value: ValidationResult(
                    name="identity_check",
                    passed=value == 1,
                    message="Identity value was preserved.",
                ),
            )
        ]
    )

    results = suite.run()

    assert len(results) == 1
    assert results[0].passed

