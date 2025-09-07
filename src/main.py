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
    format="%(asctime)s - %(name)s - %(levelname)s - %(thread)d - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


mcp_server = FastMCP(name="users-groups-mcp")


@mcp_server.custom_route("/get_username_by_user_id", methods=["POST"])
async def http_get_username_by_user_id(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    logger.info(f"Getting username for user ID: {user_id}")
    with SessionLocal() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        logger.info(f"User: {user}")
        return JSONResponse({"username": user.username if user else None})


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


@mcp_server.tool(tags=["admin"])
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


@mcp_server.custom_route("/create_student_account", methods=["POST"])
async def http_create_student_account(request: Request):
    data = await request.json()
    student_user_id = data.get("user_id")

    response = await generate_username()
    logger.info(f"Response from generate_username: {response}")

    body = json.loads(response.body.decode("utf-8"))

    if response.status_code != 200:
        logger.error(f"Error creating new student account: {body.get('error')}")
        return JSONResponse(
            {"success": False, "error": body.get("error")}, status_code=400
        )

    username = body.get("username")

    with SessionLocal() as session:
        # a teacher activates the student account adding into the group
        User.create(
            username=username,
            is_activated=False,
            user_id=student_user_id,
            session=session,
        )
        return JSONResponse({"success": True, "username": username}, status_code=200)


@mcp_server.custom_route("/generate_username", methods=["GET"])
async def generate_username() -> JSONResponse:
    """Generate a friendly username and create a user record in the database.
    It's used to create a teacher and a student accounts.
    """
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


@mcp_server.tool(tags=["teacher"])
async def call_agent_for_a_student(
    student_username: Annotated[str, "Username of the student"],
    prompt: Annotated[str, "Message to the student"],
) -> str:
    """Call an LLM agent behalf of a student to do a task.
    It's helpful when a teacher wants to do a task for a student.
    It will use student's knowledge and context to do the task.
    """
    logger.info(f"Calling agent for student: {student_username}, message: {prompt}")

    with SessionLocal() as session:
        student = session.query(User).filter(User.username == student_username).first()
        if not student:
            return f"Student with username {student_username} not found"
        student_user_id = student.user_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{AGENT_ENDPOINT}/message"
        payload = {
            "message": prompt,
            "user_id": student_user_id,
            "role": "student",
        }
        response = await client.post(url, json=payload)

        if response.status_code != 200:
            return f"Error calling agent: {response.text}"

        data = response.json()
        message = json.loads(data.get("message", ""))
        return message.get("message")


@mcp_server.tool(tags=["admin", "debug"])
async def create_user(
    user_id: Annotated[str, "User ID of the user to create"],
    username: Annotated[str, "Username of the user to create"],
    role: Annotated[str, "Role of the user to create"],
    is_activated: Annotated[bool, "Whether the user is activated"],
) -> str:
    """Create a new user with the given username and register in registry MCP."""
    logger.info(
        f"Creating user: {username}, user_id: {user_id}, is_activated: {is_activated}"
    )
    with SessionLocal() as session:
        User.create(
            username=username,
            session=session,
            user_id=user_id,
            is_activated=is_activated,
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MCP_REGISTRY_ENDPOINT}/register_user",
            json={"user_id": user_id, "role_name": role},
        )
        if response.status_code != 200:
            return f"Error registering user: {response.text}"
        return f"User {username} created successfully"


@mcp_server.tool(tags=["teacher"])
async def create_group(
    name: Annotated[str, "Name of the group"],
    description: Annotated[Optional[str], "Description of the group"],
    teacher_user_id: Annotated[str, "User ID of the teacher owner of the group"],
    students_usernames: Annotated[
        Optional[List[str]], "List of student usernames to add to the group"
    ] = None,
) -> str:
    """Create a new group with optional users and description."""
    logger.info(
        f"Creating group: {name}, description: {description}, owner: {teacher_user_id}"
    )
    if students_usernames:
        logger.info(f"Students usernames: {students_usernames}")
    else:
        logger.info("No students usernames add to the group")

    try:
        with SessionLocal() as session:
            group = Group.create(
                name=name,
                usernames=students_usernames,
                description=description,
                session=session,
                owner_user_id=teacher_user_id,
            )
            result = f"Group '{name}' created successfully with ID: {group['id']}"
            if students_usernames:
                result += f"\nAdded {group['added_users_count']} users to the group"
                if len(students_usernames) > group["added_users_count"]:
                    result += "\nWarning: Not all students were added to the group"
            return result
    except ValueError as e:
        return f"Error creating group: {str(e)}"
    except Exception as e:
        logger.error(f"Error creating group: {e}")
        return f"Database error: {str(e)}"


