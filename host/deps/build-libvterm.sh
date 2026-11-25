#!/bin/sh
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
prefix=${VTERM_PREFIX:-"$HOME/.local/superface/libvterm-0.3.3"}
case "$prefix" in /*) ;; *) echo "VTERM_PREFIX must be absolute" >&2; exit 2;; esac
case "$prefix" in *[!a-zA-Z0-9_./-]*) echo "VTERM_PREFIX contains unsupported characters" >&2; exit 2;; esac
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
trap 'exit 1' HUP INT TERM
archive=$build/libvterm-0.3.3.tar.gz
if [ "$#" -gt 0 ]; then
    cp -- "$1" "$archive"
else
    curl -fL --proto '=https' https://www.leonerd.org.uk/code/libvterm/libvterm-0.3.3.tar.gz -o "$archive"
fi
printf '%s  %s\n' 09156f43dd2128bd347cbeebe50d9a571d32c64e0cf18d211197946aff7226e0 "$archive" |
    sha256sum -c -
tar -xf "$archive" -C "$build"
cd "$build/libvterm-0.3.3"
patch -p1 < "$here/libvterm-0.3.3.patch"

# The release ships the generated encoding tables. Build only the library.
mkdir objects
for source in src/*.c; do
    # As in make, CFLAGS is a whitespace-separated list of compiler options.
    # shellcheck disable=SC2086
    "${CC:-cc}" -std=c99 ${CFLAGS:--O2} -Iinclude -Wall -c "$source" -o "objects/$(basename "$source" .c).o"
done
"${AR:-ar}" rcs libvterm.a objects/*.o
install -d "$prefix/include" "$prefix/lib/pkgconfig" "$prefix/share/licenses/libvterm"
install -m644 include/*.h "$prefix/include/"
install -m644 libvterm.a "$prefix/lib/"
install -m644 LICENSE "$prefix/share/licenses/libvterm/"
sed -e "s|@INCDIR@|$prefix/include|" -e "s|@LIBDIR@|$prefix/lib|" \
    -e 's|@VERSION@|0.3.3|' vterm.pc.in > "$prefix/lib/pkgconfig/superface-vterm.pc"
echo "Set PKG_CONFIG_PATH=$prefix/lib/pkgconfig"
