import pytest
from src.app.models import SearchResult
from src.services.ranking import score_result, rank_results

def test_higher_keyword_overlap_scores_higher():
    query = "redis caching benefits"
    
    # 0 overlap
    res_bad = SearchResult(
        title="Unrelated",
        url="https://example.com/bad",
        content="Nothing about the topic.",
        source="serper"
    )
    
    # High overlap
    res_good = SearchResult(
        title="Redis Caching",
        url="https://example.com/good",
        content="The main benefits of redis caching include speed.",
        source="serper"
    )
    
    score_bad = score_result(res_bad, query)
    score_good = score_result(res_good, query)
    assert score_good > score_bad


def test_serper_scores_higher_than_duckduckgo():
    query = "test"
    content = "test content"
    
    res_serp = SearchResult(title="Test", url="https://x.com/1", content=content, source="serper")
    res_ddg = SearchResult(title="Test", url="https://x.com/2", content=content, source="duckduckgo")
    
    assert score_result(res_serp, query) > score_result(res_ddg, query)


def test_penalize_reddit_url():
    query = "test"
    content = "test content"
    
    # Same source, same content
    res_normal = SearchResult(title="Test", url="https://python.org/post", content=content, source="serper")
    res_reddit = SearchResult(title="Test", url="https://reddit.com/r/python", content=content, source="serper")
    
    assert score_result(res_normal, query) > score_result(res_reddit, query)


def test_duplicate_domains_suppressed():
    query = "test"
    results = [
        SearchResult(title="A", url="https://example.com/1", content="low score", source="duckduckgo"),
        SearchResult(title="B", url="https://example.com/2", content="test test test", source="serper") # higher score
    ]
    
    ranked = rank_results(results, query)
    # Should only return 1 item from example.com
    assert len(ranked) == 1
    # Should keep the one with the higher score (serper + more keywords)
    assert ranked[0].title == "B"


def test_empty_results_handling():
    ranked = rank_results([], "test query")
    assert ranked == []


def test_stable_ranking():
    query = "cache"
    results = [
        SearchResult(title="1", url="http://a.com", content="cache", source="serper"),
        SearchResult(title="2", url="http://b.com", content="nope", source="duckduckgo"),
        SearchResult(title="3", url="http://c.com", content="cache cache", source="serper") # highest
    ]
    
    ranked1 = rank_results(results, query)
    ranked2 = rank_results(results, query)
    
    assert ranked1 == ranked2
    assert ranked1[0].title == "3"


def test_score_assignment():
    query = "test"
    results = [SearchResult(title="Test", url="http://a.com", content="test", source="serper")]
    ranked = rank_results(results, query)
    
    assert len(ranked) == 1
    assert ranked[0].score is not None
    assert ranked[0].score > 0.0


def test_snippet_length_reward():
    query = "test"
    res_short = SearchResult(title="Test", url="http://a.com", content="test", source="serper")
    # A longer snippet should get a slightly higher score
    res_long = SearchResult(title="Test", url="http://b.com", content="test " + "word " * 100, source="serper")
    
    assert score_result(res_long, query) > score_result(res_short, query)
