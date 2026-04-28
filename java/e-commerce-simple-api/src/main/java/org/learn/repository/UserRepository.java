package org.learn.repository;

import org.learn.domain.User;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface UserRepository {
    Optional<User> findById(UUID userId);
    List<User> findAll();
}
