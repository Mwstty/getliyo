from app.utils.retry import backoff_seconds


def test_schedule_from_start():
    assert [backoff_seconds(i, 3) for i in range(5)] == [3, 5, 10, 30, 30]
    assert [backoff_seconds(i, 10) for i in range(3)] == [10, 30, 30]
    assert backoff_seconds(0, 99) == 30
