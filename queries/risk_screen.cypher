MATCH (s:Supplier)-[:SUPPLIES]->(m:Material)
WHERE s.disruption_risk_score >= 60
RETURN m.material_id, m.name, avg(s.disruption_risk_score) AS supplier_risk
ORDER BY supplier_risk DESC
