INSERT INTO courses (course_id, course_name, credit_hours) VALUES
    (201, 'Data Engineering', 3),
    (202, 'Database Systems', 3),
    (203, 'Machine Learning', 4),
    (204, 'Python Programming', 3);

-- The score of 105 for student 1010 is intentionally invalid raw data.
INSERT INTO enrollments (student_id, course_id, semester, score) VALUES
    (1001, 201, '2026-Fall', 93),
    (1002, 202, '2026-Fall', 88),
    (1003, 203, '2026-Fall', 77),
    (1004, 204, '2026-Fall', 91),
    (1005, 201, '2026-Fall', 85),
    (1006, 202, '2026-Fall', 79),
    (1007, 203, '2026-Fall', 95),
    (1008, 204, '2026-Fall', 67),
    (1009, 201, '2026-Fall', 58),
    (1010, 202, '2026-Fall', 105),
    (1011, 203, '2026-Fall', 73),
    (1012, 204, '2026-Fall', 89);
