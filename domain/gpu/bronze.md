# GPU Bronze Layer

## Purpose of the Bronze Layer
Bronze captures external evidence about the GPU market in raw form. It preserves inputs
for deterministic resolution in Silver. Bronze exists to preserve evidence, not to be correct.

## What Bronze Represents (and What It Does Not)
Bronze represents:
- External, point-in-time evidence from retailers
- Raw observations and optional hypotheses tied to observed product descriptions

Bronze does not represent:
- Canonical identity or normalized entities
- Corrected or consolidated market truth
- A staging area for Silver

## Types of Data Stored in Bronze

### Market Observations
Market observations are point-in-time facts scraped from retailers. They include the raw
product name, price, URL, timestamp, and scrape_run_id, and are never deduplicated or corrected.

### Product Hypotheses
Product hypotheses are optional interpretations of an observed product description produced by
external processes (LLMs, scrapers, human input). They are not treated as truth, may be
contradictory, remain traceable to their source and input, and can exist in multiples for the
same observed description. Hypotheses apply to observed product descriptions, not to individual
observations.

## Immutability and Versioning Guarantees
- Append-only: evidence is never updated or deleted
- Immutable: observations and hypotheses remain as originally recorded
- Versioned by source and run (e.g. scrape_run_id)
- Reproducible: reruns create new versions without altering prior evidence

## Identification, Fingerprints, and Deduplication (Bronze-only)
- Bronze never assigns canonical IDs
- Bronze never decides chip or variant identity
- Market observations are events and are never grouped or merged
- Bronze may deduplicate descriptions but never events
- Weak, non-canonical fingerprints (e.g. normalized product name hashes) may be computed only to
  avoid redundant enrichment work
- Fingerprints are Bronze-scoped, do not cross into Silver, do not represent domain identity, and
  exist only for cost and processing efficiency

## Relationship to Silver
- Silver consumes Bronze strictly as evidence
- Silver is the only layer that resolves identity and creates gpu_chip or gpu_variant
- Silver deterministically decides equivalence and uniqueness
- Bronze hypotheses remain inputs; Silver determines what becomes canonical

## Explicit Non-Goals
- Normalization or canonical modeling
- Assigning or resolving identity
- Event deduplication or correction
- Current-state aggregation or ranking
- Recommendation logic or user-facing semantics
