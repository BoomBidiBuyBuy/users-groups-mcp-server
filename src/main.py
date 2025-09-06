import logging
import json
from typing import Annotated, List, Optional

from user_group_db.models import Group, User
from storage import SessionLocal, engine, init_db

from envs import MCP_HOST, MCP_PORT, MCP_REGISTRY_ENDPOINT, AGENT_ENDPOINT
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
import httpx


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


mcp_server = FastMCP(name="users-groups-mcp")


@mcp_server.custom_route("/check_username_exists", methods=["POST"])
async def http_check_username_exists(request: Request):
    data = await request.json()
    username = data.get("username")
    logger.info(f"Checking username exists: {username}")
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        logger.info(f"User: {user}")
        return JSONResponse({"exists": user is not None})


@mcp_server.custom_route("/get_user_id", methods=["POST"])
async def http_get_user_id(request: Request):
    data = await request.json()
    username = data.get("username")
    logger.info(f"Getting user ID for username: {username}")
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        logger.info(f"User: {user}")
        return JSONResponse({"user_id": user.user_id})


@mcp_server.custom_route("/set_user_id_for_username", methods=["POST"])
async def http_set_user_id_for_username(request: Request):
    data = await request.json()
    username = data.get("username")
    user_id = data.get("user_id")
    logger.info(f"Setting user ID for username: {username} to {user_id}")
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        user.user_id = user_id
        session.commit()
        logger.info(f"User: {user}")
        return JSONResponse({"success": True})


@mcp_server.custom_route("/check_user_id_activated", methods=["POST"])
async def http_check_user_id_activated(request: Request):
    logger.info("Checking user ID activated")
    data = await request.json()
    user_id = data.get("user_id")
    logger.info(f"Checking user ID activated: {user_id}")
    with SessionLocal() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        logger.info(f"User: {user}")
        return JSONResponse({"activated": user.is_activated if user else False})


@mcp_server.tool
async def create_new_teacher_account() -> str:
    """Create a new teacher activated account."""
    logger.info("Creating new teacher account")

    response = await generate_username()
    logger.info(f"Response from generate_username: {response}")

    body = json.loads(response.body.decode("utf-8"))

    if response.status_code != 200:
        logger.error(f"Error creating new teacher account: {body.get('error')}")
        return body.get("error")

    username = body.get("username")

    with SessionLocal() as session:
        User.create(username=username, is_activated=True, session=session)
        return f"Teacher account created successfully with username: {username}"


@mcp_server.custom_route("/generate_username", methods=["GET"])
async def generate_username() -> JSONResponse:
    """Generate a friendly username and create a user record in the database."""
    logger.info("Generating username")

    async with httpx.AsyncClient(timeout=30.0) as client:
        limit_attempts = 3
        attempts = 0
        while attempts < limit_attempts:
            url = f"{AGENT_ENDPOINT}/message"
            payload = {
                "message": "Generate a kids friendly funny sounding username contains of some animal and adjective",
                "structured_output": True,
                "user_id": "service",
                "role": "service",
                "json_schema": {
                    "name": "username_record",  # required by OpenAI structured outputs
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "username": {"type": "string"},
                        },
                        "required": ["username"],
                    },
                },
            }
            response = await client.post(url, json=payload)
            logger.info(f"Response: {response.json()}")

            if response.status_code != 200:
                logger.error(f"Error generating username: {response.text}")
                return JSONResponse(
                    {"success": False, "error": "Error generating username"},
                    status_code=400,
                )

            data = response.json()
            message = json.loads(data.get("message", ""))
            username = message.get("username")

            if not username:
                logger.error("Username is empty")
                return JSONResponse(
                    {"success": False, "error": "Username is empty"},
                    status_code=400,
                )

            with SessionLocal() as session:
                # check if username already exists
                existing_user = (
                    session.query(User).filter(User.username == username).first()
                )
                if existing_user:
                    logger.info(f"Username {username} already exists")
                    attempts += 1
                    continue

            break

        if attempts == limit_attempts:
            return JSONResponse(
                {
                    "success": False,
                    "error": "Username already exists",
                },
                status_code=400,
            )

        return JSONResponse(
            {
                "username": username,
                "success": True,
            },
            status_code=200,
        )


@mcp_server.tool(tags=["admin"])
async def create_user(
    username: Annotated[str, "Username of the user to create"],
) -> str:
    """Create a new user with the given username and register in registry."""
    logger.info(f"Creating user: {username}")
    with SessionLocal() as session:
        User.create(username=username, session=session)
        return f"User {username} created successfully"


