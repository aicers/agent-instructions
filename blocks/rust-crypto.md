<!-- BEGIN shared:rust-crypto v1 -->
### Cryptographic comparisons and randomness

- Compare secrets, tokens, MACs, and certificate fingerprints with
  `ring::constant_time::verify_slices_are_equal`, never with `==`. The
  derived `PartialEq` on a secret-bearing type is a timing oracle.
- Draw key material, and any value whose security rests on being
  unguessable (session identifiers, API keys, opaque bearer tokens),
  from a cryptographically secure source (`ring::rand::SystemRandom`)
  — never from a general-purpose PRNG, a timestamp, or a process ID.
  A signed token such as a JWT is not drawn this way at all: its
  strength comes from the signing key, which is key material.
- A nonce must meet whatever its construction documents, which is
  usually uniqueness under a given key rather than randomness. Counter
  and deterministically derived nonces are correct where the algorithm
  calls for them. What is never acceptable is reusing one under the
  same key.
- Do not implement a cryptographic primitive by hand. If the operation is
  not available in an existing dependency, that is a design discussion,
  not a coding task.
<!-- END shared:rust-crypto -->
