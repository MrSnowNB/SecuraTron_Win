# Doctrine: Skill Cards (v1)

## Overview
A **Skill Card** is a structured definition of a tool or capability within the Securatron harness. It serves as the single source of truth for tool discovery, input validation, execution, and structured result parsing.

## Atoms vs. Molecules
- **Atoms:** Atomic operations that map directly to a system command (shell), a Python script, or a Docker Compose stack.
- **Molecules:** Higher-order capabilities composed of multiple atoms. They use a Directed Acyclic Graph (DAG) to define the flow and data dependencies between atoms.

## The Promotion Gate
Every Skill Card tracks its own provenance (`trials`). To be promoted from a `project` tier to the `global` canon, a tool must survive the **Promotion Gate**, which requires a specific number of successful runs across distinct inputs.

## Composition
Molecules enable complex reasoning chains to be frozen into reliable, repeatable tools. Once an atom is proven stable, it can be combined with others to form recon, exploit, or post-ex molecules.
