"""Explicit live evaluation: ten small, source-grounded turns; never prints credentials."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from dotenv import load_dotenv
from blinkspace.assistant import ChatInput
from blinkspace.assistant_qfit import local_sources, run_qfit

ROOT = Path(__file__).resolve().parents[1]

async def evaluate():
    results = []
    for target in ['barnard', 'eps-indi-b', 'wise-0855', 'rw-aur', 'r-dra']:
        for question in ['Bu yıldızda ne görüyorum? Yüzey ve çevresinin hangi kısımları temsili? En fazla iki kısa paragraf ve kaynak kimlikleriyle açıkla.', 'Bu yıldız için gösterilen sıcaklık ve yarıçap sayıları nereden geliyor? Değer benimsenmemişse açıkça söyle. En fazla iki kısa paragraf ve kaynak kimlikleriyle açıkla.']:
            started = time.monotonic()
            try:
                answer, commands, errors = await run_qfit(ChatInput(message=question, context={'target': {'id': target}, 'ui_language': 'tr', 'mode': 'star', 'year': 2026}))
                results.append({'target': target, 'question': question, 'seconds': round(time.monotonic() - started, 2),
                                'message_source': answer['message_source'], 'model': answer['meta']['ai_model'],
                                'answer': answer['message'], 'sources': answer['sources'], 'uncertainty': answer['uncertainty'],
                                'grounding': answer['data'].get('grounding'), 'commands': commands, 'errors': errors})
                print(json.dumps({'target': target, 'completed': len(results), 'sources': len(answer['sources']), 'errors': len(errors)}), flush=True)
            except Exception as exc:
                results.append({'target': target, 'question': question, 'error_class': type(exc).__name__, 'code': getattr(exc, 'code', 'unknown')})
                print(json.dumps({'target': target, 'completed': len(results), 'error_class': type(exc).__name__}), flush=True)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'Live OpenAI gpt-5.4-mini via QFIT adapter; source-grounding review, not astronomical validation', 'results': results}
    (ROOT / 'evidence/integration/assistant-live-eval.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.parse_args()
    load_dotenv(ROOT / '.env')
    asyncio.run(evaluate())
