package org.learn.controller;

import org.learn.domain.User;
import org.learn.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Optional;
import java.util.UUID;

@RestController
@RequestMapping("/users")
public class UserController {
    private final UserService userService;

    public UserController(@Autowired UserService userService){
        this.userService = userService;
    }

    @GetMapping("/{uuid}")
    public ResponseEntity<User> getUser(@PathVariable UUID uuid){
        Optional<User> userOptional = this.userService.getUser(uuid);

        return userOptional
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
