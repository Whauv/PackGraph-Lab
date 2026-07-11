MATCH (m:Material {material_id: $material_id})-[:HAS_DOCUMENT]->(d:SourceDocument)
OPTIONAL MATCH (m)<-[:SUPPLIES]-(s:Supplier)
RETURN m.name, collect(DISTINCT d.title) AS documents, collect(DISTINCT s.name) AS suppliers
