import requests

url = 'https://api.moltbook.com/v1/agents/register'
payload = {
    'agent_name': 'calamum-keysmith',
    'purpose': 'moltbook_agent_registration',
    'operator': 'ORACL-Prime',
}

try:
    response = requests.post(url, json=payload, timeout=20)
    print({
        'status': response.status_code,
        'content_type': response.headers.get('content-type', ''),
        'body': response.text[:400],
    })
except Exception as exc:
    print({
        'error_type': type(exc).__name__,
        'message': str(exc),
    })
