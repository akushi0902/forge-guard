"""Unit tests for the severity classification framework (WO-036).

Covers:
  - SeverityLevel enum values and case-insensitive factory
  - SeverityMetadata dataclass immutability and field values
  - SEVERITY_REGISTRY completeness and Decimal precision
  - SeverityClassifier methods: classify_finding, get_severity_metadata,
    is_escalation_required, numeric_weight, sla_hours
  - Escalation logic edge cases (CRITICAL+security vs CRITICAL+other dimension)
  - Error handling for unknown severity strings
  - SeverityResponse Pydantic schema serialisation

Run:
    pytest tests/unit/services/test_severity.py -v
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from forgeguard.services.domain.severity import (
    SEVERITY_ORDER,
    SEVERITY_REGISTRY,
    SeverityClassifier,
    SeverityLevel,
    SeverityMetadata,
)


# ===========================================================================
# SeverityLevel enum
# ===========================================================================

class TestSeverityLevelEnum:
    def test_four_values_defined(self):
        assert len(SeverityLevel) == 4

    def test_values_are_lowercase(self):
        for level in SeverityLevel:
            assert level.value == level.value.lower()

    def test_value_strings(self):
        assert SeverityLevel.CRITICAL == "critical"
        assert SeverityLevel.HIGH == "high"
        assert SeverityLevel.MEDIUM == "medium"
        assert SeverityLevel.LOW == "low"

    def test_from_string_uppercase(self):
        assert SeverityLevel.from_string("CRITICAL") == SeverityLevel.CRITICAL
        assert SeverityLevel.from_string("HIGH") == SeverityLevel.HIGH
        assert SeverityLevel.from_string("MEDIUM") == SeverityLevel.MEDIUM
        assert SeverityLevel.from_string("LOW") == SeverityLevel.LOW

    def test_from_string_lowercase(self):
        assert SeverityLevel.from_string("critical") == SeverityLevel.CRITICAL
        assert SeverityLevel.from_string("low") == SeverityLevel.LOW

    def test_from_string_mixed_case(self):
        assert SeverityLevel.from_string("Critical") == SeverityLevel.CRITICAL
        assert SeverityLevel.from_string("High") == SeverityLevel.HIGH

    def test_from_string_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid_severity"):
            SeverityLevel.from_string("invalid_severity")

    def test_from_string_error_lists_valid_values(self):
        with pytest.raises(ValueError) as exc_info:
            SeverityLevel.from_string("blocker")
        message = str(exc_info.value)
        assert "critical" in message
        assert "high" in message
        assert "medium" in message
        assert "low" in message

    def test_str_enum_equality_with_string(self):
        assert SeverityLevel.CRITICAL == "critical"
        assert "critical" == SeverityLevel.CRITICAL

    def test_severity_order_tuple_length(self):
        assert len(SEVERITY_ORDER) == 4

    def test_severity_order_descending_by_weight(self):
        weights = [SEVERITY_REGISTRY[level].numeric_weight for level in SEVERITY_ORDER]
        assert weights == sorted(weights, reverse=True)


# ===========================================================================
# SeverityMetadata dataclass
# ===========================================================================

class TestSeverityMetadata:
    def test_frozen_dataclass_immutable(self):
        meta = SEVERITY_REGISTRY[SeverityLevel.CRITICAL]
        with pytest.raises((AttributeError, TypeError)):
            meta.numeric_weight = Decimal("0.5")  # type: ignore[misc]

    def test_critical_metadata_values(self):
        meta = SEVERITY_REGISTRY[SeverityLevel.CRITICAL]
        assert meta.level == SeverityLevel.CRITICAL
        assert meta.display_label == "Critical"
        assert meta.numeric_weight == Decimal("1.0")
        assert meta.color_code == "#DC2626"
        assert meta.escalation_required is True
        assert meta.sla_hours == 48

    def test_high_metadata_values(self):
        meta = SEVERITY_REGISTRY[SeverityLevel.HIGH]
        assert meta.level == SeverityLevel.HIGH
        assert meta.display_label == "High"
        assert meta.numeric_weight == Decimal("0.7")
        assert meta.color_code == "#F59E0B"
        assert meta.escalation_required is False
        assert meta.sla_hours == 120

    def test_medium_metadata_values(self):
        meta = SEVERITY_REGISTRY[SeverityLevel.MEDIUM]
        assert meta.level == SeverityLevel.MEDIUM
        assert meta.display_label == "Medium"
        assert meta.numeric_weight == Decimal("0.4")
        assert meta.color_code == "#3B82F6"
        assert meta.escalation_required is False
        assert meta.sla_hours == 240

    def test_low_metadata_values(self):
        meta = SEVERITY_REGISTRY[SeverityLevel.LOW]
        assert meta.level == SeverityLevel.LOW
        assert meta.display_label == "Low"
        assert meta.numeric_weight == Decimal("0.2")
        assert meta.color_code == "#6B7280"
        assert meta.escalation_required is False
        assert meta.sla_hours == 480


# ===========================================================================
# SEVERITY_REGISTRY
# ===========================================================================

class TestSeverityRegistry:
    def test_registry_has_all_four_levels(self):
        for level in SeverityLevel:
            assert level in SEVERITY_REGISTRY

    def test_registry_is_immutable(self):
        import types
        assert isinstance(SEVERITY_REGISTRY, types.MappingProxyType)

    def test_numeric_weights_are_decimal_type(self):
        for meta in SEVERITY_REGISTRY.values():
            assert isinstance(meta.numeric_weight, Decimal), (
                f"Expected Decimal for {meta.level}, got {type(meta.numeric_weight)}"
            )

    def test_numeric_weights_are_not_float(self):
        for meta in SEVERITY_REGISTRY.values():
            assert not isinstance(meta.numeric_weight, float)

    def test_weights_ordered_critical_gt_high_gt_medium_gt_low(self):
        assert (
            SEVERITY_REGISTRY[SeverityLevel.CRITICAL].numeric_weight
            > SEVERITY_REGISTRY[SeverityLevel.HIGH].numeric_weight
            > SEVERITY_REGISTRY[SeverityLevel.MEDIUM].numeric_weight
            > SEVERITY_REGISTRY[SeverityLevel.LOW].numeric_weight
        )

    def test_weights_within_range(self):
        for meta in SEVERITY_REGISTRY.values():
            assert Decimal("0.0") < meta.numeric_weight <= Decimal("1.0")

    def test_sla_hours_ordered_ascending(self):
        assert (
            SEVERITY_REGISTRY[SeverityLevel.CRITICAL].sla_hours
            < SEVERITY_REGISTRY[SeverityLevel.HIGH].sla_hours
            < SEVERITY_REGISTRY[SeverityLevel.MEDIUM].sla_hours
            < SEVERITY_REGISTRY[SeverityLevel.LOW].sla_hours
        )

    def test_only_critical_has_escalation_required_true(self):
        for level, meta in SEVERITY_REGISTRY.items():
            if level == SeverityLevel.CRITICAL:
                assert meta.escalation_required is True
            else:
                assert meta.escalation_required is False, (
                    f"{level} should not have escalation_required=True"
                )

    def test_no_floating_point_drift_in_weighted_sum(self):
        """Decimal weights must sum without floating-point drift."""
        total = sum(meta.numeric_weight for meta in SEVERITY_REGISTRY.values())
        # Sum of 1.0 + 0.7 + 0.4 + 0.2 = 2.3 exactly
        assert total == Decimal("2.3")


# ===========================================================================
# SeverityClassifier
# ===========================================================================

class TestSeverityClassifierClassifyFinding:
    def test_string_input_lowercase(self):
        assert SeverityClassifier.classify_finding("critical") == SeverityLevel.CRITICAL
        assert SeverityClassifier.classify_finding("high") == SeverityLevel.HIGH
        assert SeverityClassifier.classify_finding("medium") == SeverityLevel.MEDIUM
        assert SeverityClassifier.classify_finding("low") == SeverityLevel.LOW

    def test_string_input_uppercase(self):
        assert SeverityClassifier.classify_finding("CRITICAL") == SeverityLevel.CRITICAL
        assert SeverityClassifier.classify_finding("HIGH") == SeverityLevel.HIGH

    def test_string_input_mixed_case(self):
        assert SeverityClassifier.classify_finding("Medium") == SeverityLevel.MEDIUM

    def test_enum_input_passthrough(self):
        assert SeverityClassifier.classify_finding(SeverityLevel.HIGH) == SeverityLevel.HIGH

    def test_unknown_string_raises_value_error(self):
        with pytest.raises(ValueError):
            SeverityClassifier.classify_finding("catastrophic")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            SeverityClassifier.classify_finding("")


class TestSeverityClassifierGetMetadata:
    @pytest.mark.parametrize("level", list(SeverityLevel))
    def test_returns_metadata_for_all_levels(self, level: SeverityLevel):
        meta = SeverityClassifier.get_severity_metadata(level)
        assert isinstance(meta, SeverityMetadata)
        assert meta.level == level

    def test_accepts_string_input(self):
        meta = SeverityClassifier.get_severity_metadata("critical")
        assert meta.level == SeverityLevel.CRITICAL

    def test_unknown_string_raises_value_error(self):
        with pytest.raises(ValueError):
            SeverityClassifier.get_severity_metadata("unknown")


class TestSeverityClassifierEscalation:
    """is_escalation_required: CRITICAL + security → True; everything else → False."""

    def test_critical_security_requires_escalation(self):
        assert SeverityClassifier.is_escalation_required("critical", "security") is True

    def test_critical_code_quality_no_escalation(self):
        assert SeverityClassifier.is_escalation_required("critical", "code_quality") is False

    def test_critical_test_coverage_no_escalation(self):
        assert SeverityClassifier.is_escalation_required("critical", "test_coverage") is False

    def test_critical_documentation_no_escalation(self):
        assert SeverityClassifier.is_escalation_required("critical", "documentation") is False

    def test_critical_operations_readiness_no_escalation(self):
        assert SeverityClassifier.is_escalation_required("critical", "operations_readiness") is False

    def test_high_security_no_escalation(self):
        assert SeverityClassifier.is_escalation_required("high", "security") is False

    def test_medium_security_no_escalation(self):
        assert SeverityClassifier.is_escalation_required("medium", "security") is False

    def test_low_security_no_escalation(self):
        assert SeverityClassifier.is_escalation_required("low", "security") is False

    def test_accepts_severity_level_enum_input(self):
        assert SeverityClassifier.is_escalation_required(SeverityLevel.CRITICAL, "security") is True
        assert SeverityClassifier.is_escalation_required(SeverityLevel.HIGH, "security") is False

    def test_case_insensitive_severity_input(self):
        assert SeverityClassifier.is_escalation_required("CRITICAL", "security") is True


class TestSeverityClassifierHelpers:
    @pytest.mark.parametrize("severity, expected_weight", [
        ("critical", Decimal("1.0")),
        ("high", Decimal("0.7")),
        ("medium", Decimal("0.4")),
        ("low", Decimal("0.2")),
    ])
    def test_numeric_weight(self, severity: str, expected_weight: Decimal):
        assert SeverityClassifier.numeric_weight(severity) == expected_weight

    def test_numeric_weight_returns_decimal(self):
        result = SeverityClassifier.numeric_weight("high")
        assert isinstance(result, Decimal)

    @pytest.mark.parametrize("severity, expected_sla", [
        ("critical", 48),
        ("high", 120),
        ("medium", 240),
        ("low", 480),
    ])
    def test_sla_hours(self, severity: str, expected_sla: int):
        assert SeverityClassifier.sla_hours(severity) == expected_sla


# ===========================================================================
# SeverityResponse Pydantic schema
# ===========================================================================

class TestSeverityResponseSchema:
    def test_from_metadata_critical(self):
        from forgeguard.api.schemas.severity import SeverityResponse

        meta = SEVERITY_REGISTRY[SeverityLevel.CRITICAL]
        resp = SeverityResponse.from_metadata(meta)
        assert resp.level == SeverityLevel.CRITICAL
        assert resp.display_label == "Critical"
        assert resp.numeric_weight == Decimal("1.0")
        assert resp.color_code == "#DC2626"
        assert resp.escalation_required is True
        assert resp.sla_hours == 48

    def test_from_metadata_all_levels(self):
        from forgeguard.api.schemas.severity import SeverityResponse

        for level in SeverityLevel:
            meta = SEVERITY_REGISTRY[level]
            resp = SeverityResponse.from_metadata(meta)
            assert resp.level == level

    def test_json_serialisation(self):
        from forgeguard.api.schemas.severity import SeverityResponse

        meta = SEVERITY_REGISTRY[SeverityLevel.HIGH]
        resp = SeverityResponse.from_metadata(meta)
        data = resp.model_dump()
        assert data["level"] == "high"
        assert data["sla_hours"] == 120
        assert data["escalation_required"] is False
