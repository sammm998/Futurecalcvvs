"""Realtime minting stays private; drawing actions remain a bounded contract."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))


def test_session_only_returns_ephemeral_secret(monkeypatch):
    from app import live_agent, source_model
    import openai
    monkeypatch.setattr(source_model, 'connection_settings', lambda: ('private-key', 'takeoff-model'))
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(value='ek_short', expires_at=123)
    monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: SimpleNamespace(realtime=SimpleNamespace(client_secrets=SimpleNamespace(create=create))))
    got = live_agent.create_session()
    assert got['value'] == 'ek_short' and 'private-key' not in str(got)
    assert captured['expires_after']['seconds'] == 60
    assert captured['session']['model'] != 'takeoff-model'
    assert captured['session']['audio']['input']['turn_detection']['interrupt_response'] is True
    assert captured['session']['tools'][0]['parameters']['additionalProperties'] is False
    assert captured['session']['audio']['input']['transcription']['language'] == 'sv'
    live_agent.create_session(language='en')
    assert captured['session']['audio']['input']['transcription']['language'] == 'en'
    assert 'Speak natural, concise English' in captured['session']['instructions']
    assert 'Tala naturlig, kort svenska' not in captured['session']['instructions']


def test_missing_key_does_not_make_network_request(monkeypatch):
    import pytest
    from app import live_agent, source_model
    monkeypatch.setattr(source_model, 'connection_settings', lambda: (None, 'model'))
    with pytest.raises(ValueError, match='anslutning saknas'):
        live_agent.create_session()
