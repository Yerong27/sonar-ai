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
        "topic_signals": [
            {
                "concept": "Large Language Models",
                "aliases": ["LLM", "LLMs"],
                "supporting_story_ids": ["1"],
            },
            {
                "concept": "Docker Sandboxes",
                "aliases": ["Docker Sandbox"],
                "supporting_story_ids": [],
            },
        ]
    }
    stories = [
        _story("1", "How I use LLMs to learn complex topics", 400),
        _story("2", "Local LLM inference on consumer hardware", 300),
        _story("3", "Benchmarking large language models", 200),
        _story("4", "Docker Sandboxes for AI agents", 150),
        _story("5", "A completely unrelated database story", 500),
        _story("6", "Running coding agents inside a Docker Sandbox", 120),
    ]

    signals = _expanded_keyword_signals(payload, stories)

    assert [signal["keyword"] for signal in signals] == [
        "Large Language Models",
        "Docker Sandboxes",
    ]
    assert signals[0]["story_count"] == 3
    assert {story["story_id"] for story in signals[0]["stories"]} == {"1", "2", "3"}
    assert signals[1]["story_count"] == 2


def test_single_story_concepts_are_not_presented_as_recurring_signals() -> None:
    payload = {
        "topic_signals": [
            {
                "concept": "One-off Product",
                "aliases": [],
                "supporting_story_ids": ["1"],
            }
        ]
    }

    assert _expanded_keyword_signals(
        payload,
        [_story("1", "One-off Product launches today")],
    ) == []


def test_no_title_frequency_fallback_is_created_without_model_concepts() -> None:
    stories = [_story("1", "Show developers a useful command")]

    assert _expanded_keyword_signals({}, stories) == []


def test_legacy_keyword_signals_remain_readable() -> None:
    payload = {
        "keyword_signals": [
            {
                "concept": "Developer Tooling",
                "aliases": [],
                "supporting_story_ids": ["1", "2"],
            }
        ]
    }

    signals = _expanded_keyword_signals(
        payload,
        [_story("1", "A new terminal workflow"), _story("2", "Debugging build tools")],
    )

    assert signals[0]["keyword"] == "Developer Tooling"
    assert signals[0]["story_count"] == 2
