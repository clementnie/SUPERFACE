#!/bin/sh
# Grant one account rw access to the bound UART2 device for this boot.
set -eu
if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ]; then
    echo "Usage: sudo $0 ACCOUNT" >&2
    exit 2
fi
account_id=$(id -u "$1")
[ "$account_id" -ne 0 ]
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
device=$(sh "$script_dir/find-tty.sh")
[ "$device" = /dev/ttyS2 ]
setfacl -m "u:$account_id:rw" "$device"
getfacl -p "$device"
