from dataclasses import dataclass


@dataclass(frozen=True)
class DbConfig:
    host: str = "localhost"
    port: int = 5432
    dbname: str = "mydb"
    user: str = "postgres"
    password: str = ""

    @property
    def conninfo(self) -> str:
        """psycopg connection string. Only this property carries the password —
        __str__ stays safe to log."""
        return f"host={self.host} port={self.port} dbname={self.dbname} user={self.user} password={self.password}"

    def __str__(self) -> str:
        return f"{self.host}:{self.port}/{self.dbname}"
