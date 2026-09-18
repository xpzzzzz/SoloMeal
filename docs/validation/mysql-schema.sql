CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_identity

CREATE TABLE users (
    id VARCHAR(36) NOT NULL, 
    username VARCHAR(64) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_users_username UNIQUE (username)
);

CREATE TABLE user_preferences (
    user_id VARCHAR(36) NOT NULL, 
    equipment JSON NOT NULL, 
    excluded_ingredients JSON NOT NULL, 
    default_servings INTEGER NOT NULL, 
    max_minutes INTEGER NOT NULL, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE auth_sessions (
    token_hash VARCHAR(64) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    expires_at INTEGER NOT NULL, 
    PRIMARY KEY (token_hash), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at);

INSERT INTO alembic_version (version_num) VALUES ('0001_identity');