async def check_teacher_owner_of_group(group_id: int, teacher_user_id: str) -> bool:
    with SessionLocal() as session:
        group = session.query(Group).filter(Group.id == group_id).first()
        if not group:
            logger.error(f"Group with ID {group_id} not found")
            return False
        if group.owner.user_id != teacher_user_id:
            logger.error(f"Group with ID {group_id} is not owned by {teacher_user_id}")
            return False
        return True


@mcp_server.tool(tags=["teacher"])
async def delete_group(
    group_id: Annotated[int, "ID of the group to delete"],
    teacher_user_id: Annotated[str, "User ID of the teacher owner of the group"],
) -> str:
    """Delete a group by its ID."""
    logger.info(f"Deleting group: {group_id} owned by {teacher_user_id}")
    try:
        with SessionLocal() as session:
            is_allowed = await check_teacher_owner_of_group(group_id, teacher_user_id)
            if not is_allowed:
                return f"Group with ID {group_id} is not owned by {teacher_user_id}"

            success = Group.delete_by_id(group_id, session)
        if success:
            return f"Group with ID {group_id} deleted successfully"
        else:
            return f"Group with ID {group_id} not found"
    except Exception as e:
        logger.error(f"Error deleting group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(tags=["teacher"])
async def add_user_to_group(
    teacher_user_id: Annotated[str, "User ID of the teacher owner of the group"],
    group_id: Annotated[int, "ID of the group"],
    username: Annotated[str, "Username of the user to add"],
) -> str:
    """Add a user to a group."""
    logger.info(f"Adding user {username} to group {group_id}")
    try:
        with SessionLocal() as session:
            # check that the teacher can do this action
            is_allowed = await check_teacher_owner_of_group(group_id, teacher_user_id)
            if not is_allowed:
                return f"Group with ID {group_id} is not owned by {teacher_user_id}"

            user = session.query(User).filter(User.username == username).first()
            if not user:
                return f"User with username {username} not found"
            Group.add_user(group_id, user.user_id, session)
            session.query(User).filter(User.username == username).update(
                {"is_activated": True}
            )

            return f"User {username} added to group {group_id} successfully."
    except Exception as e:
        logger.error(f"Error adding user to group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(tags=["teacher"])
async def get_students_in_group(
    teacher_user_id: Annotated[str, "User ID of the teacher owner of the group"],
    group_id: Annotated[int, "ID of the group to retrieve"],
) -> str:
    """Get a list of all students in a group.
    It returns only activated students.
    """
    logger.info(f"Getting all students in group {group_id}")
    with SessionLocal() as session:
        is_allowed = await check_teacher_owner_of_group(group_id, teacher_user_id)
        if not is_allowed:
            return f"Group with ID {group_id} is not owned by {teacher_user_id}"

        students = (
            session.query(User)
            .join(User.groups)
            .filter(Group.id == group_id)
            .filter(User.is_activated)
            .all()
        )
        if not students:
            return "No students found in the group"

        result = [
            {"username": student.username, "user_id": student.user_id}
            for student in students
            for student in students
        ]

        return str(result)


@mcp_server.tool(tags=["teacher"])
async def remove_user_from_group(
    teacher_user_id: Annotated[str, "User ID of the teacher owner of the group"],
    group_id: Annotated[int, "ID of the group"],
    username: Annotated[str, "Username of the user to remove"],
) -> str:
    """Remove a user from a group."""
    logger.info(
        f"Removing user {username} from group {group_id} owned by {teacher_user_id}"
    )
    try:
        with SessionLocal() as session:
            is_allowed = await check_teacher_owner_of_group(group_id, teacher_user_id)
            if not is_allowed:
                return f"Group with ID {group_id} is not owned by {teacher_user_id}"

            success = Group.remove_user(group_id, username, session, teacher_user_id)
        if success:
            user = session.query(User).filter(User.username == username).first()
            # if there is no more groups for the user, deactivate the user
            if len(user.groups) == 0:
                session.query(User).filter(User.username == username).update(
                    {"is_activated": False}
                )
                logger.info(f"User {username} deactivated successfully")

            return f"User {username} removed from group {group_id} successfully"
        else:
            return f"Failed to remove user {username} from group {group_id}. Check if both exist and user is in the group."
    except Exception as e:
        logger.error(f"Error removing user from group: {e}")
        return f"Database error: {str(e)}"


@mcp_server.tool(tags=["teacher"])
async def get_available_groups(
    teacher_user_id: Annotated[str, "User ID of the teacher owner of the group"],
) -> str:
    """Get a list of all groups in the database."""
    logger.info(f"Getting all groups owned by {teacher_user_id}")
    try:
        with SessionLocal() as session:
            groups = Group.get_groups(session, teacher_user_id)
        if not groups:
            return "No groups found in the database"

        result = [
            {
                "id": group["id"],
                "name": group["name"],
                "description": group["description"],
                "users_count": group["users_count"],
            }
            for group in groups
        ]

        result = "Groups in the database owned by {teacher_user_id}:\n" + str(result)

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
