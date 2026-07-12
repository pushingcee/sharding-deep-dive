package org.learn.repository.commons;

/**
 * Shared SQL for user reads — same statement in every strategy; only the
 * routing (which shard receives it) differs per profile.
 */
public final class UserSql {

    public static final String FIND_BY_ID =
        "SELECT user_id, first_name, last_name, email, country, created_at, last_active " +
        "FROM users WHERE user_id = ?";

    private UserSql() {
    }
}
