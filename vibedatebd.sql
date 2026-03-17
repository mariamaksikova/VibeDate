CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    tg_id         INTEGER UNIQUE NOT NULL,
    username      VARCHAR(100),
    referral_code VARCHAR(20) UNIQUE,         
    referred_by   INTEGER,                     
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE profiles (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER UNIQUE NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    age                 INTEGER,
    gender              CHAR(1),               
    city                VARCHAR(100),
    interests           TEXT,                 
    bio                 TEXT,
    min_age             INTEGER,
    max_age             INTEGER,
    looking_for         CHAR(1),             
    photo_count         INTEGER DEFAULT 0,
    completeness_score  INTEGER DEFAULT 0,   
    primary_rating      INTEGER DEFAULT 1000, 
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE photos (
    id         SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    s3_key     TEXT NOT NULL,                
    is_main    BOOLEAN DEFAULT FALSE,
    order_num  INTEGER DEFAULT 1
);

CREATE TABLE likes (
    id              SERIAL PRIMARY KEY,
    from_profile    INTEGER NOT NULL REFERENCES profiles(id),
    to_profile      INTEGER NOT NULL REFERENCES profiles(id),
    is_like         BOOLEAN NOT NULL,           
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (from_profile, to_profile)
);

CREATE TABLE matches (
    id          SERIAL PRIMARY KEY,
    profile1    INTEGER NOT NULL REFERENCES profiles(id),
    profile2    INTEGER NOT NULL REFERENCES profiles(id),
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (profile1, profile2)
);

CREATE TABLE ratings (
    profile_id          INTEGER PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    
    primary_rating      INTEGER NOT NULL DEFAULT 1000,
    
    likes_received      INTEGER DEFAULT 0,
    skips_received      INTEGER DEFAULT 0,
    matches_count       INTEGER DEFAULT 0,
    dialogs_started     INTEGER DEFAULT 0,     
    
    combined_rating     INTEGER NOT NULL DEFAULT 1000,
    
    updated_at          TIMESTAMP DEFAULT NOW()
);