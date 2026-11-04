from app import security


def test_generate_otp():
    otp = security.generate_otp()

    assert len(otp) == 6
    assert otp.isdigit()


def test_generate_otp_custom_length():
    otp = security.generate_otp(8)

    assert len(otp) == 8
    assert otp.isdigit()


def test_hash_and_verify_otp():
    otp = "123456"
    verification_id = "test-verification"

    hashed = security.hash_otp(otp, verification_id)

    assert hashed != otp
    assert security.verify_otp_hash(
        otp,
        verification_id,
        hashed
    )


def test_verify_wrong_otp():
    otp = "123456"
    verification_id = "test-verification"

    hashed = security.hash_otp(otp, verification_id)

    assert not security.verify_otp_hash(
        "999999",
        verification_id,
        hashed
    )


def test_verify_wrong_verification_id():
    otp = "123456"
    verification_id = "test-verification"

    hashed = security.hash_otp(otp, verification_id)

    assert not security.verify_otp_hash(
        otp,
        "wrong-verification-id",
        hashed
    )


def test_new_hold_token():
    token = security.new_hold_token()

    assert isinstance(token, str)
    assert len(token) == 32


def test_hold_tokens_are_unique():
    token1 = security.new_hold_token()
    token2 = security.new_hold_token()

    assert token1 != token2


def test_sign_and_verify_order():
    order_id = "order_test123"
    payment_id = "payment_test123"

    signature = security.sign_order(
        order_id,
        payment_id
    )

    assert isinstance(signature, str)
    assert security.verify_signature(
        order_id,
        payment_id,
        signature
    )


def test_invalid_payment_signature():
    assert not security.verify_signature(
        "order_test123",
        "payment_test123",
        "invalid-signature"
    )


def test_wrong_payment_id():
    order_id = "order_test123"
    payment_id = "payment_test123"

    signature = security.sign_order(
        order_id,
        payment_id
    )

    assert not security.verify_signature(
        order_id,
        "wrong-payment",
        signature
    )