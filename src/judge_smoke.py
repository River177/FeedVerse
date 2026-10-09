"""Exercise the unmodified official visual Judge with an identical image pair."""
import json
from pathlib import Path
import sys

sys.path.insert(0, '/official')
from gpt4_visual_judge import encode_image, score_figure

reference = Path('/benchmark/eval_programs/gold_results/Elk_Analysis_gold.png')
image = encode_image(reference)
responses, score = score_figure(image, image)
if len(responses) != 3 or not all(isinstance(text, str) and '[FINAL SCORE]' in text for text in responses):
    raise RuntimeError('Official Judge did not return three parseable scores')
Path('/control/judge-smoke.json').write_text(json.dumps({'passed': True, 'choices': len(responses),
    'identical_image_score': score, 'deployment': 'gpt-4o_2024-11-20',
    'prompt_and_scoring_source': 'unmodified official gpt4_visual_judge.py'}, indent=2))
