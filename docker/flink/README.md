# Flink conformance arm

The simulated `global_watermark` and `idle_watermark` reconcilers claim to
reproduce what Apache Flink's interval join does. That claim is checked here
against the real engine rather than asserted: the same arrivals are replayed
through a Flink SQL job, and the resulting match/break partition is compared
with the simulator's.
