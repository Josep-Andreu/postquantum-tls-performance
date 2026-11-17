# Integration notes for the parent repository

The current top-level `README.md` already documents a completed HTTPS stability campaign and contains a scope line saying that the reported HTTPS campaign excludes mTLS. **Keep that campaign's figures and tables unchanged.** Extend the project scope, not the old campaign's experiment definitions.

Recommended section to paste near the top-level README's navigation or the end of the results section:

```markdown
## Mutual TLS extension (October 2026)

A separate [mTLS campaign](mtls/README.md) compares classic ECDSA P-384 + `secp384r1`, ECDSA P-384 + `X25519MLKEM768` (hybrid KEM), and ML-DSA-65 authentication with `X25519MLKEM768`. Nine 120-second runs (three/profile) are preserved with sanitized `wrk` logs, derived datasets, eight figures, portable analysis scripts, an offline consistency checker, and [methodological limitations](mtls/docs/methodology-and-limitations.md).

The hybrid mTLS profile measured **1,100.47 HTTP requests/s** versus **946.68** for the classic reference (+16.25%) on this 4-vCPU lab, but its client-observed HTTP p99 was higher (206.24 ms versus 161.25 ms). These are **separate** experiments from the November 4 server-only HTTPS benchmark and should not be pooled or used to infer a universal PQC speed advantage.
```

Also amend the existing scope sentence from:

> Scope: classical and post-quantum server-side HTTPS/TLS. This campaign excludes mutual TLS, proxies, and Kubernetes.

to:

> Scope: This **November 4 HTTPS campaign** excludes mutual TLS, proxies, and Kubernetes; the repository additionally contains a **separate October mTLS campaign** in [`mtls/`](mtls/README.md).

Keep the top-level main research headline about November 4 HTTPS results unchanged. It is not contradicted by the mTLS findings; the configurations and client authentication models differ.

For an initial PR, add `mtls/` and `.github/workflows/mtls-data.yml`, and make only the minimal README edits described above. Do not commit the originally uploaded tarball or raw lab hostnames.
