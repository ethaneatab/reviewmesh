package dev.reviewmesh.migration;

/**
 * Where this app version stands in the reviewer -> reviewer_id migration.
 *
 * <pre>
 * phase        writes               reads                 needs schema
 * LEGACY       reviewer             reviewer              V1, V2
 * DUAL_WRITE   reviewer + id        reviewer              V2
 * READ_NEW     reviewer + id        reviewers.handle      V2
 * NEW_ONLY     id                   reviewers.handle      V2, V3
 * </pre>
 * Neighbouring phases can run side by side; that is what lets us roll forward one instance at a time.
 */
public enum ReviewerPhase {
    LEGACY, DUAL_WRITE, READ_NEW, NEW_ONLY;

    public boolean writesText() {
        return this != NEW_ONLY;
    }

    public boolean writesId() {
        return this != LEGACY;
    }

    public boolean readsId() {
        return this == READ_NEW || this == NEW_ONLY;
    }
}
