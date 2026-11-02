from app.utils.url_normalize import normalize_url


def test_case_and_trailing_slash_equivalence():
    a = normalize_url("HTTPS://Example.COM/Path/")
    b = normalize_url("https://example.com/Path")
    assert a == b


def test_tracking_params_removed():
    a = normalize_url("https://example.com/video?id=1&utm_source=tw&fbclid=abc")
    b = normalize_url("https://example.com/video?id=1")
    assert a == b


def test_meaningful_params_preserved():
    # YouTube'un 'si' parametresi gibi anlamlı olabilecek parametreler silinmemeli.
    a = normalize_url("https://youtu.be/abc123?si=XYZ")
    b = normalize_url("https://youtu.be/abc123")
    assert a != b


def test_param_order_independent():
    a = normalize_url("https://example.com/x?b=2&a=1")
    b = normalize_url("https://example.com/x?a=1&b=2")
    assert a == b


def test_fragment_stripped():
    a = normalize_url("https://example.com/x#section")
    b = normalize_url("https://example.com/x")
    assert a == b


def test_distinct_content_stays_distinct():
    a = normalize_url("https://example.com/video/1")
    b = normalize_url("https://example.com/video/2")
    assert a != b
