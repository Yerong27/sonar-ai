from sonar.ai.gemini import GeminiExplainer


class _Response:
    text = '{"keyword_signals": []}'


class _RecordingModel:
    def __init__(self) -> None:
        self.prompt = ""

    def generate_content(self, prompt: str) -> _Response:
        self.prompt = prompt
        return _Response()


def test_monitoring_prompt_renders_keyword_signal_schema() -> None:
    explainer = GeminiExplainer.__new__(GeminiExplainer)
    explainer.enabled = True
    explainer.model = _RecordingModel()
    explainer.last_error = None

    result = explainer.summarize_monitoring_snapshot(
        [{"story_id": "101", "title": "A concrete technical story"}]
    )

    assert result == {"keyword_signals": []}
    assert '"concept": "string' in explainer.model.prompt
    assert '"supporting_story_ids": [' in explainer.model.prompt
