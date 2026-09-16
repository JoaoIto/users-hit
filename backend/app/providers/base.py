from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseUserProvider(ABC):
    """Contrato abstrato para provedores externos de dados de usuário.
    
    Permite desacoplar a camada de serviços da implementação concreta da API externa,
    facilitando testes, mocks e substituição do provedor sem tocar nas regras de negócio.
    """

    @abstractmethod
    async def fetch_user_by_id(self, user_id: int) -> Dict[str, Any]:
        """Consulta um usuário individual pelo seu identificador único.
        
        Args:
            user_id: Identificador numérico do usuário.
            
        Returns:
            Dict[str, Any]: Dicionário contendo os dados brutos do usuário.
            
        Raises:
            UserNotFoundError: Quando o usuário não for encontrado (HTTP 404).
            ProviderError: Para erros de rede, timeout, rate limit ou status HTTP 5xx.
        """
        pass
