from sonar.ai.gemini import GeminiExplainer


class _Response:
    text = '{"keyword_signals": []}'


class _RecordingModel:
    def __init__(self) -> None:
        self.prompts = []
        self.generation_config = {}

    def generate_content(self, prompt: str, *, generation_config: dict) -> _Response:
        self.prompts.append(prompt)
        self.generation_config = generation_config
        return _Response()


def test_monitoring_prompt_requests_multiple_standalone_concepts_once() -> None:
    explainer = GeminiExplainer.__new__(GeminiExplainer)
    explainer.enabled = True
    explainer.model = _RecordingModel()
    explainer.last_error = None

    result = explainer.summarize_monitoring_snapshot(
        [{"story_id": "101", "title": "A concrete technical story"}]
    )

    assert result == {"keyword_signals": []}
    assert len(explainer.model.prompts) == 1
    prompt = explainer.model.prompts[0]
    assert '"keyword_signals": [' in prompt
    assert '"concept_type":' in prompt
    assert "Return 8–15 keyword_signals" in prompt
    assert "concepts are not mutually exclusive" in prompt
    assert "headline scaffolding" in prompt
    assert explainer.model.generation_config == {
        "response_mime_type": "application/json",
        "max_output_tokens": 4096,
    }
