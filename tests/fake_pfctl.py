#!/usr/bin/env python3
"""Stand-in for /sbin/pfctl: tables are files in $PFCTL_TABLES.

Supports `-t NAME -T show|flush|replace [-f FILE | ADDR...]` and, like the
real pfctl, rejects the whole replace if any address is invalid.
"""
import ipaddress
import os
import sys

tables = os.environ['PFCTL_TABLES']
with open(os.path.join(tables, '.argv'), 'a') as log:
    log.write(' '.join(sys.argv[1:]) + '\n')

args = sys.argv[1:]
if args[0] != '-t' or args[2] != '-T':
    sys.exit('fake pfctl: unsupported arguments')
path = os.path.join(tables, args[1])
op, rest = args[3], args[4:]

if op == 'show':
    if not os.path.exists(path):
        sys.exit('pfctl: Table does not exist.')
    sys.stdout.write(open(path).read())
elif op == 'flush':
    open(path, 'w').close()
elif op == 'replace':
    addrs = open(rest[1]).read().split() if rest[:1] == ['-f'] else rest
    for a in addrs:
        try:
            ipaddress.ip_network(a, strict=False)
        except ValueError:
            sys.exit(f'pfctl: cannot decode {a}')
    with open(path, 'w') as f:
        f.write(''.join(a + '\n' for a in addrs))
else:
    sys.exit(f'fake pfctl: unsupported command {op}')
