from unittest.mock import Mock, patch

from memory.structured_log_interface import MemoryJobLogContext, memory_job_log_context


def test_memory_job_log_context_sets_trace_commits_and_resets() -> None:
    logger = Mock()
    with patch("memory.structured_log_interface.structured_log_module.StructuredLogger", return_value=logger):
        with MemoryJobLogContext("trace-1"):
            assert logger._req_id == "trace-1"
        logger.commit.assert_called_once()


def test_memory_job_log_context_allows_missing_trace_id_and_resets_on_exception() -> None:
    logger = Mock()
    with patch("memory.structured_log_interface.structured_log_module.StructuredLogger", return_value=logger):
        try:
            with memory_job_log_context(None):
                raise ValueError("boom")
        except ValueError:
            pass

    assert "_req_id" not in logger.__dict__
    logger.commit.assert_called_once()