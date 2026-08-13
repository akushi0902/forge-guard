"""Tests for the ForgeGuard custom exception hierarchy.

Covers:
    1. ForgeGuardError base class: status_code, error_type, message, details.
    2. Each subclass maps to the correct HTTP status code and error type slug.
    3. Default messages are present for all subclasses.
    4. Custom messages are stored correctly.
    5. details kwarg is propagated.
    6. ForbiddenError carries required_permission and contact_role.
    7. All subclasses are instances of ForgeGuardError and Exception.
"""

from __future__ import annotations

import pytest

from forgeguard.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    ForgeGuardError,
    NotFoundError,
    RateLimitError,
    UnauthorizedError,
)


# ---------------------------------------------------------------------------
# ForgeGuardError base class
# ---------------------------------------------------------------------------

class TestForgeGuardError:
    def test_default_status_and_type(self) -> None:
        err = ForgeGuardError()
        assert err.status_code == 500
        assert err.error_type == "internal_error"

    def test_default_message(self) -> None:
        err = ForgeGuardError()
        assert err.message == "An unexpected error occurred"
        assert str(err) == "An unexpected error occurred"

    def test_custom_message(self) -> None:
        err = ForgeGuardError("Something went wrong")
        assert err.message == "Something went wrong"

    def test_details_default_none(self) -> None:
        err = ForgeGuardError("msg")
        assert err.details is None

    def test_details_propagated(self) -> None:
        d = {"key": "value"}
        err = ForgeGuardError("msg", details=d)
        assert err.details == d

    def test_is_exception(self) -> None:
        assert isinstance(ForgeGuardError(), Exception)


# ---------------------------------------------------------------------------
# NotFoundError
# ---------------------------------------------------------------------------

class TestNotFoundError:
    def test_status_code(self) -> None:
        assert NotFoundError().status_code == 404

    def test_error_type(self) -> None:
        assert NotFoundError().error_type == "not_found"

    def test_default_message_present(self) -> None:
        assert NotFoundError().message != ""

    def test_custom_message(self) -> None:
        err = NotFoundError("Service xyz not found")
        assert err.message == "Service xyz not found"

    def test_is_forgeguard_error(self) -> None:
        assert isinstance(NotFoundError(), ForgeGuardError)
        assert isinstance(NotFoundError(), Exception)


# ---------------------------------------------------------------------------
# UnauthorizedError
# ---------------------------------------------------------------------------

class TestUnauthorizedError:
    def test_status_code(self) -> None:
        assert UnauthorizedError().status_code == 401

    def test_error_type(self) -> None:
        assert UnauthorizedError().error_type == "unauthorized"

    def test_default_message_present(self) -> None:
        assert UnauthorizedError().message != ""

    def test_custom_message(self) -> None:
        err = UnauthorizedError("Token expired")
        assert err.message == "Token expired"

    def test_is_forgeguard_error(self) -> None:
        assert isinstance(UnauthorizedError(), ForgeGuardError)


# ---------------------------------------------------------------------------
# ForbiddenError
# ---------------------------------------------------------------------------

class TestForbiddenError:
    def test_status_code(self) -> None:
        assert ForbiddenError().status_code == 403

    def test_error_type(self) -> None:
        assert ForbiddenError().error_type == "forbidden"

    def test_default_message_present(self) -> None:
        assert ForbiddenError().message != ""

    def test_custom_message(self) -> None:
        err = ForbiddenError("Not allowed here")
        assert err.message == "Not allowed here"

    def test_required_permission_default_empty(self) -> None:
        err = ForbiddenError()
        assert err.required_permission == ""

    def test_required_permission_set(self) -> None:
        err = ForbiddenError(required_permission="service:delete")
        assert err.required_permission == "service:delete"

    def test_contact_role_default(self) -> None:
        err = ForbiddenError()
        assert err.contact_role != ""  # has a sensible default

    def test_contact_role_custom(self) -> None:
        err = ForbiddenError(contact_role="platform admin")
        assert err.contact_role == "platform admin"

    def test_is_forgeguard_error(self) -> None:
        assert isinstance(ForbiddenError(), ForgeGuardError)

    def test_details_propagated(self) -> None:
        err = ForbiddenError(details={"resource": "service-123"})
        assert err.details == {"resource": "service-123"}


# ---------------------------------------------------------------------------
# BadRequestError
# ---------------------------------------------------------------------------

class TestBadRequestError:
    def test_status_code(self) -> None:
        assert BadRequestError().status_code == 400

    def test_error_type(self) -> None:
        assert BadRequestError().error_type == "bad_request"

    def test_default_message_present(self) -> None:
        assert BadRequestError().message != ""

    def test_custom_message(self) -> None:
        err = BadRequestError("Invalid input format")
        assert err.message == "Invalid input format"

    def test_is_forgeguard_error(self) -> None:
        assert isinstance(BadRequestError(), ForgeGuardError)


# ---------------------------------------------------------------------------
# ConflictError
# ---------------------------------------------------------------------------

class TestConflictError:
    def test_status_code(self) -> None:
        assert ConflictError().status_code == 409

    def test_error_type(self) -> None:
        assert ConflictError().error_type == "conflict"

    def test_default_message_present(self) -> None:
        assert ConflictError().message != ""

    def test_custom_message(self) -> None:
        err = ConflictError("Service name already taken")
        assert err.message == "Service name already taken"

    def test_is_forgeguard_error(self) -> None:
        assert isinstance(ConflictError(), ForgeGuardError)


# ---------------------------------------------------------------------------
# RateLimitError
# ---------------------------------------------------------------------------

class TestRateLimitError:
    def test_status_code(self) -> None:
        assert RateLimitError().status_code == 429

    def test_error_type(self) -> None:
        assert RateLimitError().error_type == "rate_limit_exceeded"

    def test_default_message_present(self) -> None:
        assert RateLimitError().message != ""

    def test_custom_message(self) -> None:
        err = RateLimitError("Slow down, cowboy")
        assert err.message == "Slow down, cowboy"

    def test_is_forgeguard_error(self) -> None:
        assert isinstance(RateLimitError(), ForgeGuardError)


# ---------------------------------------------------------------------------
# Cross-class uniqueness
# ---------------------------------------------------------------------------

class TestExceptionUniqueness:
    def test_all_status_codes_distinct(self) -> None:
        codes = [
            NotFoundError().status_code,
            UnauthorizedError().status_code,
            ForbiddenError().status_code,
            BadRequestError().status_code,
            ConflictError().status_code,
            RateLimitError().status_code,
        ]
        assert len(codes) == len(set(codes)), "Each subclass must map to a distinct HTTP status code"

    def test_all_error_types_distinct(self) -> None:
        types = [
            NotFoundError().error_type,
            UnauthorizedError().error_type,
            ForbiddenError().error_type,
            BadRequestError().error_type,
            ConflictError().error_type,
            RateLimitError().error_type,
        ]
        assert len(types) == len(set(types)), "Each subclass must have a distinct error_type slug"

    def test_all_catchable_as_forgeguard_error(self) -> None:
        errors = [
            NotFoundError(),
            UnauthorizedError(),
            ForbiddenError(),
            BadRequestError(),
            ConflictError(),
            RateLimitError(),
        ]
        for err in errors:
            assert isinstance(err, ForgeGuardError), f"{type(err).__name__} must be a ForgeGuardError"
