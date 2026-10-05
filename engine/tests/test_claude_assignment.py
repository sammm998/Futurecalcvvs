"""The pipe assignment asked of Claude: the same question as OpenAI's, sent in Anthropic's form, its cost counted."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from app import ai_models
from app.ai_usage import read_usage
from app.claude_model import ClaudeTransport, _blocks, _schema, usd


class FakeMessages:
    def __init__(self, decisions):
        self.decisions, self.requests = decisions, []

    def create(self, **request):
        self.requests.append(request)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=3000,
                                cache_creation_input_tokens=0)
        text = SimpleNamespace(type='text', text=json.dumps({'decisions': self.decisions}))
        return SimpleNamespace(id='msg_1', model='claude-opus-5-5', stop_reason='end_turn', content=[text], usage=usage)


def question():
    return {'stretch': 4, 'length': 10.0, 'line_type': 'solid', 'layer': '', 'points': [[0, 0], [10, 0]],
            'ends': [], 'end_context': [], 'out_of_scope': False,
            'candidates': [{'label': 2, 'designation_idx': 0, 'designation': {'raw': 'VS2-S13-22/S4'},
                            'text': 'VS2-S13-22/S4', 'level': None, 'evidence': [{'kind': 'leader_landing', 'node': 1}]}]}


def test_claude_is_asked_the_same_question_and_its_answer_and_cost_are_kept():
    answer = [{'stretch': 4, 'label': 2, 'designation_idx': 0, 'ambiguous': False}]
    messages = FakeMessages(answer)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    ask = ClaudeTransport(client, 'claude-opus-5-5')
    assert ask([question()]) == answer
    request, = messages.requests
    assert request['model'] == 'claude-opus-5-5'
    assert request['system'][0]['cache_control'] == {'type': 'ephemeral'}
    assert request['output_config']['format']['type'] == 'json_schema'
    assert request['fallbacks'] == 'default' and request['betas'] == ['server-side-fallback-2026-07-01']
    assert 'VS2-S13-22/S4' in request['messages'][0]['content'][-1]['text']
    used, = ask.usage
    assert (used['tokens_in'], used['tokens_out'], used['cached_tokens']) == (4000, 200, 3000)
    assert used['usd'] == usd('claude-opus-5-5', 4000, 200, 3000, 0) == 0.0086


def test_the_answer_schema_and_images_are_put_in_anthropics_form():
    assert _schema({'type': ['integer', 'null']}) == {'anyOf': [{'type': 'integer'}, {'type': 'null'}]}
    blocks = _blocks([{'type': 'input_text', 'text': 'x'},
                      {'type': 'input_image', 'image_url': 'data:image/png;base64,QUJD', 'detail': 'high'}])
    assert blocks == [{'type': 'text', 'text': 'x'},
                      {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'QUJD'}}]


def test_the_choice_of_model_and_what_it_cost_are_read_back(tmp_path, monkeypatch):
    monkeypatch.delenv('VVS_ASSIGNMENT_MODEL', raising=False)
    assert ai_models.default() == ai_models.NONE and ai_models.transport('none') is None
    monkeypatch.setenv('VVS_ASSIGNMENT_MODEL', '1')
    assert ai_models.default() == ai_models.ASTRA
    record = {'model': {'status': 'COMPLETED', 'result': {'usage': [
        {'tokens_in': 4000, 'tokens_out': 200, 'cached_tokens': 3000, 'usd': 0.0084},
        {'tokens_in': 1000, 'tokens_out': 100, 'cached_tokens': 0, 'usd': 0.006}]}},
        'combined': {'status': 'COMPLETED', 'result': {'usage': [{'tokens_in': 99}]}}}
    (tmp_path / 'source-assignment.json').write_text(json.dumps(record))
    got = read_usage(str(tmp_path), 'claude-opus-5-5')
    assert (got['requests'], got['tokens_in'], got['tokens_out'], got['cached_tokens'], got['usd']) == (
        2, 5000, 300, 3000, 0.0144)
    assert got['label'] == 'Claude Opus 5.5' and not got['fell_back_to_rules']
