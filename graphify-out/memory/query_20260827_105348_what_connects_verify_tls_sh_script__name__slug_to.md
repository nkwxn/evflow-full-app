---
type: "query"
date: "2026-08-27T10:53:48.343756+00:00"
question: "What connects verify_tls.sh script, name, slug to the rest of the system?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["verify_tls.sh script", "TLS Deployment Verification", "slug()", "name"]
---

# Q: What connects verify_tls.sh script, name, slug to the rest of the system?

## Answer

Expanded from original query via vocab: [verify, tls, script, name, slug, system, connection]. Graph traversal found no shared path. verify_tls.sh script is a 2-node component, attached only to its file container at backend-ev-flow/scripts/verify_tls.sh:L1. TLS Deployment Verification is separately a 5-node documentation component; slug() is in the ev_union.py/test cluster; name and slug from mobile app.json belong to the Expo metadata component. This suggested question is a weak-component diagnostic, not an integration trace.

## Outcome

- Signal: useful

## Source Nodes

- verify_tls.sh script
- TLS Deployment Verification
- slug()
- name