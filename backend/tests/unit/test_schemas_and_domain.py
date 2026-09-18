import pytest
from dataclasses import FrozenInstanceError
from pydantic import ValidationError

from app.domain.models.user import User
from app.schemas.user import (
    BatchMetadata,
    FailedUserDetail,
    UserBatchResponse,
    UserFetchRequest,
    UserResponse,
)


class TestUserDomainModel:
    """Testes unitários da entidade rica de domínio User (DDD)."""

    def test_user_creation_and_attributes(self):
        user = User(
            id=1,
            name="Alan Turing",
            username="aturing",
            email="alan@turing.org",
            phone="+44 1234 5678",
            website="turing.org",
            company_name="Bletchley Park",
        )
        assert user.id == 1
        assert user.name == "Alan Turing"
        assert user.username == "aturing"
        assert user.email == "alan@turing.org"
        assert user.phone == "+44 1234 5678"
        assert user.website == "turing.org"
        assert user.company_name == "Bletchley Park"

    def test_user_immutability_structural(self):
        """Garante que a entidade User é estritamente imutável (frozen=True)."""
        user = User(id=42, name="Ada Lovelace")
        with pytest.raises(FrozenInstanceError):
            user.name = "Ada Byron"  # type: ignore

    def test_display_identifier_with_username(self):
        user = User(id=1, name="Grace Hopper", username="ghopper")
        assert user.display_identifier == "Grace Hopper (@ghopper)"

    def test_display_identifier_without_username(self):
        user = User(id=2, name="Linus Torvalds", username=None)
        assert user.display_identifier == "Linus Torvalds"

    def test_display_identifier_with_empty_username(self):
        user = User(id=3, name="Dennis Ritchie", username="")
        assert user.display_identifier == "Dennis Ritchie"


class TestUserSchemas:
    """Testes unitários de validação semântica dos schemas Pydantic V2."""

    def test_valid_user_fetch_request(self):
        req = UserFetchRequest(user_ids=[1, 2, 3])
        assert req.user_ids == [1, 2, 3]

    def test_rejection_empty_user_ids_list(self):
        with pytest.raises(ValidationError) as exc_info:
            UserFetchRequest(user_ids=[])
        assert "A lista de IDs não pode ser vazia." in str(exc_info.value)

    def test_rejection_exceeding_max_batch_size(self):
        ids = list(range(1, 102))  # 101 IDs
        with pytest.raises(ValidationError) as exc_info:
            UserFetchRequest(user_ids=ids)
        assert "O limite máximo por lote é de 100 IDs." in str(exc_info.value)

    def test_rejection_negative_or_zero_ids(self):
        for invalid_id in [0, -1, -99]:
            with pytest.raises(ValidationError) as exc_info:
                UserFetchRequest(user_ids=[1, invalid_id, 2])
            assert f"O ID {invalid_id} é inválido" in str(exc_info.value)

    def test_deduplication_preserves_original_order(self):
        """Garante deduplicação determinística preservando a ordem via dict.fromkeys(v)."""
        input_ids = [5, 3, 5, 1, 3, 2, 1, 5, 4]
        req = UserFetchRequest(user_ids=input_ids)
        assert req.user_ids == [5, 3, 1, 2, 4]

    def test_rejection_non_integer_values(self):
        with pytest.raises(ValidationError):
            UserFetchRequest(user_ids=["not-an-int"])  # type: ignore

    def test_user_response_schema_defaults(self):
        res = UserResponse(id=1, name="Test User")
        assert res.id == 1
        assert res.name == "Test User"
        assert res.username is None
        assert res.cached is False

    def test_failed_user_detail_schema(self):
        detail = FailedUserDetail(user_id=99, status_code=404, reason="User not found")
        assert detail.user_id == 99
        assert detail.status_code == 404
        assert detail.reason == "User not found"

    def test_batch_metadata_schema(self):
        meta = BatchMetadata(
            total=10,
            success_count=8,
            failed_count=2,
            cache_hits=3,
            execution_time_ms=45.67,
            request_id="req-12345",
        )
        assert meta.total == 10
        assert meta.success_count == 8
        assert meta.failed_count == 2
        assert meta.cache_hits == 3
        assert meta.execution_time_ms == 45.67
        assert meta.request_id == "req-12345"

    def test_user_batch_response_schema_and_aliases(self):
        response = UserBatchResponse(
            users=[UserResponse(id=1, name="Alice", cached=True)],
            failed=[2],
            errors=[FailedUserDetail(user_id=2, status_code=404, reason="Not found")],
            meta=BatchMetadata(
                total=2,
                success_count=1,
                failed_count=1,
                cache_hits=1,
                execution_time_ms=12.3,
            ),
            total_requested=2,
            total_success=1,
            total_failed=1,
            duration_ms=12.3,
        )
        assert len(response.users) == 1
        assert response.failed == [2]
        assert len(response.errors) == 1
        assert response.meta.cache_hits == 1
        assert response.total_requested == 2
        assert response.total_success == 1
        assert response.total_failed == 1
        assert response.duration_ms == 12.3
