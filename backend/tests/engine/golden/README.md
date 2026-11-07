# Golden cases

One YAML file per case. The engine must produce the expected outcome; P4 (DBA) owns these.
`status: from_doc_05` cases come from docs/05; `draft` cases need DBA agreement.

```yaml
name: short description
status: from_doc_05 | draft
input:              # a RequirementsInput body
  answers: {...}
  priorities: {...} # optional
expect:
  top1:             # all optional
    family_in: [relational]
    engine_in: [oracle]
    csp_in: [azure]
    roles_include: [cache]           # component roles in the top recommendation
    ha_topology_contains: Single-AZ
  excluded:         # service id -> rule id that must be among its removal reasons
    aws.dynamodb: SHAPE-FILTER
```
