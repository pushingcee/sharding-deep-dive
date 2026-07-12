package org.learn.service.commons;

import org.learn.domain.User;
import org.learn.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.UUID;

@Service
@Profile({"single", "sharded", "lookup"})
public class UserService implements org.learn.service.UserService {
    private final UserRepository userRepository;

    public UserService(@Autowired UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public Optional<User> getUser(UUID user_uuid) {
        return userRepository.findById(user_uuid);
    }
}
