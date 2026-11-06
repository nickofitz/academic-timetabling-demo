-- Academic Timetabling Demo 0.1; documentary revision 0.2.
-- Synthetic source data. Enable on EVERY connection, before transactions.
PRAGMA foreign_keys = ON;

-- SOURCE TABLES. Cross-row invariants are checked by the loader (see specification).
CREATE TABLE weeks (id INTEGER PRIMARY KEY CHECK(id >= 1));
CREATE TABLE days (id INTEGER PRIMARY KEY CHECK(id BETWEEN 1 AND 7));
CREATE TABLE blocks (
 id INTEGER PRIMARY KEY CHECK(id >= 1),
 start_time TEXT NOT NULL CHECK(length(start_time)=5 AND start_time GLOB '[0-2][0-9]:[0-5][0-9]' AND substr(start_time,1,2) <= '23'),
 end_time TEXT NOT NULL CHECK(length(end_time)=5 AND end_time GLOB '[0-2][0-9]:[0-5][0-9]' AND substr(end_time,1,2) <= '23'),
 CHECK(start_time < end_time)
);
CREATE TABLE teachers (id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL);
CREATE TABLE rooms (id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity > 0));
CREATE TABLE features (id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL);
CREATE TABLE room_features (
 room_id TEXT NOT NULL REFERENCES rooms(id), feature_id TEXT NOT NULL REFERENCES features(id),
 PRIMARY KEY(room_id,feature_id)
);
CREATE TABLE groups (
 id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL,
 basis TEXT NOT NULL CHECK(basis IN ('estudiantes_compartidos','regla_curricular'))
);
CREATE TABLE sections (
 id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL, teacher_id TEXT NOT NULL REFERENCES teachers(id),
 enrollment INTEGER NOT NULL CHECK(enrollment > 0),
 sessions_per_week INTEGER NOT NULL CHECK(sessions_per_week > 0),
 blocks_per_session INTEGER NOT NULL CHECK(blocks_per_session > 0)
);
CREATE TABLE section_groups (
 section_id TEXT NOT NULL REFERENCES sections(id), group_id TEXT NOT NULL REFERENCES groups(id),
 PRIMARY KEY(section_id,group_id)
);
CREATE TABLE section_features (
 section_id TEXT NOT NULL REFERENCES sections(id), feature_id TEXT NOT NULL REFERENCES features(id),
 PRIMARY KEY(section_id,feature_id)
);
CREATE TABLE section_weeks (
 section_id TEXT NOT NULL REFERENCES sections(id), week_id INTEGER NOT NULL REFERENCES weeks(id),
 PRIMARY KEY(section_id,week_id)
);
CREATE TABLE patterns (id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL);
CREATE TABLE pattern_sessions (
 pattern_id TEXT NOT NULL REFERENCES patterns(id), session_id TEXT NOT NULL,
 day_id INTEGER NOT NULL REFERENCES days(id), start_block_id INTEGER NOT NULL REFERENCES blocks(id),
 duration_blocks INTEGER NOT NULL CHECK(duration_blocks > 0),
 PRIMARY KEY(pattern_id,session_id)
);
CREATE TABLE section_patterns (
 section_id TEXT NOT NULL REFERENCES sections(id), pattern_id TEXT NOT NULL REFERENCES patterns(id),
 PRIMARY KEY(section_id,pattern_id)
);
CREATE TABLE teacher_available (
 teacher_id TEXT NOT NULL REFERENCES teachers(id), week_id INTEGER NOT NULL REFERENCES weeks(id),
 day_id INTEGER NOT NULL REFERENCES days(id), block_id INTEGER NOT NULL REFERENCES blocks(id),
 PRIMARY KEY(teacher_id,week_id,day_id,block_id)
);
CREATE TABLE room_available (
 room_id TEXT NOT NULL REFERENCES rooms(id), week_id INTEGER NOT NULL REFERENCES weeks(id),
 day_id INTEGER NOT NULL REFERENCES days(id), block_id INTEGER NOT NULL REFERENCES blocks(id),
 PRIMARY KEY(room_id,week_id,day_id,block_id)
);
CREATE TABLE room_reservations (
 room_id TEXT NOT NULL REFERENCES rooms(id), week_id INTEGER NOT NULL REFERENCES weeks(id),
 day_id INTEGER NOT NULL REFERENCES days(id), block_id INTEGER NOT NULL REFERENCES blocks(id), reason TEXT NOT NULL,
 PRIMARY KEY(room_id,week_id,day_id,block_id)
);
CREATE TABLE section_blocked (
 section_id TEXT NOT NULL REFERENCES sections(id), week_id INTEGER NOT NULL REFERENCES weeks(id),
 day_id INTEGER NOT NULL REFERENCES days(id), block_id INTEGER NOT NULL REFERENCES blocks(id), reason TEXT NOT NULL,
 PRIMARY KEY(section_id,week_id,day_id,block_id),
 FOREIGN KEY(section_id,week_id) REFERENCES section_weeks(section_id,week_id)
);
CREATE TABLE teacher_penalties (
 teacher_id TEXT NOT NULL REFERENCES teachers(id), day_id INTEGER NOT NULL REFERENCES days(id),
 block_id INTEGER NOT NULL REFERENCES blocks(id), penalty INTEGER NOT NULL CHECK(penalty >= 0),
 PRIMARY KEY(teacher_id,day_id,block_id)
);

-- DERIVED TABLES. Rebuilt per run; never source input for independent audit.
CREATE TABLE alternative (
 alt_id INTEGER PRIMARY KEY,
 section_id TEXT NOT NULL, pattern_id TEXT NOT NULL, room_id TEXT NOT NULL REFERENCES rooms(id),
 cost_d INTEGER NOT NULL CHECK(cost_d >= 0), cost_e INTEGER NOT NULL CHECK(cost_e >= 0),
 FOREIGN KEY(section_id,pattern_id) REFERENCES section_patterns(section_id,pattern_id),
 UNIQUE(section_id,pattern_id,room_id)
);
CREATE TABLE discarded_alternative (
 section_id TEXT NOT NULL, pattern_id TEXT NOT NULL, room_id TEXT NOT NULL REFERENCES rooms(id),
 rule TEXT NOT NULL CHECK(rule IN ('CAPACITY','FEATURES','TEACHER_UNAVAILABLE','ROOM_UNAVAILABLE','ROOM_RESERVED','PROTECTED_SLOT')),
 evidence_json TEXT NOT NULL,
 FOREIGN KEY(section_id,pattern_id) REFERENCES section_patterns(section_id,pattern_id),
 PRIMARY KEY(section_id,pattern_id,room_id,rule)
);
CREATE TABLE occupancy (
 alt_id INTEGER NOT NULL REFERENCES alternative(alt_id),
 resource_type TEXT NOT NULL CHECK(resource_type IN ('room','teacher','group')),
 resource_id TEXT NOT NULL,
 week_id INTEGER NOT NULL REFERENCES weeks(id), day_id INTEGER NOT NULL REFERENCES days(id), block_id INTEGER NOT NULL REFERENCES blocks(id),
 PRIMARY KEY(alt_id,resource_type,resource_id,week_id,day_id,block_id)
);
CREATE INDEX idx_occupancy_slot ON occupancy(resource_type,resource_id,week_id,day_id,block_id);
-- Polymorphic resource_id and valid evidence_json are checked by preprocessing.
-- Pattern bounds/overlaps, minimum memberships, equal block duration, contiguous IDs,
-- and declared numeric/text types are validated by the loader, not SQLite affinity alone.
