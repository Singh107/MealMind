import argparse
import asyncio
import json
from pathlib import Path
from .cases import load_cases
from .runner import run, markdown


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline recipe pipeline evaluation; fixture mode is not Gemini quality.')
    parser.add_argument('--mode', choices=['fixture', 'live'], default='fixture')
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--output', type=Path, default=Path('evaluation/results/baseline'))
    parser.add_argument('--acknowledge-live-cost', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 25:
        parser.error('--limit must be 1-25')
    cases = load_cases()
    if set(args.case) - {c.id for c in cases}:
        parser.error('Unknown case ID')
    cases = [c for c in cases if not args.case or c.id in args.case][:args.limit]
    if args.mode == 'live':
        print(f'LIVE API/COST WARNING: {len(cases)} generation calls, up to {2 * len(cases)} Gemini HTTP attempts; real USDA requests. No repair. Sequential execution.', flush=True)
        if not args.acknowledge_live_cost:
            parser.error('Live execution requires --acknowledge-live-cost')
    try:
        report = asyncio.run(run(cases, args.mode))
    except Exception:
        # Configuration errors may contain environment values: never print them.
        parser.exit(2, 'Evaluation setup failed; check configuration locally. No exception details retained.\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
    print(f"{report['label']}: {len(cases)} cases. Reports written.")
    return 1 if args.mode == 'fixture' and any(not r['expectation_pass'] for r in report['results']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
