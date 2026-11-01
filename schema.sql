CREATE DATABASE IF NOT EXISTS accesslearn CHARACTER SET utf8mb4;
USE accesslearn;

CREATE TABLE IF NOT EXISTS Users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(150) UNIQUE,
  role ENUM('student','teacher') DEFAULT 'student',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS Lectures (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  title VARCHAR(200) NOT NULL,
  video_file VARCHAR(255),
  summary TEXT,
  level VARCHAR(20),
  duration_sec INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES Users(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS Transcripts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  lecture_id INT NOT NULL,
  start_sec FLOAT NOT NULL,
  text TEXT NOT NULL,
  corrected TINYINT(1) DEFAULT 0,
  FOREIGN KEY (lecture_id) REFERENCES Lectures(id) ON DELETE CASCADE,
  INDEX (lecture_id, start_sec)
);
CREATE TABLE IF NOT EXISTS Concepts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  definition TEXT
);
CREATE TABLE IF NOT EXISTS LectureConcepts (
  lecture_id INT NOT NULL,
  concept_id INT NOT NULL,
  first_sec FLOAT DEFAULT 0,
  mentions INT DEFAULT 1,
  PRIMARY KEY (lecture_id, concept_id),
  FOREIGN KEY (lecture_id) REFERENCES Lectures(id) ON DELETE CASCADE,
  FOREIGN KEY (concept_id) REFERENCES Concepts(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ConceptRelationships (
  concept_a INT NOT NULL,
  concept_b INT NOT NULL,
  PRIMARY KEY (concept_a, concept_b),
  FOREIGN KEY (concept_a) REFERENCES Concepts(id) ON DELETE CASCADE,
  FOREIGN KEY (concept_b) REFERENCES Concepts(id) ON DELETE CASCADE
);
