<!-- BEGIN shared:rust-tls v1 -->
### TLS

- Certificate and hostname verification is never disabled to get a
  handshake working. If a handshake fails, fix the trust chain, the SANs,
  or the clock — do not reach for an escape hatch.
- `rustls`'s `dangerous()` accessors and any hand-written
  `ServerCertVerifier`/`ClientCertVerifier` live in one dedicated module
  per crate, named in the repository-specific section below. Do not
  introduce them anywhere else, and do not add a new verifier without an
  explicit design decision recorded in the pull request.
- Never widen a verifier to accept a certificate it would otherwise
  reject as a temporary measure. There is no such thing as a temporary
  measure here.
<!-- END shared:rust-tls -->
