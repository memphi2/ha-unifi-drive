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
`test/real-integration-contract.test.ts`. Missing exports fail, including skipped
HA-backed tests. The card also keeps a generated baseline fixture for its own CI;
refresh it deliberately using `UNAS_CARD_CONTRACT_OUTPUT` when an intentional
entity-contract change is accepted. Do not substitute live diagnostics or entity
exports, which can contain local identifiers.
