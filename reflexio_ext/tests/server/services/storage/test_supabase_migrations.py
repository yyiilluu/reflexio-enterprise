"""Tests for supabase_migrations.py -- pure parsing logic and helpers."""

from unittest.mock import MagicMock, patch


from reflexio_ext.server.services.storage.supabase_migrations import (
    DATA_MIGRATIONS,
    _backfill_table,
    _parse_feedback_content,
    _strip_trailing_dot,
    migrate_20260124120000_structured_feedback_fields,
)


# ---------------------------------------------------------------------------
# _strip_trailing_dot
# ---------------------------------------------------------------------------

class TestStripTrailingDot:
    def test_none_input(self):
        assert _strip_trailing_dot(None) is None

    def test_no_dot(self):
        assert _strip_trailing_dot("hello") == "hello"

    def test_trailing_dot(self):
        assert _strip_trailing_dot("hello.") == "hello"

    def test_trailing_dot_with_space(self):
        assert _strip_trailing_dot("  hello.  ") == "hello"

    def test_multiple_dots_strips_last(self):
        assert _strip_trailing_dot("a.b.c.") == "a.b.c"

    def test_only_dot(self):
        assert _strip_trailing_dot(".") == ""

    def test_empty_string(self):
        assert _strip_trailing_dot("") == ""


# ---------------------------------------------------------------------------
# _parse_feedback_content -- Structured format
# ---------------------------------------------------------------------------

class TestParseFeedbackContentStructured:
    def test_full_structured(self):
        text = 'When: "user asks for help" Do: "provide detailed answer" Don\'t: "ignore the question"'
        do, dont, when = _parse_feedback_content(text)
        assert when == "user asks for help"
        assert do == "provide detailed answer"
        assert dont == "ignore the question"

    def test_when_and_do_only(self):
        text = 'When: "editing code" Do: "use best practices"'
        do, dont, when = _parse_feedback_content(text)
        assert when == "editing code"
        assert do == "use best practices"
        assert dont is None

    def test_when_only(self):
        text = 'When: "the user is upset"'
        do, dont, when = _parse_feedback_content(text)
        assert when == "the user is upset"
        assert do is None
        assert dont is None

    def test_structured_with_trailing_dots(self):
        text = 'When: "condition." Do: "action." Don\'t: "avoid."'
        do, dont, when = _parse_feedback_content(text)
        assert when == "condition"
        assert do == "action"
        assert dont == "avoid"


# ---------------------------------------------------------------------------
# _parse_feedback_content -- Sentence format
# ---------------------------------------------------------------------------

class TestParseFeedbackContentSentence:
    def test_sentence_format(self):
        text = "Use descriptive names instead of single letters when naming variables."
        do, dont, when = _parse_feedback_content(text)
        assert do == "Use descriptive names"
        assert dont == "single letters"
        assert when == "naming variables"

    def test_sentence_format_case_insensitive(self):
        text = "Say hello Instead Of goodbye When greeting users."
        do, dont, when = _parse_feedback_content(text)
        assert do == "Say hello"
        assert dont == "goodbye"
        assert when == "greeting users"

    def test_sentence_with_quotes(self):
        text = '"Provide context instead of bare assertions when writing tests."'
        do, dont, when = _parse_feedback_content(text)
        assert do == "Provide context"
        assert dont == "bare assertions"
        assert when == "writing tests"


# ---------------------------------------------------------------------------
# _parse_feedback_content -- No match
# ---------------------------------------------------------------------------

class TestParseFeedbackContentNoMatch:
    def test_plain_text_no_pattern(self):
        do, dont, when = _parse_feedback_content("just some random text")
        assert do is None
        assert dont is None
        assert when is None

    def test_empty_string(self):
        do, dont, when = _parse_feedback_content("")
        assert do is None
        assert dont is None
        assert when is None


# ---------------------------------------------------------------------------
# _backfill_table
# ---------------------------------------------------------------------------

class TestBackfillTable:
    def test_no_rows(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        parsed, skipped = _backfill_table(cursor, "feedbacks", "feedback_id")
        assert parsed == 0
        assert skipped == 0

    def test_parseable_rows_are_updated(self):
        cursor = MagicMock()
        content = 'When: "user types" Do: "respond"'
        cursor.fetchall.return_value = [("id-1", content)]

        parsed, skipped = _backfill_table(cursor, "feedbacks", "feedback_id")
        assert parsed == 1
        assert skipped == 0
        # The UPDATE call should have been issued
        assert cursor.execute.call_count == 2  # SELECT + UPDATE

    def test_unparseable_rows_are_skipped(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [("id-2", "random text")]

        parsed, skipped = _backfill_table(cursor, "feedbacks", "feedback_id")
        assert parsed == 0
        assert skipped == 1

    def test_mixed_rows(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ("id-1", 'When: "cond" Do: "act"'),
            ("id-2", "no match here"),
            ("id-3", "Use X instead of Y when Z."),
        ]
        parsed, skipped = _backfill_table(cursor, "raw_feedbacks", "raw_feedback_id")
        assert parsed == 2
        assert skipped == 1


# ---------------------------------------------------------------------------
# migrate_20260124120000_structured_feedback_fields
# ---------------------------------------------------------------------------

class TestMigrationFunction:
    @patch(
        "reflexio_ext.server.services.storage.supabase_migrations._backfill_table"
    )
    def test_calls_backfill_for_both_tables(self, mock_backfill):
        mock_backfill.return_value = (5, 2)
        conn = MagicMock()
        cursor = MagicMock()
        migrate_20260124120000_structured_feedback_fields(conn, cursor)
        assert mock_backfill.call_count == 2
        mock_backfill.assert_any_call(cursor, "raw_feedbacks", "raw_feedback_id")
        mock_backfill.assert_any_call(cursor, "feedbacks", "feedback_id")


# ---------------------------------------------------------------------------
# DATA_MIGRATIONS registry
# ---------------------------------------------------------------------------

class TestDataMigrations:
    def test_registry_has_expected_keys(self):
        assert "20260124120000" in DATA_MIGRATIONS
        assert "20260202000000" in DATA_MIGRATIONS

    def test_registry_values_are_callable(self):
        for fn in DATA_MIGRATIONS.values():
            assert callable(fn)
