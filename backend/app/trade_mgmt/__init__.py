"""
TradeMinds — Trade Management v2 (Phase 1: Offline Replay Harness).

ISOLATED, READ-ONLY analysis package. Nothing in the live hot paths
(tracker / scheduler / signal_generator / lifecycle) imports from here, so the
current trading behavior cannot change. Phase 1 only *measures*: it reads
signal_trade_path, replays policies counterfactually, and reports — it never
writes, never executes, never learns yet.

See: docs/trade-management-v2-design.md, docs/trade-management-v2-phase1-spec.md
"""
