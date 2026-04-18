BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0a6980e2578f

CREATE TABLE users (
    id SERIAL NOT NULL, 
    username VARCHAR(50) NOT NULL, 
    hashed_password VARCHAR(128) NOT NULL, 
    role VARCHAR(20), 
    created_at TIMESTAMP(3) WITH TIME ZONE, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_users_id ON users (id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE chat_sessions (
    id SERIAL NOT NULL, 
    session_id VARCHAR(64), 
    user_id INTEGER, 
    title VARCHAR(200), 
    created_at TIMESTAMP(3) WITH TIME ZONE, 
    updated_at TIMESTAMP(3) WITH TIME ZONE, 
    message_count INTEGER, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_chat_sessions_id ON chat_sessions (id);

CREATE UNIQUE INDEX ix_chat_sessions_session_id ON chat_sessions (session_id);

CREATE TABLE documents (
    id SERIAL NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    doc_hash VARCHAR(32), 
    pages INTEGER, 
    chunk_count INTEGER, 
    uploaded_by INTEGER, 
    uploaded_at TIMESTAMP(3) WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(uploaded_by) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_documents_doc_hash ON documents (doc_hash);

CREATE INDEX ix_documents_id ON documents (id);

CREATE TABLE chat_messages (
    id SERIAL NOT NULL, 
    session_id VARCHAR(64), 
    role VARCHAR(16), 
    content TEXT, 
    created_at TIMESTAMP(3) WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES chat_sessions (session_id)
);

CREATE INDEX ix_chat_messages_id ON chat_messages (id);

CREATE INDEX ix_chat_messages_session_id ON chat_messages (session_id);

INSERT INTO alembic_version (version_num) VALUES ('0a6980e2578f') RETURNING alembic_version.version_num;

COMMIT;

