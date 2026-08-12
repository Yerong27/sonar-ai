from sonar.api.main import _expanded_keyword_signals


def _story(story_id: str, title: str, score: int = 100) -> dict:
    return {
        "story_id": story_id,
        "source_feed": "topstories",
        "title": title,
        "score": score,
        "num_comments": 20,
        "permalink": f"https://news.ycombinator.com/item?id={story_id}",
        "url": f"https://example.com/{story_id}",
        "collected_at": "2026-08-11T00:00:00+00:00",
    }


def test_model_concepts_expand_across_the_full_story_window() -> None:
    payload = {
        "keyword_signals": [
            {
                "concept": "Large Language Models",
                "concept_type": "technology",
                "aliases": ["Local LLM Inference", "LLM"],
                "supporting_story_ids": ["1", "2"],
                "confidence": 0.92,
            },
            {
                "concept": "Docker Sandboxes",
                "concept_type": "technology",
                "aliases": ["Agent Sandboxes"],
                "supporting_story_ids": ["4", "5"],
                "confidence": 0.86,
            },
        ]
    }
    stories = [
        _story("1", "How I use LLMs to learn complex topics", 400),
        _story("2", "Local LLM inference on consumer hardware", 300),
        _story("3", "Benchmarking large language models", 200),
        _story("4", "Docker Sandboxes for AI agents", 150),
        _story("5", "Agent Sandboxes for untrusted code", 130),
        _story("6", "Running coding agents inside Docker Sandboxes", 120),
    ]

    signals = _expanded_keyword_signals(payload, stories)

    assert [signal["keyword"] for signal in signals] == [
        "Large Language Models",
        "Docker Sandboxes",
    ]
    assert signals[0]["story_count"] == 3
    assert signals[1]["story_count"] == 3


def test_same_story_may_support_multiple_meaningful_concepts() -> None:
    payload = {
        "keyword_signals": [
            {
                "concept": "Local AI Inference",
                "concept_type": "technical_subject",
                "aliases": ["Local LLM"],
                "supporting_story_ids": ["1", "2"],
                "confidence": 0.9,
            },
            {
                "concept": "Apple Silicon",
                "concept_type": "technology",
                "aliases": [],
                "supporting_story_ids": ["1", "3"],
                "confidence": 0.88,
            },
        ]
    }
    stories = [
        _story("1", "Local LLM inference on Apple Silicon"),
        _story("2", "Local AI inference reaches laptops"),
        _story("3", "Apple Silicon accelerates model serving"),
    ]

    signals = _expanded_keyword_signals(payload, stories)

    assert len(signals) == 2
    assert {signal["keyword"] for signal in signals} == {
        "Local AI Inference",
        "Apple Silicon",
    }


def test_plain_single_word_fragments_are_rejected_without_a_supported_type() -> None:
    payload = {
        "top_keywords": ["During", "Show"],
    }
    stories = [
        _story("1", "During deployment the database failed"),
        _story("2", "Show HN: a database monitor"),
        _story("3", "Show HN: another monitor"),
    ]

    assert _expanded_keyword_signals(payload, stories) == []


def test_specific_single_word_product_can_expand_beyond_one_sampled_story() -> None:
    payload = {
        "keyword_signals": [
            {
                "concept": "Docker",
                "concept_type": "product",
                "aliases": [],
                "supporting_story_ids": ["1"],
                "confidence": 0.9,
            }
        ]
    }

    signals = _expanded_keyword_signals(
        payload,
        [_story("1", "Docker adds agent sandboxes"), _story("2", "Running tools in Docker")],
    )

    assert [signal["keyword"] for signal in signals] == ["Docker"]
    assert signals[0]["story_count"] == 2


def test_fallback_requires_repetition_instead_of_a_word_blacklist() -> None:
    stories = [
        _story("1", "New OpenAI model reaches production"),
        _story("2", "Developers compare OpenAI model latency"),
        _story("3", "During an unrelated launch"),
    ]

    signals = _expanded_keyword_signals({}, stories)

    assert any(signal["keyword"] == "OpenAI" for signal in signals)
    assert all(signal["keyword"] != "During" for signal in signals)
