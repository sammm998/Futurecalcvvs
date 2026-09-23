"""Explicit PipeStudio model assignment transport; no VVS5 settlement rules."""
import json
import os
import threading
from pathlib import Path


def connection_settings():
    key=os.environ.get('OPENAI_API_KEY','').strip()
    model=os.environ.get('OPENAI_MODEL','gpt-6-astra')
    if key:return key,model
    filename=os.environ.get('VVS_OPENAI_CONFIG_FILE')
    if not filename:return None,model
    try:
        path=Path(filename)
        if path.stat().st_mode & 0o077:return None,model
        saved=json.loads(path.read_text())
        return str(saved.get('api_key','')).strip() or None, str(saved.get('model') or model)
    except (OSError, ValueError, TypeError):
        return None,model


def configured():
    return bool(connection_settings()[0])


class AssignmentTransport:
    def __init__(self, client, model, style=None, page=None, request_cache=None):
        from .model_request_cache import ModelRequestCache
        self.request_cache = request_cache if request_cache is not None else ModelRequestCache()
        self.client = client
        self.model = model
        self.usage = []
        self.candidate_aliases = []
        self.lock = threading.Lock()
        self.style = style or {"rules": []}
        self.page = page

    def for_style(self, style):
        return AssignmentTransport(self.client, self.model, style, self.page, self.request_cache)

    def for_page(self, page):
        return AssignmentTransport(self.client, self.model, self.style, (page.source_path, page.info.index), self.request_cache)

    def __call__(self, questions):
        from vvs_engine.source_rules.pipestudio.final_bind import SYSTEM, SCHEMA
        from vvs_engine.source_rules.pipestudio.assignment_payload import FORMAT, pack, serialize
        from vvs_engine.source_rules.model_payload import FORMAT as ALIAS_FORMAT, group_equivalent_candidates
        grouped, aliases = group_equivalent_candidates(questions)
        from vvs_engine.source_rules.swedish import label_facts
        for question in grouped:
            for candidate in question.get('candidates', []):
                candidate['swedish_interpretation'] = label_facts({'designations': [candidate.get('designation', {})]})
        content = serialize(pack(grouped))
        images = []
        if self.page and self.page[0] and questions:
            from .drawing_evidence import visual_evidence
            visual, images = visual_evidence(*self.page, questions)
            content = [{"type":"input_text","text":content}] + visual
        request = dict(
            model=self.model, store=False, max_output_tokens=12000,
            reasoning={'effort': os.environ.get('STUDIO_ASTRA_EFFORT', 'medium')},
            input=[{'role': 'system', 'content': SYSTEM + '\n' + FORMAT + '\n' + ALIAS_FORMAT + '\nSTYLE CONVENTIONS:\n' + serialize(self.style.get('rules', [])) + '\nMEASURED DRAWING FEATURES (observations, not ownership rules):\n' + serialize(self.style.get('observed_features', {}))},
                   {'role': 'user', 'content': content}],
            text={'format': {'type': 'json_schema', 'name': 'pipe_assignments',
                             'strict': True, 'schema': SCHEMA}})
        def produce():
            response = self.client.responses.create(**request)
            if response.status != 'completed':
                raise RuntimeError('Model assignment did not complete')
            if not isinstance(json.loads(response.output_text).get('decisions'), list):
                raise ValueError('Invalid assignment response')
            return response
        response, reused = self.request_cache.run(request, produce)
        u = response.usage
        with self.lock:
            self.candidate_aliases.extend(aliases)
            self.usage.append({'model': response.model, 'response_id': response.id,
                'tokens_in': 0 if reused else u.input_tokens if u else None,
                'tokens_out': 0 if reused else u.output_tokens if u else None,
                'cached_tokens': 0 if reused else getattr(getattr(u, 'input_tokens_details', None), 'cached_tokens', 0),
                'request_reused': reused, 'drawing_images': images})
        if response.status != 'completed':
            raise RuntimeError('Model assignment did not complete')
        decisions = json.loads(response.output_text)['decisions']
        if not isinstance(decisions, list):
            raise ValueError('Invalid assignment response')
        return decisions


def transport():
    key, model = connection_settings()
    if not key:
        return None
    from openai import OpenAI
    # A request that has not answered in a minute is split and asked again in smaller pieces by the assignment
    # (engine source_rules/dual.py), which is faster than waiting on it or letting the client repeat it whole.
    return AssignmentTransport(OpenAI(api_key=key, timeout=60, max_retries=0), model)
