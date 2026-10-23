"""Bounded Responses transport with safe failure telemetry and no retries."""
import re
import httpx
from app import provider


def safe_text(value, key):
    text = str(value).replace(key, '[redacted]') if key else str(value)
    text = re.sub(r'sk-[A-Za-z0-9_-]+', '[redacted]', text)
    text = re.sub(r'Bearer\s+\S+', 'Bearer [redacted]', text, flags=re.I)
    return text[:800]


class DiagnosticTransport:
    def __init__(self, key, client_factory=httpx.Client):
        self.key = key
        self.client_factory = client_factory
        self.telemetry = {'http_status': None, 'failure_kind': None}

    def __call__(self, payload):
        try:
            with self.client_factory(timeout=httpx.Timeout(45, connect=10),
                                     trust_env=False, follow_redirects=False) as client:
                with client.stream('POST', 'https://api.openai.com/v1/responses',
                                   headers={'Authorization': 'Bearer ' + self.key}, json=payload) as response:
                    self.telemetry['http_status'] = response.status_code
                    body = bytearray()
                    limit = provider.MAX_RESPONSE_BYTES if response.status_code == 200 else 65536
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > limit:
                            self.telemetry['failure_kind'] = 'response_size_limit'
                            raise provider.ProviderError('Provider response exceeds its bounded size.')
                        body.extend(chunk)
                    try:
                        result = provider._json_unique(body.decode('utf8'))
                    except (ValueError, UnicodeError):
                        self.telemetry['failure_kind'] = 'invalid_json_response'
                        raise provider.ProviderError('Provider returned invalid JSON.') from None
                    if response.status_code != 200:
                        error = result.get('error', {}) if isinstance(result, dict) else {}
                        self.telemetry['failure_kind'] = 'http_error'
                        self.telemetry['provider_error'] = {
                            k: safe_text(error[k], self.key)
                            for k in ('type', 'code', 'param', 'message')
                            if isinstance(error, dict) and k in error and error[k] is not None}
                        raise provider.ProviderError(f'OpenAI returned HTTP {response.status_code}; no retry sent.')
                    return result
        except httpx.HTTPError as exc:
            self.telemetry['failure_kind'] = type(exc).__name__
            raise provider.ProviderError(f'Provider transport failed: {type(exc).__name__}; no retry sent.') from None
