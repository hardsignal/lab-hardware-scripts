"""Explicit offline/hardware command line. No discovery or enable commands."""
import argparse
import json
import sys

from . import SafetyPolicy
from .connections import Connections, connected_session
from .logger import JsonlLogger
from .errors import note_failure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('idn', 'status', 'rigol', 'siglent', 'all-off'):
        item = sub.add_parser(name)
        mode = item.add_mutually_exclusive_group(required=True)
        mode.add_argument('--dry-run', action='store_true')
        mode.add_argument('--hardware', action='store_true')
        item.add_argument('--connections', help='JSON transport profile; required for hardware')
        item.add_argument('--config')
        item.add_argument('--log', help='append JSONL here; default: stderr')
        if name == 'rigol':
            item.add_argument('--channel', type=int, required=True)
            item.add_argument('--voltage', type=float, required=True)
            item.add_argument('--current-limit', type=float, required=True)
        if name == 'siglent':
            item.add_argument('--mode', choices=['cc'], required=True)
            item.add_argument('--current', type=float, required=True)
    args = parser.parse_args(argv)
    stream = open(args.log, 'a', encoding='utf-8') if args.log else sys.stderr
    logger = JsonlLogger(stream)
    primary = None
    try:
        policy = SafetyPolicy.load_file(
            args.config) if args.config else SafetyPolicy()
        connections = Connections.load_file(args.connections) if args.connections else None
        with connected_session(policy, logger, connections, dry_run=args.dry_run) as session:
            rigol, siglent = session.rigol, session.siglent
            if args.command == 'all-off':
                session.all_off()
                result = {'all_off': 'confirmed'}
            elif args.command == 'idn':
                result = {kind: report['identity']
                          for kind, report in session.startup_state.items()}
            elif args.command == 'status':
                result = {'status': session.status()}
            elif args.command == 'rigol':
                voltage, current = rigol.configure(
                    args.channel, args.voltage, args.current_limit)
                result = {'channel': args.channel, 'voltage': voltage,
                          'current_limit': current, 'output': 'OFF'}
            else:
                result = {'mode': 'cc', 'current': siglent.configure_cc(args.current),
                          'input': 'OFF'}
        print(json.dumps({'dry_run': args.dry_run,
              'startup_state': session.startup_state, **result}))
        return 0
    except Exception as exc:
        primary = exc
        note_failure(exc, 'CLI failure logging failed',
                     lambda primary=exc: logger.record('failure', error=repr(primary)))
        print(str(exc), file=sys.stderr)
        for note in getattr(exc, '__notes__', ()):
            print(note, file=sys.stderr)
        return 1
    finally:
        if args.log:
            if primary is None:
                stream.close()
            else:
                note_failure(primary, 'Log close failed', stream.close)


if __name__ == '__main__':
    sys.exit(main())
