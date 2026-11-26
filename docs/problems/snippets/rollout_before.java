// Before q10: the controller only ever moved forward; going back was a human's job.
// @learn:before-rollout
public Action tick(String status, int percent, long stageSinceMs, OutcomeWindow.Stats v2, long nowMs) {
    if (!"RAMPING".equals(status)) {
        return new None();
    }
    if (nowMs - stageSinceMs >= cfg.holdMs()) {
        return new Advance(next(percent), "hold time passed");
    }
    return new None();
}
// @learn:end before-rollout
