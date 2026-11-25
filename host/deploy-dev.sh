#!/bin/sh
# Copy only host source and canonical inputs, then build and run tests on the board.
set -eu
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 /path/to/opi_ssh.sh /tmp/libvterm-0.3.3.tar.gz" >&2
    exit 2
fi
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
ssh_helper=$1
archive=$2
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
trap 'exit 1' HUP INT TERM
cp -- "$archive" "$work/libvterm-0.3.3.tar.gz"
printf '%s  %s\n' 09156f43dd2128bd347cbeebe50d9a571d32c64e0cf18d211197946aff7226e0 \
    "$work/libvterm-0.3.3.tar.gz" | sha256sum -c -
tar -czf "$work/source.tgz" --exclude=host/build --exclude=__pycache__ -C "$root" host \
    assets/fonts/glyph_map.csv assets/fonts/font_manifest.json assets/fonts/missing_zh_hans.csv \
    -C "$work" libvterm-0.3.3.tar.gz
sh "$ssh_helper" '
    set -eu
    test "$(uname -m)" = aarch64
    tr "\000" "\n" </proc/device-tree/compatible | grep -qx xunlong,orangepi-zero2w
    uname -sr
    command -v cc make pkg-config python3
    if pkg-config --modversion vterm; then :; else echo "System libvterm absent"; fi
    mkdir -p "$HOME/.local/superface"
    dest=$(mktemp -d "$HOME/.local/superface/phase5.XXXXXXXX")
    tar -mxzf - -C "$dest"
    sh "$dest/host/deps/build-libvterm.sh" "$dest/libvterm-0.3.3.tar.gz"
    PKG_CONFIG_PATH="$HOME/.local/superface/libvterm-0.3.3/lib/pkgconfig" make -C "$dest/host" check
    printf "Deployment: %s\n" "$dest"
' < "$work/source.tgz"
