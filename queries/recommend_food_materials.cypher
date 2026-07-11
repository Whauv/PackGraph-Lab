MATCH (m:Material)-[:TARGETS_APPLICATION]->(a:Application)
WHERE m.food_contact_safe = true
RETURN m.material_id, m.name, m.sustainability_score, collect(a.name) AS applications
ORDER BY m.sustainability_score DESC
LIMIT 10
