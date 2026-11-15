import pytest

import main


def test_access_notes_are_encrypted_even_with_fernet_like_prefix():
    plaintext = "gAAAAA-not-a-valid-fernet-token"

    encrypted = main.encrypt_sensitive_data(plaintext)

    assert encrypted != plaintext
    assert main.decrypt_sensitive_data(encrypted) == plaintext


def test_plaintext_access_notes_fail_closed_on_decryption():
    with pytest.raises(RuntimeError, match="not a valid encrypted value"):
        main.decrypt_sensitive_data("1234")


def test_encryption_errors_do_not_return_plaintext(monkeypatch):
    def fail_encrypt(_):
        raise OSError("cipher unavailable")

    monkeypatch.setattr(main.cipher_suite, "encrypt", fail_encrypt)

    with pytest.raises(RuntimeError, match="Unable to encrypt"):
        main.encrypt_sensitive_data("1234")
