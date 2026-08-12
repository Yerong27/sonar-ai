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
    assert "2–6 exact supplied IDs" in explainer.model.prompt
    assert "grouping related stories" in explainer.model.prompt
    assert "return exactly 10 topic_signals" in explainer.model.prompt
    assert "Do not stop after restating" in explainer.model.prompt
    assert explainer.model.generation_config == {
        "response_mime_type": "application/json",
        "max_output_tokens": 4096,
    }
