"""Everything that wraps an external system.

LLM providers, MCP transports, Postgres, Langfuse, the rate-limit store and the
artifact filesystem. Grouping them says which modules have a dependency on
something outside this process -- and, by omission, which do not: `capabilities/`
and `shared/` should never need anything from here except through an injected
collaborator.
"""
