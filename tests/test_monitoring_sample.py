from sonar.services.collection import _select_monitoring_sample


def _story(story_id: int, feed: str, engagement: int, created_at: int) -> dict:
    return {
        "story_id": str(story_id),
        "source_feed": feed,
        "title": f"Story {story_id}",
        "score": engagement,
        "num_comments": 0,
        "created_at": f"2026-08-11T{created_at:02d}:00:00+00:00",
    }


def test_monitoring_sample_is_bounded_deduplicated_and_feed_aware() -> None:
    stories = [
        *[_story(index, "topstories", 1000 - index, index) for index in range(10)],
        *[_story(index + 20, "newstories", 100 - index, index) for index in range(10)],
        _story(1, "newstories", 1, 23),
    ]

    sample = _select_monitoring_sample(stories, limit=10)

    assert len(sample) == 10
    assert len({story["story_id"] for story in sample}) == 10
    assert {story["source_feed"] for story in sample} == {"topstories", "newstories"}
