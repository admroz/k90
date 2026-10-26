"""Optional subscription-backed Responses conversation; never falls back to API keys."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from profiling import span

from responses_api import FunctionCall, Turn, _input_messages
from subscription_protocol import API_ORIGIN, ProbeError, request_json


class SubscriptionError(RuntimeError):
    """Fixed diagnostic codes, never provider exception/body text."""


class SubscriptionConversation:
    def __init__(self, model, messages, tools=None, *, token_store, policy,
                 request=None, reasoning_effort=None):
        self.model = model.removeprefix('openai/')
        self.token_store = token_store
        self.policy = policy
        self.request = request or request_json
        self.reasoning_effort = reasoning_effort
        # Validate original structure before normalization can discard restrictions.
        with span('filtering'):
            messages = self.policy.sanitize(messages)
        self.instructions = '\n\n'.join(m['content'] for m in messages if m.get('role') == 'system')
        self.input = _input_messages([m for m in messages if m.get('role') != 'system'])
        self.tool_names = set()
        functions = []
        for tool in tools or []:
            if tool.get('type') != 'function' or not isinstance(tool.get('function'), dict):
                raise SubscriptionError('invalid_tool_schema')
            function = deepcopy(tool['function'])
            if not isinstance(function.get('name'), str):
                raise SubscriptionError('invalid_tool_schema')
            self.tool_names.add(function['name'])
            functions.append({'type': 'function', **function, 'strict': False})
        self.tools = ([{'type': 'namespace', 'name': 'k90',
                        'description': 'Tools explicitly registered by this k90 instance.',
                        'tools': functions}] if functions else [])
        self._model_checked = False

    def complete(self):
        body = {'model': self.model, 'input': deepcopy(self.input),
                'instructions': self.instructions, 'store': False, 'stream': True,
                'include': ['reasoning.encrypted_content']}
        if self.tools:
            body['tools'] = deepcopy(self.tools)
        if self.reasoning_effort:
            body['reasoning'] = {'effort': self.reasoning_effort}
        # Filter BEFORE any token refresh, catalog request or inference request.
        with span('filtering'):
            body = self.policy.sanitize(body)
        with span('token_access'):
            token = self.token_store.access_token()
        try:
            if not self._model_checked:
                with span('catalog'):
                    catalog = self.request(API_ORIGIN+'/v1/models', token=token)
                allowed = {m.get('slug') for m in catalog.get('models', [])
                           if m.get('visibility') == 'list' and isinstance(m.get('slug'), str)}
                if self.model not in allowed:
                    raise SubscriptionError('model_not_in_account_catalog')
                self._model_checked = True
            with span('provider_request'):
                response = self.request(API_ORIGIN+'/v1/responses', data=body, token=token, stream=True)
        except SubscriptionError:
            raise
        except ProbeError as exc:
            code = str(exc)
            raise SubscriptionError(code if re.fullmatch(r'[a-z0-9_]{1,100}', code) else 'subscription_request_failed') from None
        except Exception:
            raise SubscriptionError('subscription_request_failed') from None
        if response.get('status') != 'completed':
            raise SubscriptionError('response_not_completed')
        output = response.get('output', [])
        calls, text = [], []
        for item in output:
            if item.get('type') == 'function_call':
                name = item.get('name', '')
                if name.startswith('k90.'):
                    name = name[4:]
                if item.get('namespace') not in (None, 'k90') or name not in self.tool_names:
                    raise SubscriptionError('unexpected_tool')
                if not isinstance(item.get('call_id'), str) or not item['call_id'] or not isinstance(item.get('arguments'), str):
                    raise SubscriptionError('invalid_tool_call')
                calls.append(FunctionCall(item['call_id'], name, item['arguments']))
            elif item.get('type') == 'message':
                for part in item.get('content', []):
                    if part.get('type') == 'output_text':
                        text.append(part.get('text', ''))
                    elif part.get('type') == 'refusal':
                        text.append(part.get('refusal', ''))
        # Replay complete tool calls and encrypted reasoning, never only displayed text.
        self.input.extend(deepcopy(output))
        usage = response.get('usage') or {}
        return Turn(text='\n'.join(text), calls=calls,
                    input_tokens=int(usage.get('input_tokens') or 0),
                    output_tokens=int(usage.get('output_tokens') or 0), complete=True)

    def add_tool_result(self, call_id, result):
        with span('filtering'):
            safe = self.policy.sanitize(result)
        self.input.append({'type': 'function_call_output', 'call_id': call_id,
                           'output': json.dumps(safe, ensure_ascii=False, default=str)})
