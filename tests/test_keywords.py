from sonar.api.main import _validated_topic_clusters


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


def test_validated_topics_expand_across_the_full_story_window() -> None:
    payload = {
        "topic_signals": [
            {
                "concept": "Large Language Models",
                "aliases": ["Local LLM Inference"],
                "supporting_story_ids": ["1", "2", "3"],
                "confidence": 0.92,
            },
            {
                "concept": "Docker Sandboxes",
                "aliases": ["Agent Sandboxes"],
                "supporting_story_ids": ["4", "5", "6"],
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
        _story("6", "Running coding agents inside a Docker Sandbox", 120),
        _story("7", "Local LLM Inference reaches laptops", 110),
    ]

    signals = _validated_topic_clusters(payload, stories)

    assert [signal["keyword"] for signal in signals] == [
        "Large Language Models",
        "Docker Sandboxes",
    ]
    assert signals[0]["story_count"] == 4
    assert {story["story_id"] for story in signals[0]["stories"]} == {"1", "2", "3", "7"}
    assert signals[1]["story_count"] == 3


def test_topics_with_fewer_than_three_stories_are_not_presented() -> None:
    payload = {
        "topic_signals": [
            {
                "concept": "One-off Product",
                "aliases": [],
                "supporting_story_ids": ["1", "2"],
                "confidence": 0.95,
            }
        ]
    }

    assert _validated_topic_clusters(
        payload,
        [_story("1", "One-off Product launches today"), _story("2", "One-off Product review")],
    ) == []


def test_no_title_frequency_fallback_is_created_without_model_concepts() -> None:
    stories = [_story("1", "Show developers a useful command")]

    assert _validated_topic_clusters({}, stories) == []


def test_low_confidence_topics_are_rejected() -> None:
    payload = {
        "topic_signals": [
            {
                "concept": "Developer Tooling",
                "aliases": [],
                "supporting_story_ids": ["1", "2", "3"],
                "confidence": 0.4,
            }
        ]
    }

    signals = _validated_topic_clusters(
        payload,
        [
            _story("1", "A new terminal workflow"),
            _story("2", "Debugging build tools"),
            _story("3", "A new compiler"),
        ],
    )

    assert signals == []


def test_overlapping_topics_do_not_reuse_the_same_primary_evidence() -> None:
    payload = {
        "topic_signals": [
            {
                "concept": "Local AI Inference",
                "aliases": [],
                "supporting_story_ids": ["1", "2", "3", "4"],
                "confidence": 0.95,
            },
            {
                "concept": "AI Hardware Systems",
                "aliases": [],
                "supporting_story_ids": ["2", "3", "4", "5"],
                "confidence": 0.9,
            },
        ]
    }
    stories = [_story(str(index), f"Story {index}") for index in range(1, 6)]

    signals = _validated_topic_clusters(payload, stories)

    assert [signal["keyword"] for signal in signals] == ["Local AI Inference"]
