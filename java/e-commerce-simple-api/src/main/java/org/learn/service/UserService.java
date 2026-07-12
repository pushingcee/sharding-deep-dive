package org.learn.service;

import org.learn.domain.User;

import java.util.Optional;
import java.util.UUID;

public interface UserService {
    Optional<User> getUser(UUID user_uuid);
}
