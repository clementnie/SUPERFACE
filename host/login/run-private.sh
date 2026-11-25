#!/bin/sh
# Explicit bench invocation from a private operator terminal.
set -eu
[ "$(id -u)" = 0 ] && [ -t 0 ] && [ -t 1 ]
case "$#" in
    0) ;;
    1) [ "$1" = --uart ]; set -- --uart /dev/ttyS2 ;;
    *) exit 2 ;;
esac
exec systemd-run --unit=superface-private-login --pty --wait --collect \
    --property=KillMode=control-group --property=LimitCORE=0 \
    --property=TimeoutStopSec=5s /opt/superface/bin/superface --login "$@"
