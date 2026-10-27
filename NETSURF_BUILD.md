# NetSurf 3DS local browser build

This GitHub Actions build targets Horizon OS, supports Old 3DS plus New 3DS hardware speedups already configured in the upstream RSF.

Source: socksprox/netsurf-3ds, with libcurl+mbedTLS and experimental Duktape bindings enabled. Two CIA memory profiles: ordinary 64MB and HiMem 80MB. The binary targets ARMv6K, not N3DS-only instructions.

The modern-web Wisp fork (mcirsta/wisp) is **not** the current build input: it removed the framebuffer backend and its QuickJS-ng engine is presently not wired to a real DOM. Attempting to substitute it would produce a broken 3DS port.

Web 2.0 compatibility milestones after a successful booting baseline:
1. Verify HTTPS/TLS and cert handling, links, forms, cookies, JavaScript DOM changes, event listeners.
2. Add modern DOM methods querySelector/querySelectorAll, classList, innerHTML getter, CSSOM.
3. XMLHttpRequest and fetch with cookies, same-origin policy and CORS.
4. Integrate QuickJS or QuickJS-ng with real DOM bindings (not just an interpreter).
5. Benchmark page layout, image decoding, memory pressure and N3DS CPU usage.

A successful CI build only proves compilation and packaging, not gameplay or browser runtime behaviour.
Install a CIA using FBI and use the Home Menu. Do not flash or chainload CIA binaries.
