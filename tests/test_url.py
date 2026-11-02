import pytest

from app.utils.errors import UserError
from app.utils.validators import is_valid_url, validate_url


def test_valid():
    assert validate_url("https://youtu.be/abc") == "https://youtu.be/abc"
    assert validate_url("youtube.com/watch?v=1") == "https://youtube.com/watch?v=1"


@pytest.mark.parametrize("bad", ["", "   ", "file:///c:/x.exe", "javascript:alert(1)", "ftp://x.com/a", "https://localhost", "abc", "https://a b.com"])
def test_invalid(bad):
    assert not is_valid_url(bad)
    with pytest.raises(UserError):
        validate_url(bad)
