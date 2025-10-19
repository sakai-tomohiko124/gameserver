"""
Minimal awsgi stub for local development/editor to satisfy imports.
This file should NOT be used in production. In deployment, install the real `awsgi` package
and remove or ignore this stub.
"""
from typing import Any

def response(app: Any, event: Any, context: Any) -> Any:
    # Very small emulation: return a simple dict so handler can call awsgi.response in tests.
    return {
        'statusCode': 200,
        'body': 'awsgi stub in use'
    }
