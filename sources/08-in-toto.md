# in-toto Attestation Framework

**Title:** in-toto Attestation Framework Specification v1

**URL:** https://github.com/in-toto/attestation

**Version/Date:** Specification v1; framework under ongoing development

**Access:** Public (GitHub repository and specification documents)

**Source(s):** GitHub repository at github.com/in-toto/attestation; specification in `/spec/v1` directory.

## Statement Specification

- **Statement:** "Binds the attestation to a particular subject and unambiguously identifies the types of the predicate"
- **_type:** Field identifying the attestation statement type (e.g., "https://in-toto.io/Statement/v0.1")
- **subject:** The artifact being attested; contains name and digest(s) of the artifact
- **predicateType:** URI identifying the type of predicate (e.g., "https://slsa.dev/provenance/v0.1")
- **predicate:** Arbitrary metadata about the subject artifact with a type-specific schema

## DSSE Envelope

- **DSSE (Dead Simple Signing Envelope):** Authentication and serialization mechanism wrapping the statement
- **Envelope structure:** Contains `payload` (base64-encoded Statement) and `signatures` (signing records with `keyid` and `sig`)
- **Purpose:** Provides cryptographic signing and verification without embedding signature data in the statement itself

## Test-Result Predicate

- **test-result predicate:** Metadata structure for test execution results
- **Field names:** (Per specification in `/spec/v1/predicate.md`) Include execution context, test identity, result status, and optional logs
- **Result values:** Status enum with values such as PASSED, FAILED, SKIPPED (for test predicates)

## SLSA Integration

- The in-toto framework integrates with SLSA (Supply-chain Levels for Software Artifacts)
- SLSA Provenance and Verification Summary Attestation (VSA) are defined as predicates using in-toto Statement structure

## Not Found

- Complete field-by-field schema for all in-toto predicates
- Exact enum values for test-result predicate status field (confirmed PASSED, FAILED, SKIPPED but not exhaustive list)
- Full protobuf definitions in detail

## Notes

The in-toto specification is actively maintained and publicly available. The framework is designed as a generalized attestation format supporting multiple predicate types including SLSA provenance.
