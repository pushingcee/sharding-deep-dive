package org.learn.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import lombok.Data;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.UUID;

@Data
@Entity(name="users")
public class User {
    @Id
    @GeneratedValue
    @Column(name = "user_id")
    UUID user_id;
    String firstName;
    String lastName;
    String email;
    @Column(name = "country", columnDefinition = "bpchar") // Use PostgreSQL's internal type name
    String country;
    LocalDateTime createdAt;
    LocalDate lastActive;
    // TODO: add preferences beware of the nesting hehexd
}
