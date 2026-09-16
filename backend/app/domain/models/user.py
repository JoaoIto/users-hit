from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class User:
    """Entidade pura de domínio representando um usuário de negócio."""
    id: int
    name: str
    username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    company_name: Optional[str] = None

    @property
    def display_identifier(self) -> str:
        return f"{self.name} (@{self.username})" if self.username else self.name
