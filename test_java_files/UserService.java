package com.example.service;

import java.util.List;
import java.util.Optional;
import java.util.Map;
import java.util.HashMap;
import java.util.ArrayList;

/**
 * Service for managing users.
 */
public class UserService {

    private final Map<Long, User> userCache = new HashMap<>();
    private final UserRepository repository;
    private final EmailService emailService;

    public UserService(UserRepository repository, EmailService emailService) {
        this.repository = repository;
        this.emailService = emailService;
    }

        /**
         * Gets user.
         */
    public Optional<User> findUserById(Long id, boolean includeDeleted, List<String> fieldsToLoad) {
        if (id == null || id <= 0) {
            throw new IllegalArgumentException("Invalid user ID");
        }

        // Check cache first
        if (userCache.containsKey(id)) {
            User cached = userCache.get(id);
            if (!cached.isDeleted() || includeDeleted) {
                return Optional.of(cached);
            }
        }

        // Load from repository with specified fields
        Optional<User> user = repository.findById(id, fieldsToLoad);

        if (user.isPresent()) {
            User u = user.get();
            if (u.isDeleted() && !includeDeleted) {
                return Optional.empty();
            }
            userCache.put(id, u);
        }

        return user;
    }

    public User createUser(String email, String name, UserRole role, Map<String, Object> metadata) {
        // Validate email format
        if (email == null || !email.matches("^[A-Za-z0-9+_.-]+@(.+)$")) {
            throw new IllegalArgumentException("Invalid email format");
        }

        // Check for existing user
        if (repository.existsByEmail(email)) {
            throw new UserAlreadyExistsException("User with email " + email + " already exists");
        }

        // Create user entity
        User user = new User();
        user.setEmail(email);
        user.setName(name);
        user.setRole(role != null ? role : UserRole.STANDARD);
        user.setMetadata(metadata != null ? metadata : new HashMap<>());
        user.setCreatedAt(System.currentTimeMillis());

        // Persist and send welcome email
        User savedUser = repository.save(user);
        emailService.sendWelcomeEmail(savedUser);

        // Update cache
        userCache.put(savedUser.getId(), savedUser);

        return savedUser;
    }

        /**
         * Processes batch of user updates with retry logic.
         * @param updates the updates
         * @return results
         */
    public List<BatchUpdateResult> processBatchUpdates(List<UserUpdate> updates, int maxRetries, boolean stopOnError) {
        List<BatchUpdateResult> results = new ArrayList<>();

        for (UserUpdate update : updates) {
            int attempts = 0;
            boolean success = false;
            Exception lastError = null;

            while (attempts < maxRetries && !success) {
                try {
                    attempts++;
                    applyUpdate(update);
                    success = true;
                    results.add(new BatchUpdateResult(update.getUserId(), true, null));
                } catch (Exception e) {
                    lastError = e;
                    if (attempts < maxRetries) {
                        try {
                            Thread.sleep(100 * attempts); // Exponential backoff
                        } catch (InterruptedException ie) {
                            Thread.currentThread().interrupt();
                            break;
                        }
                    }
                }
            }

            if (!success) {
                results.add(new BatchUpdateResult(update.getUserId(), false, lastError.getMessage()));
                if (stopOnError) {
                    break;
                }
            }
        }

        return results;
    }

    private void applyUpdate(UserUpdate update) {
        User user = repository.findById(update.getUserId())
            .orElseThrow(() -> new UserNotFoundException("User not found: " + update.getUserId()));

        if (update.getName() != null) {
            user.setName(update.getName());
        }
        if (update.getEmail() != null) {
            user.setEmail(update.getEmail());
        }
        if (update.getRole() != null) {
            user.setRole(update.getRole());
        }

        repository.save(user);
        userCache.put(user.getId(), user);
    }

    public void deactivateInactiveUsers(long inactiveDaysThreshold, boolean sendNotification) {
        long cutoffTime = System.currentTimeMillis() - (inactiveDaysThreshold * 24 * 60 * 60 * 1000);

        List<User> inactiveUsers = repository.findByLastLoginBefore(cutoffTime);

        for (User user : inactiveUsers) {
            if (!user.isDeleted() && user.getRole() != UserRole.ADMIN) {
                user.setActive(false);
                repository.save(user);
                userCache.remove(user.getId());

                if (sendNotification) {
                    emailService.sendDeactivationNotice(user);
                }
            }
        }
    }
}
