import pytest

from whotalksitron.retry import RetryExhausted, retry_with_backoff


class FlakyError(Exception):
    pass


def test_retry_succeeds_on_first_try():
    call_count = 0

    def succeeds():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = retry_with_backoff(succeeds, retries=3, retry_on=(FlakyError,))
    assert result == "ok"
    assert call_count == 1


def test_retry_succeeds_after_failures():
    call_count = 0

    def fails_twice():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise FlakyError("transient")
        return "recovered"

    result = retry_with_backoff(
        fails_twice, retries=3, retry_on=(FlakyError,), base_delay=0.01,
    )
    assert result == "recovered"
    assert call_count == 3


def test_retry_exhausted():
    def always_fails():
        raise FlakyError("permanent")

    with pytest.raises(RetryExhausted) as exc_info:
        retry_with_backoff(
            always_fails, retries=2, retry_on=(FlakyError,), base_delay=0.01,
        )
    assert isinstance(exc_info.value.__cause__, FlakyError)


def test_retry_does_not_catch_unexpected_errors():
    def wrong_error():
        raise ValueError("unexpected")

    with pytest.raises(ValueError, match="unexpected"):
        retry_with_backoff(
            wrong_error, retries=3, retry_on=(FlakyError,), base_delay=0.01,
        )


def test_retry_logs_attempts(caplog):
    import logging
    call_count = 0

    def fails_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise FlakyError("once")
        return "ok"

    with caplog.at_level(logging.INFO, logger="whotalksitron.retry"):
        retry_with_backoff(
            fails_once, retries=3, retry_on=(FlakyError,), base_delay=0.01,
        )

    assert any("Retry 1/3" in r.message for r in caplog.records)
