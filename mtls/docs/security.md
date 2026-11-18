# Publication safety and reproducibility

The public files intentionally exclude TLS private keys, CA trust files, credential contents, tokens, passwords, internal FQDNs, private IP addresses and absolute paths to the original lab credentials. The 40-row CSV contains protocol profile identifiers, experimental port numbers and numeric performance measurements only.

The public benchmark runner is a **parameterized template**: it requires the user to explicitly supply a server name, SSH target, wrk binary path and certificate directory. Its generic observer-script location is an example and must be configured for each installation. Certificate/key names in its profile matrix are template filenames, not published cryptographic material.

Do not upload private raw wrk logs: the actual logs can contain hostnames, certificate filenames, endpoints and internal paths. Do not upload the original lab bundles, SSL private key files, unredacted Apache configuration or credentials. Private logs should be retained only on secured benchmark infrastructure.

The verified wrk binary's negative-CA test and Apache client-certificate rejection tests were performed before the measurements; public CSV values cannot replace those validations.

The October 2026 pilot is available via previous Git commits, but its legacy client did not enforce server-chain verification. Use only the November 2026 validated campaign for peer-verified mTLS claims.
