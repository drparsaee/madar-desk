/*
  PARSIAN v39 SCHEMA-ONLY reconnaissance. NO actual rows or finance values.
  Run ONLY after a qualified operator has restored an explicitly authorized
  copy to a SEPARATE SQL SERVER INSTANCE named MADARQA_*, and a database
  named MADARQA_PARSIAN_*.

  DO NOT run against MSSQLSERVER, ESKO, Parsian live DB, or an instance
  sharing production files. This script never restores or changes a database.

  Example AFTER isolated clone exists:
    sqlcmd -S .\MADARQA_P39 -d MADARQA_PARSIAN_CLONE -E -b -i scripts\parsian_cloned_schema_readonly.sql
*/
SET NOCOUNT ON;
DECLARE @instance nvarchar(128) = CONVERT(nvarchar(128), SERVERPROPERTY('InstanceName'));
DECLARE @database nvarchar(128) = DB_NAME();
IF (@instance IS NULL OR UPPER(@instance) NOT LIKE N'MADARQA[_]%' OR
    @database IS NULL OR UPPER(@database) NOT LIKE N'MADARQA[_]PARSIAN[_]%')
BEGIN
    THROW 51042, 'REFUSED: dedicated MADARQA_* SQL instance and MADARQA_PARSIAN_* clone database required', 1;
END;

-- (1) Revision-aware, database-local schema/columns/types. No row values.
SELECT s.name AS schema_name, t.name AS table_name,
       c.column_id, c.name AS column_name, ty.name AS system_type,
       c.max_length, c.precision, c.scale, c.is_nullable
FROM sys.tables AS t
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
JOIN sys.columns AS c ON c.object_id = t.object_id
JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE t.is_ms_shipped = 0
ORDER BY s.name, t.name, c.column_id;

-- (2) Candidate primary/composite keys: establishes grain for later audits.
SELECT s.name AS schema_name, t.name AS table_name,
       kc.name AS key_name, ic.key_ordinal, c.name AS column_name
FROM sys.key_constraints AS kc
JOIN sys.tables AS t ON t.object_id = kc.parent_object_id
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
JOIN sys.index_columns AS ic ON ic.object_id = t.object_id
    AND ic.index_id = kc.unique_index_id AND ic.key_ordinal > 0
JOIN sys.columns AS c ON c.object_id = t.object_id AND c.column_id = ic.column_id
WHERE kc.type = 'PK'
ORDER BY s.name, t.name, kc.name, ic.key_ordinal;

-- (3) Source-defined references. Absence of a declared FK is NOT evidence
-- that business references do not exist in application code.
SELECT psch.name AS from_schema, parent.name AS from_table,
       pc.name AS from_column, rsch.name AS to_schema,
       referenced.name AS to_table, rc.name AS to_column,
       fk.name AS foreign_key_name, fkc.constraint_column_id
FROM sys.foreign_key_columns AS fkc
JOIN sys.foreign_keys AS fk ON fk.object_id = fkc.constraint_object_id
JOIN sys.tables AS parent ON parent.object_id = fkc.parent_object_id
JOIN sys.schemas AS psch ON psch.schema_id = parent.schema_id
JOIN sys.columns AS pc ON pc.object_id = parent.object_id
    AND pc.column_id = fkc.parent_column_id
JOIN sys.tables AS referenced ON referenced.object_id = fkc.referenced_object_id
JOIN sys.schemas AS rsch ON rsch.schema_id = referenced.schema_id
JOIN sys.columns AS rc ON rc.object_id = referenced.object_id
    AND rc.column_id = fkc.referenced_column_id
ORDER BY psch.name,parent.name,fk.name,fkc.constraint_column_id;

-- No SELECT from business tables, UPDATE, INSERT, DELETE, RESTORE or DBCC.
