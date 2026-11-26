// Before q04: a second constructor for tests, and Spring no longer knew which one to use.
// @learn:before-repo-constructors
public TaskRepository(JdbcTemplate db, PhaseHolder phase) {
    this(db, phase.phase());
}

public TaskRepository(JdbcTemplate db, ReviewerPhase phase) {
    this.db = db;
    this.phase = phase;
}
// @learn:end before-repo-constructors
