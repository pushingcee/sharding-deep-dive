package org.learn.repository.single;

import org.learn.domain.User;
import org.springframework.context.annotation.Profile;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

@Profile("single")
public interface UserRepository extends JpaRepository<User, UUID> {
}
