SmartFit Stage 2, Part C5 — Data in the product
The home page now displays a live statistics panel using SQLite queries:
SELECT COUNT(*), COUNT(DISTINCT LOWER(TRIM(goal))) FROM users;
SELECT goal, COUNT(*) AS entries FROM users GROUP BY LOWER(TRIM(goal)) ORDER BY entries DESC, goal ASC LIMIT 5;
The panel refreshes on each GET / request after form submissions.
Demo records are synthetic; do not interpret them as real user behavior.
For evidence: screenshot the statistics panel, add a DEMO entry, then screenshot the updated count.
Only main.py, templates/index.html and static/css/style.css require updating on GitHub.
