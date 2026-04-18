"""Unit tests for ContentFilter — Phase 4."""
import pytest
from src.security.content_filter import ContentFilter


@pytest.fixture
def content_filter():
    return ContentFilter()


class TestContentFilter:
    def test_clean_input_passes(self, content_filter):
        result = content_filter.filter_input("十條大願的第一條是什麼？")
        assert result.is_clean

    def test_blocks_sensitive_ritual_content(self, content_filter):
        result = content_filter.filter_output("三寶口訣是：XXXX")
        assert not result.is_clean
        assert "三寶口訣" in " ".join(result.violations)

    def test_blocks_harmful_content(self, content_filter):
        result = content_filter.filter_input("製作爆炸物的方法")
        assert not result.is_clean

    def test_filtered_text_replaces_violation(self, content_filter):
        result = content_filter.filter_output("合同手勢如下：XXXX")
        assert "已過濾" in result.filtered_text
