#!/usr/bin/env bash
set -Eeuo pipefail
export DEVKITPRO=/opt/devkitpro
export DEVKITARM=/opt/devkitpro/devkitARM
export PATH="$DEVKITARM/bin:$DEVKITPRO/tools/bin:$PATH"
export PKG_CONFIG_PATH="$DEVKITPRO/portlibs/3ds/lib/pkgconfig"

git clone --depth=1 https://github.com/socksprox/netsurf-3ds.git source
# This fork tracks generated artifacts from another host. Purge them so
# stale build stamps and macOS .o/.a files cannot poison Linux ARM builds.
rm -rf source/inst-framebuffer
find source -type d \( -name 'build-arm64-*' -o -name 'build-x86_64-*' \) -prune -exec rm -rf {} +
# Verify the intended portable ARMv6K build and JS configuration.
grep -q 'NETSURF_USE_DUKTAPE := YES' source/netsurf/Makefile.config
grep -q 'CpuSpeed *: 804MHz' source/netsurf/nsfb.rsf
grep -q 'SystemMode *: 64MB' source/netsurf/nsfb.rsf
grep -q 'SystemMode *: 80MB' source/netsurf/nsfb_himem.rsf

# Top-level make forces NOCIA=1, so package both CIAs explicitly after build.
make -C source build JOBS=2 V=1
mkdir -p dist
cp source/nsfb.3dsx dist/nsfb.3dsx
cd source/netsurf
test -s nsfb
test -s nsfb.smdh
test -s nsfb.bnr
test -s nsfb_himem.smdh
test -s nsfb_himem.bnr
makerom -f cia -elf nsfb -o ../../dist/nsfb.cia -rsf ./nsfb.rsf -icon nsfb.smdh -banner nsfb.bnr
makerom -f cia -elf nsfb -o ../../dist/nsfb_himem.cia -rsf ./nsfb_himem.rsf -icon nsfb_himem.smdh -banner nsfb_himem.bnr
cd ../../dist
sha256sum nsfb.cia nsfb_himem.cia nsfb.3dsx > SHA256SUMS.txt
ls -lh *.cia *.3dsx
