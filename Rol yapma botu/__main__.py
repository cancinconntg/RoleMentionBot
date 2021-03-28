import os
import re
import logging
import telegram
from telegram.ext import Updater, CommandHandler, PrefixHandler, MessageHandler, Filters
from typing import NamedTuple, Callable
from dotenv import load_dotenv
from .database import Database


load_dotenv()
PREFIX = os.getenv("PREFIX", ";")
BATCH = int(os.getenv("BATCH", 7))
MAX_ROLES = int(os.getenv("MAX_ROLES", 10))
ROLE_PATTERN = re.compile(r"(\s|^)@([a-zA-Z0-9_]{5,32})")
IGNORE_STATUS = (telegram.ChatMember.LEFT,
                 telegram.ChatMember.KICKED,
                 telegram.ChatMember.RESTRICTED)
ADMIN_STATUS = (telegram.ChatMember.ADMINISTRATOR,
                telegram.ChatMember.CREATOR)

TOKEN = ("1777609083:AAHsGVYqkCRBui1xfWIy7lbjsau4E7advXI")
if not TOKEN:
    raise Exception("TOKEN not found")

DB_FILE = os.getenv("DBFILE", "db/role.db")
DB = Database(DB_FILE)

REGISTERED = os.getenv("REGISTERED")
if REGISTERED is None:
    raise Exception("No registered groups")
REGISTERED = set(map(int, REGISTERED.split(':')))


class Command(NamedTuple):
    command: str
    function: Callable
    usage: str = ""
    help: str = ""
    hidden: bool = False


CommandList = []


def prefix_command(command, **kwargs):
    def _decorator(func):
        global CommandList

        def wrapper(update, context):
            return func(update, context)

        CommandList.append(Command(command=command, function=wrapper, **kwargs))
        return wrapper
    return _decorator


def admin_command(func):
    def wrapper(update, context):
        chat = update.effective_chat
        user = update.effective_user
        chat_member = chat.get_member(user.id)
        if chat_member.status in ADMIN_STATUS:
            return func(update, context)
        update.message.reply_text("Only admins can use this command!")

    return wrapper


def only_registered_group(func):
    def wrapper(update, context):
        chat = update.effective_chat
        if chat is not None and chat.type in ("group", "supergroup") and chat.id in REGISTERED:
            return func(update, context)
    return wrapper


def find_role(message):
    match = ROLE_PATTERN.fullmatch(message)
    if not match:
        return None
    return match.group(2)


def get_command_args(message):
    return message.split()[1:]


def get_available(bot, group_id, users: list):
    users = list(filter(lambda user_id: user_id != -1, users))
    chat_members = [bot.get_chat_member(group_id, user_id) for user_id in users]
    available = [member for member in chat_members
                 if member.status not in IGNORE_STATUS or member.is_member]
    return available


@prefix_command(command="start", hidden=True)
def start_command(update, context):
    chat = update.effective_chat
    if chat is None or chat.type not in ("group", "supergroup"):
        update.message.reply_text(f"Hi!")
        return
    message = f"Hi!\nThe id for this group is {chat.id}, "
    if chat.id in REGISTERED:
        message += "and it is registered :)"
    else:
        message += "and it is not registered yet. So most features may not available :("
    update.message.reply_text(message)


@prefix_command(command="help", hidden=True)
def help_command(update, context):
    message = ["These are my commands, and they work only in registered groups:"]
    for obj in CommandList:
        if obj.hidden:
            continue
        cmd = f"{PREFIX}{obj.command} {obj.usage}"
        cmd += " " * (20 - len(cmd))
        message.append(f"`{cmd}{obj.help}`")
    update.message.reply_markdown("\n".join(message))


@prefix_command(command="about", hidden=True)
def about_command(update, context):
    update.message.reply_text("This telegram bot adds a feature to groups and super-groups similar to mention a role "
                              "in Discord. Members can join some roles and get notified when the role mentioned.")


@prefix_command(command="add", usage="<role>", help="Add role")
@only_registered_group
def add_role_command(update, context):
    chat_id = update.message.chat_id
    user_id = update.effective_user.id

    args = get_command_args(update.message.text)
    if len(args) != 1:
        update.message.reply_text("Bad formatted request")
        return
    role = find_role(args[0])
    if not role:
        update.message.reply_text("Bad formatted request")
        return

    if not DB.exist(chat_id, role):
        update.message.reply_text(f"Role @{role} hasn't been created")
        return
    if DB.select(user_id=user_id, group_id=chat_id, role=role):
        update.message.reply_text(f"Role @{role} exists for you")
        return
    result = DB.select(user_id=user_id)
    if len(result) >= MAX_ROLES:
        update.message.reply_text(f"You have reached the maximum number of roles :(")
        return

    DB.insert(user_id, chat_id, role)
    update.message.reply_text(f"Role @{role} added to you")


