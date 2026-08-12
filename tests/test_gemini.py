from sonar.ai.gemini import GeminiExplainer


class _Response:
    text = '{"topic_signals": []}'


class _RecordingModel:
    def __init__(self) -> None:
        self.prompt = ""
        self.generation_config = {}

    def generate_content(self, prompt: str, *, generation_config: dict) -> _Response:
        self.prompt = prompt
        self.generation_config = generation_config
        return _Response()


class _ReviewingModel:
    def __init__(self) -> None:
        self.prompts = []

    def generate_content(self, prompt: str, *, generation_config: dict) -> _Response:
        self.prompts.append(prompt)
        response = _Response()
        if len(self.prompts) == 1:
            response.text = (
                '{"topic_signals":[{"concept":"Software Engineering",'
                '"aliases":[],"supporting_story_ids":["1","2","3"],'
                '"confidence":1.0}],"top_topics":["Software Engineering"]}'
            )
        else:
            response.text = '{"accepted_topics":[]}'
        return response


def test_monitoring_prompt_renders_topic_signal_schema() -> None:
    explainer = GeminiExplainer.__new__(GeminiExplainer)
    explainer.enabled = True
    explainer.model = _RecordingModel()
    explainer.last_error = None

    result = explainer.summarize_monitoring_snapshot(
        [{"story_id": "101", "title": "A concrete technical story"}]
    )

    assert result == {"topic_signals": []}
    assert '"topic_signals": [' in explainer.model.prompt
    assert '"concept": "string' in explainer.model.prompt
    assert '"aliases": [' in explainer.model.prompt
    assert '"supporting_story_ids": [' in explainer.model.prompt
    assert "at least 3 exact supplied story IDs" in explainer.model.prompt
    assert "First cluster the supplied stories" in explainer.model.prompt
    assert "Return between 3 and 8 topic_signals" in explainer.model.prompt
    assert "unclustered_story_ids" in explainer.model.prompt
    assert "Assign a story to at most one topic_signal" in explainer.model.prompt
    assert explainer.model.generation_config == {
        "response_mime_type": "application/json",
        "max_output_tokens": 4096,
    }


def test_monitoring_topics_receive_an_independent_cohesion_review() -> None:
    explainer = GeminiExplainer.__new__(GeminiExplainer)
    explainer.enabled = True
    explainer.model = _ReviewingModel()
    explainer.last_error = None

    result = explainer.summarize_monitoring_snapshot(
        [
            {"story_id": "1", "title": "A language release"},
            {"story_id": "2", "title": "A compiler implementation"},
            {"story_id": "3", "title": "A coding practice"},
        ]
    )

    assert result["topic_signals"] == []
    assert result["top_topics"] == []
    assert len(explainer.model.prompts) == 2
    assert "independent quality reviewer" in explainer.model.prompts[1]
    assert "A broad professional domain is not a topic" in explainer.model.prompts[1]
