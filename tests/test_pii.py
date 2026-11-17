from copilot.pii import redact, restore


def test_card_is_replaced_and_restored_masked() -> None:
    text, mapping = redact("I paid with 4111 1111 1111 1111 yesterday")
    assert "4111" not in text and "[CARD_1]" in text
    assert restore("Your card [CARD_1] was charged", mapping) == "Your card •••• 1111 was charged"


def test_number_failing_luhn_is_not_a_card() -> None:
    # A 16-digit transaction id that fails Luhn stays: the agent needs it.
    text, mapping = redact("Transaction 1234567812345678 is missing")
    assert "1234567812345678" in text and not mapping


def test_email_phone_iban() -> None:
    text, mapping = redact(
        "Mail me at john.doe@example.com or call +971 50 123 4567. IBAN GB82 WEST 1234 5698 7654 32"
    )
    assert "[EMAIL_1]" in text and "[PHONE_1]" in text and "[IBAN_1]" in text
    assert "example.com" not in text and "4567" not in text
    assert mapping["[IBAN_1]"] == "GB82…5432"


def test_amounts_dates_and_leverage_are_not_pii() -> None:
    original = "I deposited 500 USD on 12.11.2026, leverage 1:2000, account 7712345"
    text, mapping = redact(original)
    assert text == original and not mapping
