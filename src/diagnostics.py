"""Local, credential-redacted tool errors; never include uploaded image bytes."""
import json
import logging
from logging.handlers import RotatingFileHandler

from settings import config

from project_paths import ROOT


def record_failure(agent, tool, result):
    if not isinstance(result, dict) or result.get('ok') is not False or result.get('deferred'):
        return
    text = json.dumps({'agent': agent, 'tool': tool,
                       'error': result.get('error'), 'failures': result.get('failures', [])},
                      ensure_ascii=False, default=str)
    for name in dir(config):
        if any(word in name.upper() for word in ('KEY', 'SECRET', 'API_ID', 'TOKEN', 'PASSWORD')):
            value = getattr(config, name)
            if isinstance(value, str) and value:
                text = text.replace(value, '<REDACTED>')
    logger = logging.getLogger('agent.errors')
    if not logger.handlers:
        folder = ROOT / '.runtime'
        folder.mkdir(exist_ok=True)
        handler = RotatingFileHandler(folder / 'errors.log', maxBytes=1_000_000,
                                      backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(logging.WARNING)
    logger.warning(text)


def capture_history(messages):
    for message in messages:
        if message.get('role') != 'tool':
            continue
        try:
            result = json.loads(message.get('content', '{}'))
        except (ValueError, TypeError):
            continue
        record_failure('history', message.get('tool_call_id', ''), result)
