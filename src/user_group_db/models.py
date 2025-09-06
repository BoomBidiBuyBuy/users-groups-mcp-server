from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Table,
    Text,
    Boolean,
)
from typing import List, Optional
import logging
from sqlalchemy.sql import func

from sqlalchemy.orm import relationship

from storage import Base

logger = logging.getLogger(__name__)

# Many-to-many association table between groups and users
group_user_association = Table(
    "group_user_association",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
)


class Group(Base):
    """Group model"""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship with users through association table
    users = relationship(
        "User", secondary=group_user_association, back_populates="groups"
    )

    def __repr__(self):
        return f"<Group(id={self.id}, name='{self.name}')>"

    @classmethod
    def create(
        cls,
        name: str,
        session,
        user_ids: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Create a group and optionally attach users by their telegram IDs.

        Returns a dict mirroring previous GroupDatabase.create_group output.
        """
        # Check existing
        existing_group = session.query(cls).filter(cls.name == name).first()
        if existing_group:
            raise ValueError(f"Group with name '{name}' already exists")

        group = cls(name=name, description=description)
        session.add(group)
        session.flush()

        users_count = 0
        if user_ids:
            for user_id in user_ids:
                user = session.query(User).filter(User.user_id == user_id).first()
                if user:
                    group.users.append(user)
                    users_count += 1
                else:
                    logger.warning(f"User with user_id {user_id} not found")

        session.commit()

        logger.info(f"Group '{name}' created successfully")
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "users_count": users_count,
            "created_at": group.created_at,
        }

    @classmethod
    def delete_by_id(cls, group_id: int, session) -> bool:
        """Delete group by ID. Returns True if deleted, False if not found."""
        group = session.query(cls).filter(cls.id == group_id).first()
        if not group:
            logger.warning(f"Group with ID {group_id} not found")
            return False
        session.delete(group)
        session.commit()
        logger.info(f"Group '{group.name}' deleted successfully")
        return True

    @classmethod
    def add_user(cls, group_id: int, user_id: str, session) -> bool:
        """Add a user (by user_id) to the group. Returns True on success."""
        group = session.query(cls).filter(cls.id == group_id).first()
        if not group:
            logger.warning(f"Group with ID {group_id} not found")
            return False

        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            logger.warning(f"User with user_id {user_id} not found")
            return False

        if user in group.users:
            logger.info(f"User {user_id} is already in group '{group.name}'")
            return True

        group.users.append(user)
        session.commit()
        logger.info(f"User {user_id} added to group '{group.name}'")
        return True

    @classmethod
    def remove_user(cls, group_id: int, user_id: str, session) -> bool:
        """Remove a user (by user_id) from the group. Returns True on success."""
        group = session.query(cls).filter(cls.id == group_id).first()
        if not group:
            logger.warning(f"Group with ID {group_id} not found")
            return False

        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            logger.warning(f"User with user_id {user_id} not found")
            return False

        if user not in group.users:
            logger.warning(f"User {user_id} is not in group '{group.name}'")
            return False

        group.users.remove(user)
        session.commit()
        logger.info(f"User {user_id} removed from group '{group.name}'")
        return True

    @classmethod
    def get_all(cls, session) -> List[dict]:
        """Return list of all groups as dicts with users_count."""
        groups = session.query(cls).all()
        result: List[dict] = []
        for group in groups:
            result.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                    "created_at": group.created_at,
                    "updated_at": group.updated_at,
                    "users_count": len(group.users),
                }
            )
        logger.info(f"Retrieved {len(groups)} groups")
        return result

    @classmethod
    def get_by_id(cls, group_id: int, session) -> Optional[dict]:
        """Return group by ID as dict with users list, or None."""
        group = session.query(cls).filter(cls.id == group_id).first()
        if not group:
            return None
        users = []
        for user in group.users:
            users.append(
                {
                    "id": user.id,
                    "user_id": user.user_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                }
            )
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "users": users,
            "users_count": len(users),
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        }

    @classmethod
    def get_by_name(cls, name: str, session) -> Optional[dict]:
        """Return group by name as dict with users list, or None."""
        group = session.query(cls).filter(cls.name == name).first()
        if not group:
            return None
        users = []
        for user in group.users:
            users.append(
                {
                    "id": user.id,
                    "user_id": user.user_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                }
            )
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "users": users,
            "users_count": len(users),
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        }


class User(Base):
    """User model"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), unique=True, nullable=True, index=True)
    username = Column(String(255), unique=True, nullable=True, index=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_activated = Column(Boolean, nullable=False, default=False)

    # Relationship with groups through association table
    groups = relationship(
        "Group", secondary=group_user_association, back_populates="users"
    )

    def __repr__(self):
        return f"<User(id={self.id}, user_id={self.user_id}, username='{self.username}', is_activated={self.is_activated})>"

    @classmethod
    def create(
        cls,
        session,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        is_activated: Optional[bool] = False,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> "User":
        """Create a new user. Raises ValueError if user_id exists."""
        if user_id and username:
            raise ValueError("Cannot create user with both user_id and username")

        user = cls(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_activated=is_activated,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info(f"User with user_id {user_id} created successfully")
        return user

    @classmethod
    def get_all(cls, session) -> List[dict]:
        """Return list of all users as dicts with groups_count."""
        users = session.query(cls).all()
        result: List[dict] = []
        for user in users:
            result.append(
                {
                    "id": user.id,
                    "user_id": user.user_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_activated": user.is_activated,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                    "groups_count": len(user.groups),
                }
            )
        logger.info(f"Retrieved {len(users)} users")
        return result

    @classmethod
    def get_by_user_id(cls, user_id: str, session) -> Optional[dict]:
        """Return user by user_id as dict with groups list, or None."""
        user = session.query(cls).filter(cls.user_id == user_id).first()
        if not user:
            return None
        groups = []
        for group in user.groups:
            groups.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                }
            )
        return {
            "id": user.id,
            "user_id": user.user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "groups": groups,
            "groups_count": len(groups),
        }
