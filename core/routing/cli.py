"""Print a policy proposal from explicit JSON inputs; perform no writes."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from core.backend.models import Memory
from core.routing.policy import RoutingContext, TargetRevision, plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--memory', type=Path, required=True, help='Memory JSON, including qualification')
    parser.add_argument('--context', type=Path, required=True, help='Explicit routing context JSON')
    args = parser.parse_args(argv)
    memory = Memory(**json.loads(args.memory.read_text(encoding='utf-8')))
    context = json.loads(args.context.read_text(encoding='utf-8'))
    if context.get('update_target') is not None:
        context['update_target'] = TargetRevision(**context['update_target'])
    for key in ('candidate_projects', 'evidence_refs'):
        if key in context:
            context[key] = tuple(context[key])
    result = plan(memory, RoutingContext(**context))
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