@mcp_server.tool
async def create_group(
    name: Annotated[str, "Name of the group"],
    user_ids: Annotated[
        Optional[List[str]], "List of user IDs to add to the group"
    ] = None,
    description: Annotated[Optional[str], "Description of the group"] = None,
) -> str:
    """Create a new group with optional users and description."""
    logger.info(
        f"Creating group: {name}, user_ids: {user_ids}, description: {description}"
    )

    try:
        with SessionLocal() as session:
            group = Group.create(
                name=name, user_ids=user_ids, description=description, session=session
            )
            result = f"Group '{name}' created successfully with ID: {group['id']}"
            if user_ids:
                result += f"\nAdded {len(user_ids)} users to the group"
            return result
    except ValueError as e:
        return f"Error creating group: {str(e)}"
    except Exception as e:
        logger.error(f"Error creating group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool
async def delete_group(group_id: Annotated[int, "ID of the group to delete"]) -> str:
    """Delete a group by its ID."""
    logger.info(f"Deleting group: {group_id}")
    try:
        with SessionLocal() as session:
            success = Group.delete_by_id(group_id, session)
        if success:
            return f"Group with ID {group_id} deleted successfully"
        else:
            return f"Group with ID {group_id} not found"
    except Exception as e:
        logger.error(f"Error deleting group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool
async def add_user_to_group(
    group_id: Annotated[int, "ID of the group"],
    user_id: Annotated[str, "User ID of the user to add"],
) -> str:
    """Add a user to a group."""
    logger.info(f"Adding user {user_id} to group {group_id}")
    try:
        with SessionLocal() as session:
            User.create(user_id=user_id, session=session)
            Group.add_user(group_id, user_id, session)

            response = httpx.post(
                f"{MCP_REGISTRY_ENDPOINT}/register_user",
                json={"user_id": user_id, "role_name": "student"},
            )
            if response.status_code != 200:
                session.rollback()
                return f"Error registering user: {response.text}"

            return f"User {user_id} added to group {group_id} successfully."
    except Exception as e:
        logger.error(f"Error adding user to group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool
async def remove_user_from_group(
    group_id: Annotated[int, "ID of the group"],
    user_id: Annotated[str, "User ID of the user to remove"],
) -> str:
    """Remove a user from a group."""
    logger.info(f"Removing user {user_id} from group {group_id}")
    try:
        with SessionLocal() as session:
            success = Group.remove_user(group_id, user_id, session)
        if success:
            return f"User {user_id} removed from group {group_id} successfully"
        else:
            return f"Failed to remove user {user_id} from group {group_id}. Check if both exist and user is in the group."
    except Exception as e:
        logger.error(f"Error removing user from group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(enabled=False)
async def get_all_groups() -> str:
    """Get a list of all groups in the database."""
    logger.info("Getting all groups")
    try:
        with SessionLocal() as session:
            groups = Group.get_all(session)
        if not groups:
            return "No groups found in the database"

        result = "Groups in the database:\n"
        for group in groups:
            result += f"- ID: {group['id']}, Name: '{group['name']}'"
            if group["description"]:
                result += f", Description: '{group['description']}'"
            result += f", Users: {group['users_count']}\n"

        return result
    except Exception as e:
        logger.error(f"Error getting groups: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(enabled=False)
async def get_group_by_id(
    group_id: Annotated[int, "ID of the group to retrieve"],
) -> str:
    """Get detailed information about a specific group."""
    logger.info(f"Getting group by ID: {group_id}")
    try:
        with SessionLocal() as session:
            group = Group.get_by_id(group_id, session)
        if not group:
            return f"Group with ID {group_id} not found"

        result = "Group Details:\n"
        result += f"- ID: {group['id']}\n"
        result += f"- Name: '{group['name']}'\n"
        if group["description"]:
            result += f"- Description: '{group['description']}'\n"
        result += f"- Created: {group['created_at']}\n"
        result += f"- Users ({group['users_count']}):\n"

        for user in group["users"]:
            result += f"  * {user['user_id']}"
            if user["username"]:
                result += f" (@{user['username']})"
            if user["first_name"] or user["last_name"]:
                result += (
                    f" - {user['first_name'] or ''} {user['last_name'] or ''}".strip()
                )
            result += "\n"

        return result
    except Exception as e:
        logger.error(f"Error getting group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(tags=["admin"])
async def activate_user(
    username: Annotated[str, "Username of the user to activate"],
) -> str:
    """Activate a user by username (sets is_activated=True)."""
    logger.info(f"Activating user: {username}")
    try:
        with SessionLocal() as session:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                return f"User with username '{username}' not found"
            if user.is_activated:
                return f"User '{username}' is already activated"
            user.is_activated = True
            session.commit()
            return f"User '{username}' activated successfully"
    except Exception as e:
        logger.error(f"Error activating user: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(tags=["admin"])
async def deactivate_user(
    username: Annotated[str, "Username of the user to deactivate"],
) -> str:
    """Deactivate a user by username (sets is_activated=False)."""
    logger.info(f"Deactivating user: {username}")
    try:
        with SessionLocal() as session:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                return f"User with username '{username}' not found"
            if not user.is_activated:
                return f"User '{username}' is already deactivated"
            user.is_activated = False
            session.commit()
            return f"User '{username}' deactivated successfully"
    except Exception as e:
        logger.error(f"Error deactivating user: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(enabled=False)
async def get_group_by_name(
    name: Annotated[str, "Name of the group to retrieve"],
) -> str:
    """Get detailed information about a group by its name."""
    logger.info(f"Getting group by name: {name}")
    try:
        with SessionLocal() as session:
            group = Group.get_by_name(name, session)
        if not group:
            return f"Group with name '{name}' not found"

        result = "Group Details:\n"
        result += f"- ID: {group['id']}\n"
        result += f"- Name: '{group['name']}'\n"
        if group["description"]:
            result += f"- Description: '{group['description']}'\n"
        result += f"- Created: {group['created_at']}\n"
        result += f"- Users ({group['users_count']}):\n"

        for user in group["users"]:
            result += f"  * {user['user_id']}"
            if user["username"]:
                result += f" (@{user['username']})"
            if user["first_name"] or user["last_name"]:
                result += (
                    f" - {user['first_name'] or ''} {user['last_name'] or ''}".strip()
                )
            result += "\n"

        return result
    except Exception as e:
        logger.error(f"Error getting group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(tags=["admin"])
async def list_users() -> str:
    """Get a list of all users in the database."""
    logger.info("Getting all users")
    try:
        with SessionLocal() as session:
            users = User.get_all(session)

            logger.info(f"Number of users: {len(users)}")

            registry_users = []
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{MCP_REGISTRY_ENDPOINT}/list_users",
                )
                if response.status_code != 200:
                    return f"Error listing users: {response.text}"
                response_users = response.json()

                registry_users = {
                    record["user"]["user_id"]: {"role": record["user"]["role"]}
                    for record in response_users.get("users", dict())
                }

                logger.info(f"Number of registry users: {len(registry_users)}")

            result = [
                {
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "activated": user.get("is_activated", False),
                    "role": registry_users.get(user["user_id"], {}).get(
                        "role", "(no role)"
                    ),
                }
                for user in users
            ]

            return str(result)
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(enabled=False)
async def get_user_by_user_id(
    user_id: Annotated[str, "User ID of the user to retrieve"],
) -> str:
    """Get detailed information about a user by their user_id."""
    logger.info(f"Getting user by user_id: {user_id}")
    try:
        with SessionLocal() as session:
            user = User.get_by_user_id(user_id, session)
        if not user:
            return f"User with ID {user_id} not found"

        result = "User Details:\n"
        result += f"- ID: {user['id']}\n"
        result += f"- User ID: {user['user_id']}\n"
        if user["username"]:
            result += f"- Username: @{user['username']}\n"
        if user["first_name"]:
            result += f"- First Name: {user['first_name']}\n"
        if user["last_name"]:
            result += f"- Last Name: {user['last_name']}\n"
        result += f"- Created: {user['created_at']}\n"
        result += f"- Groups ({user['groups_count']}):\n"

        for group in user["groups"]:
            result += f"  * {group['name']} (ID: {group['id']})\n"

        return result
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return f"Database error: {str(e)}"

    except ValueError:
        return JSONResponse({"error": "Invalid user_id format"}, status_code=400)
    except Exception as e:
        logger.error(f"Error in HTTP get_user: {e}")
        return JSONResponse(
            {"error": f"Internal server error: {str(e)}"}, status_code=500
        )


@mcp_server.custom_route("/health", methods=["GET"])
async def http_health_check(request):
    return JSONResponse({"status": "healthy", "service": "users-groups-mcp-server"})


def main():
    init_db(engine)
    mcp_server.run(
        transport="http",
        host=MCP_HOST,
        port=MCP_PORT,
    )


if __name__ == "__main__":
    main()
