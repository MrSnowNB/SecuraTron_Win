# Doctrine: Promotion Gate

## Philosophy
Tools born in a session are fragile and unverified. The Promotion Gate ensures that only "hardened" capabilities enter the global canon. 

## Rule Set
1. **Consistency:** A tool must succeed `required_success` times.
2. **Generalization:** Success must be achieved across `required_distinct_inputs`.
3. **Safety:** High-risk tools always require `requires_human_review: true`.

## Global Gate Config
```yaml
gate:
  default_required_success: 5
  default_required_distinct_inputs: 3
  auto_promotion_enabled: true
  tier_hierarchy: [session, project, global]
```