@prefix_command(command="del", usage="<role>", help="Delete role")
@only_registered_group
def delete_role_command(update, context):
    chat_id = update.message.chat_id
    user_id = update.effective_user.id

    args = get_command_args(update.message.text)
    if len(args) != 1:
        update.message.reply_text("Bad formatted request")
        return
    role = find_role(args[0])
    if not role:
        update.message.reply_text("Bad formatted request")
        return

    result = DB.delete(user_id=user_id, group_id=chat_id, role=role)
    if result:
        update.message.reply_text(f"Role @{role} deleted from you")
    else:
        update.message.reply_text(f"You didn't have @{role}.")


@prefix_command(command="get", usage="<role>", help="Get role members")
@only_registered_group
def get_role_info_command(update, context):
    chat_id = update.message.chat_id

    args = get_command_args(update.message.text)
    if len(args) != 1:
        update.message.reply_text("Bad formatted request")
        return
    role = find_role(args[0])
    if not role:
        update.message.reply_text("Bad formatted request")
        return

    result = DB.select(group_id=chat_id, role=role)
    available = get_available(context.bot, chat_id, [record.user_id for record in result])
    if not available:
        update.message.reply_text("No user with this role")
    else:
        message = [f"({len(available)}) @{role}"] + [f"├─{member.user.full_name}" for member in available]
        message[-1] = "└" + message[-1][1:]
        update.message.reply_text("\n".join(message))


@prefix_command(command="me", help="Get your roles")
@only_registered_group
def get_user_info_command(update, context):
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    result = DB.select(group_id=chat_id, user_id=user_id)
    roles = [f"@{record.role}" for record in result]
    update.message.reply_text("Your roles: \n" + " ".join(roles))


@prefix_command(command="all", help="Get group roles (admin only)")
@only_registered_group
@admin_command
def get_group_info_command(update, context):
    chat_id = update.message.chat_id
    result = DB.select(group_id=chat_id)
    roles = {}
    for record in result:
        roles.setdefault(record.role,  []).append(record.user_id)
    roles = sorted(roles.items(), key=lambda item: (-len(item[1]), item[0]))
    message = []
    for role, users in roles:
        available = get_available(context.bot, chat_id, users)
        message.append(f"({len(available)}) @{role}: ")
        message += [f"├─{member.user.full_name}" for member in available]
        if available:
            message[-1] = "└" + message[-1][1:]
    if not message:
        update.message.reply_text("No entry found for this group")
    else:
        update.message.reply_text("\n".join(message))


@prefix_command(command="create", usage="<role>", help="Create group role (admin only)")
@only_registered_group
@admin_command
def create_role_command(update, context):
    chat_id = update.message.chat_id
    args = get_command_args(update.message.text)
    if len(args) != 1:
        update.message.reply_text("Bad formatted request")
        return
    role = find_role(args[0])
    if not role:
        update.message.reply_text("Bad formatted request")
        return

    if DB.exist(chat_id, role):
        update.message.reply_text(f"Role @{role} exists in group")
        return
    DB.insert(-1, chat_id, role)
    update.message.reply_text(f"Role @{role} created. Users can join via ;add command")


@prefix_command(command="purge", usage="<role>", help="Purge group role (admin only)")
@only_registered_group
@admin_command
def purge_role_command(update, context):
    chat_id = update.message.chat_id
    args = get_command_args(update.message.text)
    if len(args) != 1:
        update.message.reply_text("Bad formatted request")
        return
    role = find_role(args[0])
    if not role:
        update.message.reply_text("Bad formatted request")
        return

    if not DB.exist(chat_id, role):
        update.message.reply_text(f"Role @{role} not found")
        return
    DB.delete(group_id=chat_id, role=role)
    update.message.reply_text(f"Role @{role} purged from group")


@only_registered_group
def check_mention(update, context):
    message = update.message if update.message else update.edited_message
    chat_id = message.chat_id
    text = message.text if message.text else message.caption
    if text is None:
        return
    users = set()
    roles = [match[1] for match in ROLE_PATTERN.findall(text)]
    for role in roles:
        result = DB.select(group_id=chat_id, role=role)
        users.update(record.user_id for record in result)

    users = list(users)
    available = get_available(context.bot, chat_id, users)
    if not available:
        return
    for i in range(0, len(available), BATCH):
        current = available[i:i + BATCH]
        msg = [f"[{member.user.first_name}](tg://user?id={member.user.id})" for member in current]
        message.reply_markdown(", ".join(msg))


def main():
    logging.basicConfig(level=logging.INFO,
                        format="[%(levelname)s] %(message)s")
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("about", about_command))

    for obj in CommandList:
        dispatcher.add_handler(PrefixHandler(PREFIX, obj.command, obj.function))
        logging.info(f"Command {obj.command} added {obj.function}")

    dispatcher.add_handler(MessageHandler(Filters.all, check_mention))
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
