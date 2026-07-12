package org.learn.domain;

import lombok.Data;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.UUID;

@Data
public class User {
    UUID user_id;
    String firstName;
    String lastName;
    String email;
    String country;
    LocalDateTime createdAt;
    LocalDate lastActive;
    // TODO: add preferences beware of the nesting hehexd
}
