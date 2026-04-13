from dataclasses import dataclass

@dataclass
class DbConfig:
    host: str = "localhost"
    port: int = 5432
    dbname: str = "mydb"
    user: str = "postgres"
    password: str = ""
    
    def __str__(self) -> str:
        return f"host={self.host} port={self.port} dbname={self.dbname} user={self.user} password={self.password}"
    
    def to_dict(self) -> dict[str, str | int]:
        """Convert to dictionary for psycopg connection."""
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password
        }
    
    def __getitem__(self, key: str) -> str | int:
        """Support dict-like access for backward compatibility."""
        value: str | int = getattr(self, key)
        return value