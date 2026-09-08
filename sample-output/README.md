# Sample output

JSON dumps of the ledger after ingesting the six documents in `sample-pdfs/` with
`rlx ingest-dir sample-pdfs --provider replay`. They let the output be reviewed
without running the project.

| file | contents |
| --- | --- |
| `four_cases.json` | the four required cases, each with both facts, verbatim quotes, page numbers, and the full comparison trace |
| `all_relations.json` | every relationship in the ledger: classification, rule code, confidence, explanation |
| `extraction_failures.json` | the proposal that was rejected because its quote could not be verified, and the fact held back by a sanity check |
| `stats.json` | counts |

Ledger: 6 documents, 28 facts, 33 relationships (13 corroborated, 2 contradictions,
18 reconciled, 0 unresolved), 1 rejected proposal.
