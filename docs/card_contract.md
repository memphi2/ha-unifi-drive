# Integration And Card Contract

The exporter in `tests/test_card_contract.py` sets up real HA platforms with a
synthetic API client, enables the registered entities and exports their registry
metadata and only grouping-related attributes. It never reads a live HA instance.
The integration test runs in normal CI even without the companion-card checkout.

To check the current integration directly against the companion card, install
the card's existing development dependencies and run from the integration's HA
test environment:

```bash
python scripts/check_card_contract.py --card-root ../ha-unifi-drive-card
```

This generates a fresh temporary export and invokes the card's
the bundled `scripts/card_contract.test.ts` in a temporary test file inside the
card checkout, removed after the run. Existing files are never overwritten.
Missing exports fail, including skipped
HA-backed tests. The card also keeps a generated baseline fixture for its own CI;
refresh it deliberately using `UNAS_CARD_CONTRACT_OUTPUT` when an intentional
entity-contract change is accepted. Do not substitute live diagnostics or entity
exports, which can contain local identifiers.

Scheduled and manually dispatched validation checks the published card commit
`da31de9c54de4a7144c6a1c22cd60c4f6132ed01`. Update this pin deliberately when
adopting a new card baseline. CI retains only synthetic exports and resource
measurements for 14 days, keyed by the integration commit. Normal PR tests remain
self-contained and do not require another repository or Node.js.
