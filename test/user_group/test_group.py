import pytest

from user_group_db.models import User, Group


def test_create_group(session):
    Group.create(name="Test Group", session=session)
    assert Group.get_by_name("Test Group", session) is not None


def test_create_group_with_existing_name(session):
    Group.create(name="Test Group", session=session)
    with pytest.raises(ValueError):
        Group.create(name="Test Group", session=session)


def test_create_group_with_users(session):
    User.create(user_id="123456789", username="TestUser", session=session)
    Group.create(name="Test Group", usernames=["TestUser"], session=session)
    assert Group.get_by_name("Test Group", session) is not None
    assert Group.get_by_name("Test Group", session)["users_count"] == 1


def test_delete_group(session):
    group = Group.create(name="Test Group", session=session)
    assert Group.delete_by_id(group["id"], session) is True
    assert Group.get_by_name("Test Group", session) is None


def test_add_user_to_group(session):
    User.create(user_id="123456789", username="Test User", session=session)
    group = Group.create(name="Test Group", session=session)
    assert Group.add_user(group["id"], "123456789", session) is True
    assert Group.get_by_name("Test Group", session) is not None


def test_remove_user_from_group(session):
    User.create(user_id="123456789", username="Test User", session=session)
    group = Group.create(name="Test Group", session=session)
    assert Group.add_user(group["id"], "123456789", session) is True
    assert Group.remove_user(group["id"], "123456789", session) is True
    assert Group.get_by_name("Test Group", session) is not None
    assert Group.get_by_name("Test Group", session)["users_count"] == 0


def test_create_group_with_owner(session):
    User.create(user_id="123456789", username="Test Owner", session=session)
    Group.create(name="Test Group", owner_id="123456789", session=session)
    group_data = Group.get_by_name("Test Group", session)
    assert group_data is not None
    assert group_data["owner"] is not None
    assert group_data["owner"]["user_id"] == "123456789"
    assert group_data["owner"]["username"] == "Test Owner"


def test_create_group_without_owner(session):
    Group.create(name="Test Group", session=session)
    group_data = Group.get_by_name("Test Group", session)
    assert group_data is not None
    assert group_data["owner"] is None


def test_create_group_with_invalid_owner(session):
    with pytest.raises(ValueError, match="Owner with user_id '999' not found"):
        Group.create(name="Test Group", owner_id="999", session=session)
