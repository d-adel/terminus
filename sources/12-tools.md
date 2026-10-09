# Existing tools to compose Terminus from, surveyed 2026-10-08

Checked on the page itself:
- in-toto test-result predicate, https://github.com/in-toto/attestation/blob/main/spec/predicates/test-result.md: predicateType https://in-toto.io/attestation/test-result/v0.1; fields result (PASSED, WARNED, FAILED), configuration, url, passedTests, warnedTests, failedTests.
- SLSA Verification Summary Attestation, https://slsa.dev/spec/v1.1/verification_summary: predicateType https://slsa.dev/verification_summary/v1; verifier.id, timeVerified, resourceUri, policy.uri and digest, inputAttestations (digest, uri), verificationResult PASSED or FAILED, verifiedLevels, dependencyLevels, slsaVersion.
- gsn2x, https://github.com/jonasthewolf/gsn2x: MIT; renders GSN v3 from YAML to SVG; README describes rendering only, no status evaluation.

From search summaries only, not checked on the project page:
- witness (in-toto, CNCF): wraps commands, records hashes of materials and products, embedded OPA Rego policy, Sigstore signing, stores to Archivista.
- GUAC (OpenSSF incubating): ingests SBOMs and in-toto/SLSA attestations into a graph, GraphQL queries.
- Clarissa / ASCE (SRI, Adelard): Assurance 2.0, defeaters, logical and probabilistic assessment; available from Adelard (commercial).
- Evidential Tool Bus (SRI, fortiss): Datalog-based workflows producing assurance evidence; open-source status not confirmed.
- Eclipse OpenCert: no recent activity. Isabelle/SACM: research implementation. OMG SACM 2.3 (2023), 2.4 in progress.
- Bencher: open source, self-hostable continuous benchmarking; thresholds by Z-score or Student's t.
- Workflow Run RO-Crate: workflow-run provenance packaging aligned with W3C PROV; implemented by several workflow systems.
- ReFrame: HPC regression and performance testing with per-system reference values.
