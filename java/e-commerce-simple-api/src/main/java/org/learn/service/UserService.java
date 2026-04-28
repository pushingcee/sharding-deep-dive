package org.learn.service;

import org.learn.domain.User;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface UserService {
    public Optional<User> getUser(UUID user_uuid);
    public List<User> getAllUsers();
}
