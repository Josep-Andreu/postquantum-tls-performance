# Adapting `wrk` for post-quantum TLS benchmarks

This directory contains the **minimal change recovered from the actual benchmark `wrk` source tree**, the OpenSSL client configurations used in the lab, and the Lua script used to request connection closure. It is **not** a fork of `wrk` and does not include private keys or certificates.

## Why this was needed

The tested `wrk` tree included a bundled OpenSSL 1.1.1i archive. To use the post-quantum TLS capabilities available in the RHEL client's OpenSSL 3.5, we built against the system OpenSSL installation. We also added a call to `SSL_CTX_config(ctx, "client")` immediately after `SSL_CTX_new(...)` in `src/ssl.c`. This applies a named OpenSSL SSL configuration to the newly created client context.

The recovered source modification is exactly one added line. **The code does not check the return value of `SSL_CTX_config`**; therefore a successful `wrk` run alone is not evidence that the requested TLS settings were applied. Validate the negotiated parameters independently.

## Build

Prerequisites: a Linux build environment with OpenSSL 3.5 development headers/libraries, `make`, a C compiler, and the other dependencies required by upstream `wrk` (including LuaJIT). The actual benchmark client used OpenSSL 3.5.8.

```bash
# From a checkout of https://github.com/wg/wrk
# Use a compatible upstream revision: verify that the patch applies before building.
git apply --check /path/to/0001-apply-openssl-client-config.patch
git apply /path/to/0001-apply-openssl-client-config.patch
make WITH_OPENSSL=/usr -j"$(nproc)"
ldd ./wrk | grep -E 'ssl|crypto'
```

On the benchmark client, `ldd` showed `libssl.so.3` and `libcrypto.so.3` loaded from `/lib64`. The `WITH_OPENSSL=/usr` option directs the build to the system installation instead of the bundled OpenSSL dependency. This does **not** pin the exact OpenSSL 3 minor release; check `openssl version -a` on the test system.

## Select a client TLS profile

The two included configuration files were recovered from the lab:

| File | TLS signature algorithms | TLS key exchange groups |
| --- | --- | --- |
| `openssl/mldsa65.cnf` | `MLDSA65` | Not explicitly set |
| `openssl/mldsa87-mlkem1024.cnf` | `MLDSA87` | `MLKEM1024` |

The configuration files define the named SSL configuration `client`. The patched `wrk` applies that configuration using `SSL_CTX_config(ctx, "client")`.

Example for the ML-DSA-87 / ML-KEM-1024 profile (replace the host with your test endpoint):

```bash
OPENSSL_CONF=/absolute/path/to/openssl/mldsa87-mlkem1024.cnf \
  ./wrk -t8 -c50 -d120s --latency \
  -s /absolute/path/to/close.lua \
  https://web.lab.example.com:12443/
```

`close.lua` adds the HTTP header `Connection: close`. This requests a fresh HTTP connection but **does not by itself prevent TLS session resumption**. In the original full-handshake experiments, session caching and tickets were disabled on the server and resumption was checked separately.

## Verify the TLS negotiation

Check the server-side TLS configuration and verify the expected algorithms with an independent OpenSSL client, for example:

```bash
openssl s_client -connect web.lab.example.com:12443 \
  -servername web.lab.example.com \
  -tls1_3 -groups MLKEM1024 </dev/null
```

Inspect the resulting handshake output for the negotiated group and signature details. This separate command checks the endpoint and OpenSSL capabilities; it does **not** directly observe `wrk`'s negotiated handshake. A packet capture or instrumented `wrk` build is needed for direct per-run verification.

## Scope and security limitations

- The recovered `wrk` source still sets `SSL_VERIFY_NONE` and `SSL_CTX_set_verify_depth(ctx, 0)`: it **does not validate the server's certificate chain or hostname**. Do not use it to claim authenticated certificate validation.
- The patch does not add ML-KEM or ML-DSA implementations. Those are supplied by the OpenSSL library.
- The patch does not change client certificate handling, add mTLS, or add certificate-verification support. Those later experiments used separate source trees and are outside this directory.
- The configuration in `mldsa65.cnf` specifies signature algorithms only; it does not force an ML-KEM group.
- The source patch is reconstructed from the uploaded `src/ssl.c.orig` and `src/ssl.c`; the original Git history was not included. Pin and test a compatible upstream `wrk` revision before advertising a fully reproducible build.

## Source and attribution

`wrk` is maintained at https://github.com/wg/wrk. This repository stores only a small patch against its source and auxiliary configuration files; consult upstream for the original project and its license.
