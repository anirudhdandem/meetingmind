"""Regression tests for the auth primitives in app.core.security.

The one-time code is the delicate part. It has only a million possible values, so the
things worth pinning down are that it's drawn uniformly from the full keyspace (a
digit-by-digit implementation that dropped leading zeros would quietly shrink it), that
it survives the mangling mail clients apply, and that a non-numeric string can never
match a stored hash.
"""

import pytest

from app.core import security as sec


def test_password_round_trip():
    h = sec.hash_password("correct horse battery staple")
    assert sec.verify_password("correct horse battery staple", h)
    assert not sec.verify_password("wrong horse battery staple", h)


def test_verify_password_tolerates_malformed_hash():
    assert not sec.verify_password("anything", "not-an-argon2-hash")


def test_needs_rehash_is_false_for_a_fresh_hash():
    assert not sec.needs_rehash(sec.hash_password("fresh"))


def test_session_token_hash_is_stable_and_distinct():
    a, b = sec.new_session_token(), sec.new_session_token()
    assert a != b
    assert sec.hash_session_token(a) == sec.hash_session_token(a)
    assert sec.hash_session_token(a) != sec.hash_session_token(b)


# --- One-time codes -----------------------------------------------------------


def test_otp_code_has_the_requested_length():
    assert all(len(sec.new_otp_code(6)) == 6 for _ in range(200))


def test_otp_code_is_all_digits():
    assert all(sec.new_otp_code(6).isdigit() for _ in range(200))


def test_otp_code_rejects_a_guessable_length():
    with pytest.raises(ValueError):
        sec.new_otp_code(3)


def test_otp_code_can_start_with_zero():
    """Leading zeros must be preserved: 000123 is a legal code, and an implementation
    that stringified an int would emit it as '123' and lose ~10% of the keyspace."""
    codes = {sec.new_otp_code(4) for _ in range(4000)}
    assert any(c.startswith("0") for c in codes)


def test_otp_round_trip():
    code = sec.new_otp_code(6)
    h = sec.hash_otp_code(code)
    assert sec.verify_otp_code(code, h)


def test_otp_rejects_a_different_code():
    h = sec.hash_otp_code("123456")
    assert not sec.verify_otp_code("123457", h)


@pytest.mark.parametrize("typed", [" 123456 ", "123 456", "123 456"])
def test_otp_tolerates_whitespace_from_mail_clients(typed):
    assert sec.verify_otp_code(typed, sec.hash_otp_code("123456"))


@pytest.mark.parametrize("bad", ["", "abcdef", "12345a", "!@#$%^"])
def test_otp_rejects_non_numeric_input(bad):
    assert not sec.verify_otp_code(bad, sec.hash_otp_code("123456"))


def test_otp_hash_is_not_the_code():
    assert "123456" not in sec.hash_otp_code("123456")
