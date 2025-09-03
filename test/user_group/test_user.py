import pytest

from user_group_db.models import User


def test_create_user(session):
    User.create(user_id="123456789", username="Test User", session=session)
    assert User.get_by_user_id("123456789", session) is not None


def test_create_user_with_existing_user_id(session):
    User.create(user_id="123456789", username="Test User", session=session)
    with pytest.raises(ValueError):
        User.create(user_id="123456789", username="Test User", session=session)


def test_get_user_by_user_id(session):
    User.create(user_id="123456789", username="Test User", session=session)
    user = User.get_by_user_id("123456789", session)
    assert user is not None
    assert user["user_id"] == "123456789"
    assert user["username"] == "Test User"


def test_get_user_by_user_id_not_found(session):
    user = User.get_by_user_id("123456789", session)
    assert user is None
