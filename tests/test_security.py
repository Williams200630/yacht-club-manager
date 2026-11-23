from yachtclub.security import hash_password,validate_credentials,validate_phone,verify_password


def test_password_is_hashed_and_verified():
    raw='Sailboat123!'
    hashed=hash_password(raw)
    assert hashed!=raw
    assert verify_password(raw,hashed)
    assert not verify_password('wrong-password',hashed)


def test_password_policy_rejects_short_password():
    try:
        validate_credentials('customer@example.test','abc123')
    except ValueError as exc:
        assert '10 символов' in str(exc)
    else:
        raise AssertionError('Short passwords must be rejected')


def test_contact_validation():
    validate_credentials('customer@example.test','Ocean12345')
    validate_phone('+7 978 123-45-67')
    for invalid in ('no-at-symbol','+7 12'):
        try:
            if '@' in invalid:validate_credentials(invalid,'Ocean12345')
            else:validate_phone(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f'Invalid value accepted: {invalid}')
