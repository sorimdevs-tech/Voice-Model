"""
VOXA Backend — Data Service (Layer 8: Data Lake)
Loads Excel data into DuckDB in-memory analytical database.
Provides query execution and pre-computed aggregations for the plant manager dashboard.
"""

import duckdb
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("voxa.data")


class DataService:
    """
    DuckDB-backed data layer.
    - Loads Excel files at startup into in-memory tables
    - Provides SQL query execution
    - Pre-computes common dashboard aggregations
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.conn = duckdb.connect(":memory:")
        self._loaded = False

    def load_data(self):
        """Load Excel files into DuckDB tables."""
        try:
            # ── Load Sales by Models ──
            models_path = self.data_dir / "Sales by Models.xlsx"
            if models_path.exists():
                df_models = pd.read_excel(models_path, engine="openpyxl")
                # Clean column names: cast to string, strip whitespace, lowercase, replace spaces with underscores
                df_models.columns = [
                    str(col).strip().lower().replace(" ", "_").replace("(", "").replace(")", "")
                    for col in df_models.columns
                ]
                self.conn.execute("DROP TABLE IF EXISTS sales_by_models")
                self.conn.execute("CREATE TABLE sales_by_models AS SELECT * FROM df_models")
                row_count = self.conn.execute("SELECT COUNT(*) FROM sales_by_models").fetchone()[0]
                logger.info(f"Loaded sales_by_models: {row_count} rows")
            else:
                logger.warning(f"File not found: {models_path}")

            # ── Load Sales by Plant ──
            plant_path = self.data_dir / "Sales by Plant.xlsx"
            if plant_path.exists():
                df_plant = pd.read_excel(plant_path, engine="openpyxl")
                df_plant.columns = [
                    str(col).strip().lower().replace(" ", "_").replace("(", "").replace(")", "")
                    for col in df_plant.columns
                ]
                self.conn.execute("DROP TABLE IF EXISTS sales_by_plant")
                self.conn.execute("CREATE TABLE sales_by_plant AS SELECT * FROM df_plant")
                row_count = self.conn.execute("SELECT COUNT(*) FROM sales_by_plant").fetchone()[0]
                logger.info(f"Loaded sales_by_plant: {row_count} rows")
            else:
                logger.warning(f"File not found: {plant_path}")

            self._loaded = True
            logger.info("Data service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            raise

    def get_table_schemas(self) -> dict:
        """Get column names and types for all loaded tables."""
        schemas = {}
        tables = self.conn.execute("SHOW TABLES").fetchall()
        for (table_name,) in tables:
            columns = self.conn.execute(f"DESCRIBE {table_name}").fetchall()
            schemas[table_name] = [
                {"name": col[0], "type": str(col[1])} for col in columns
            ]
        return schemas

    def get_table_schemas_text(self) -> str:
        """Get a formatted text representation of all table schemas."""
        schemas = self.get_table_schemas()
        lines = []
        for table_name, columns in schemas.items():
            lines.append(f"\n### Table: `{table_name}`")
            lines.append("| Column | Type |")
            lines.append("|--------|------|")
            for col in columns:
                lines.append(f"| {col['name']} | {col['type']} |")
        return "\n".join(lines)

    def get_sample_data(self, table_name: str, limit: int = 5) -> str:
        """Get sample rows from a table as formatted text."""
        try:
            df = self.conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}").fetchdf()
            return df.to_markdown(index=False)
        except Exception as e:
            return f"Error fetching sample: {e}"

    def execute_query(self, sql: str) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame."""
        try:
            return self.conn.execute(sql).fetchdf()
        except Exception as e:
            logger.error(f"Query error: {e}")
            raise

    def query_to_markdown(self, sql: str) -> str:
        """Execute query and return results as markdown table."""
        df = self.execute_query(sql)
        if df.empty:
            return "*No data found for this query.*"
        return df.to_markdown(index=False)

    def get_all_data_context(self) -> str:
        """
        Build a comprehensive data context string for the LLM.
        Includes schemas, sample data, and key aggregations.
        """
        context_parts = []

        # Table schemas
        context_parts.append("## Available Data Tables")
        context_parts.append(self.get_table_schemas_text())

        # Sample data from each table
        tables = self.conn.execute("SHOW TABLES").fetchall()
        for (table_name,) in tables:
            context_parts.append(f"\n## Sample Data from `{table_name}` (first 5 rows)")
            context_parts.append(self.get_sample_data(table_name, 5))

        # Summary statistics
        context_parts.append("\n## Summary Statistics")
        for (table_name,) in tables:
            try:
                count = self.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                context_parts.append(f"- `{table_name}`: **{count}** total rows")

                # Get numeric columns for aggregation
                cols = self.conn.execute(f"DESCRIBE {table_name}").fetchall()
                numeric_cols = [
                    col[0] for col in cols
                    if any(t in str(col[1]).upper() for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BIGINT"])
                ]
                if numeric_cols:
                    for nc in numeric_cols[:5]:  # Limit to first 5 numeric columns
                        try:
                            stats = self.conn.execute(
                                f"SELECT MIN({nc}), MAX({nc}), ROUND(AVG({nc}), 2), ROUND(SUM({nc}), 2) FROM {table_name}"
                            ).fetchone()
                            context_parts.append(
                                f"  - `{nc}`: min={stats[0]}, max={stats[1]}, avg={stats[2]}, total={stats[3]}"
                            )
                        except Exception:
                            pass
            except Exception as e:
                context_parts.append(f"- `{table_name}`: Error getting stats: {e}")

        return "\n".join(context_parts)

    def get_full_data_dump(self) -> str:
        """
        Dump ALL data as markdown tables for LLM context.
        Only suitable for small datasets (<1000 rows total).
        """
        parts = []
        tables = self.conn.execute("SHOW TABLES").fetchall()
        for (table_name,) in tables:
            count = self.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            if count <= 500:
                parts.append(f"\n## Complete Data: `{table_name}` ({count} rows)")
                df = self.conn.execute(f"SELECT * FROM {table_name}").fetchdf()
                parts.append(df.to_markdown(index=False))
            else:
                parts.append(f"\n## Data: `{table_name}` (showing first 100 of {count} rows)")
                df = self.conn.execute(f"SELECT * FROM {table_name} LIMIT 100").fetchdf()
                parts.append(df.to_markdown(index=False))
        return "\n".join(parts)

    def get_column_values(self, table_name: str, column_name: str) -> list:
        """Get distinct values for a column."""
        try:
            result = self.conn.execute(
                f"SELECT DISTINCT {column_name} FROM {table_name} ORDER BY {column_name}"
            ).fetchall()
            return [row[0] for row in result]
        except Exception:
            return []


# Singleton instance
_data_service: DataService | None = None


def get_data_service() -> DataService:
    """Get the singleton DataService instance."""
    global _data_service
    if _data_service is None:
        raise RuntimeError("DataService not initialized. Call init_data_service() first.")
    return _data_service


def init_data_service(data_dir: Path) -> DataService:
    """Initialize and return the DataService singleton."""
    global _data_service
    _data_service = DataService(data_dir)
    _data_service.load_data()
    return _data_service
