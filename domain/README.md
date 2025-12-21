# Domain Documentation

This directory contains the formal data domain definitions for the PcBuilder project.

Each domain documents:
- Its scope and responsibilities
- The physical SQL schema it owns
- The meaning of each data layer (Silver, Gold)

## Available Domains

- `gpu/` — Graphics Processing Units market data

## Conventions

- SQL is the source of truth.
- Documentation mirrors the database schema exactly.
- Silver tables are immutable and append-only.
- Gold objects are derived and can be rebuilt at any time.
