import os
import re
import psycopg2
import psycopg2.extras
import telegram
from telegram.ext import Updater, CommandHandler, PrefixHandler, MessageHandler, Filters
from typing import NamedTuple, Callable

PREFIX = os.getenv("PREFIX", ";")
BATCH = int(os.getenv("BATCH", 7))
MAX_ROLES = int(os.getenv("MAX_ROLES", 10))
IGNORE_STATUS = (telegram.ChatMember.LEFT, telegram.ChatMember.KICKED)
ROLE_PATTERN = re.compile(r"^(?=.{6,33}$)@([a-zA-Z0-9_]+)$")

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise Exception("TOKEN not found")

DB_URL = os.environ['DATABASE_URL']
DB_CONN = psycopg2.connect(DB_URL, sslmode='require', cursor_factory=psycopg2.extras.NamedTupleCursor)

REGISTERED = os.getenv("REGISTERED")
if REGISTERED is None:
    print("WARNING: There is no registered groups")
    REGISTERED = set()
else:
    REGISTERED = set(map(int, REGISTERED.split(';')))


class Command(NamedTuple):
    command: str
    function: Callable
    usage: str = ""
    help: str = ""
    hidden: bool = False


CommandList = []


def init_db():
    cur = DB_CONN.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS roletable ("
                "id SERIAL PRIMARY KEY,"
                "user_id BIGINT NOT NULL,"
                "group_id BIGINT NOT NULL,"
                "role TEXT NOT NULL"
                ");")
    DB_CONN.commit()


def prefix_command(command, **kwargs):
    def _decorator(func):
        global CommandList

        def wrapper(update, context):
            return func(update, context)

        CommandList.append(Command(command=command, function=wrapper, **kwargs))
        return wrapper
    return _decorator


def only_registered_group(func):
    def wrapper(update, context):
        chat = update.effective_chat
        if chat is not None and chat.type in ("group", "supergroup") and chat.id in REGISTERED:
            return func(update, context)
    return wrapper


def find_role(message):
    match = ROLE_PATTERN.match(message)
    if not match:
        return None
    return match.group(1)


def get_command_args(message):
    return message.split()[1:]


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
    update.message.reply_markdown(message)


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
        update.message.reply_markdown("Bad formatted request")
        return
    role = find_role(args[0])
    if not role:
        update.message.reply_markdown("Bad formatted request")
        return

    cur = DB_CONN.cursor()
    cur.execute("SELECT * FROM roletable WHERE user_id=%s AND group_id=%s AND role=%s", (user_id, chat_id, role))
    result = cur.fetchall()
    if result:
        update.message.reply_markdown(f"Role @{role} exists for you")
        return

    cur.execute("SELECT * FROM roletable WHERE user_id=%s", (user_id,))
    result = cur.fetchall()
    if len(result) >= MAX_ROLES:
        update.message.reply_markdown(f"You have reached the maximum number of roles :(")
        return

    cur.execute("INSERT INTO roletable(user_id, group_id, role) "
                "VALUES (%s, %s, %s)", (user_id, chat_id, role))
    DB_CONN.commit()
    update.message.reply_markdown(f"Role @{role} added")


@prefix_command(command="del", usage="<role>", help="Delete role")
@only_registered_group
def delete_role_command(update, context):
    chat_id = update.message.chat_id
    user_id = update.effective_user.id

    args = get_command_args(update.message.text)
    if len(args) != 1:
        update.message.reply_markdown("Bad formatted request")
        return
    role = find_role(args[0])
    if not role:
        update.message.reply_markdown("Bad formatted request")
        return

    cur = DB_CONN.cursor()
    cur.execute("DELETE FROM roletable WHERE user_id=%s AND group_id=%s AND role=%s", (user_id, chat_id, role))
    DB_CONN.commit()
    update.message.reply_markdown(f"Role @{role} deleted")


@prefix_command(command="get", usage="<role>", help="Get role members")
@only_registered_group
def get_role_info_command(update, context):
    chat_id = update.message.chat_id

    args = get_command_args(update.message.text)
    if len(args) != 1:
        update.message.reply_markdown("Bad formatted request")
        return
    role = find_role(args[0])
    if not role:
        update.message.reply_markdown("Bad formatted request")
        return

    cur = DB_CONN.cursor()
    cur.execute("SELECT * FROM roletable WHERE group_id=%s AND role=%s", (chat_id, role))
    result = cur.fetchall()
    chat_members = [context.bot.get_chat_member(chat_id, record.user_id) for record in result]
    available = [member for member in chat_members if member.status not in IGNORE_STATUS]
    if not available:
        update.message.reply_markdown("No user with this role")
    else:
        message = "\n".join(member.user.full_name for member in available)
        update.message.reply_markdown(message)


@prefix_command(command="me", help="Get your roles")
@only_registered_group
def get_user_info_command(update, context):
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    cur = DB_CONN.cursor()
    cur.execute("SELECT (role) FROM roletable WHERE group_id=%s AND user_id=%s", (chat_id, user_id))
    result = cur.fetchall()
    roles = [f"@{item[0]}" for item in result]
    update.message.reply_text("Your roles: \n" + " ".join(roles))


@prefix_command(command="all", help="Get group roles")
@only_registered_group
def get_group_info_command(update, context):
    chat_id = update.message.chat_id
    cur = DB_CONN.cursor()
    cur.execute("SELECT * FROM roletable WHERE group_id=%s", (chat_id,))
    result = cur.fetchall()
    roles = {}
    for record in result:
        roles.setdefault(record.role,  []).append(record.user_id)
    message = ["Tree of roles: "]
    for role in roles.keys():
        chat_members = [context.bot.get_chat_member(chat_id, user_id) for user_id in roles[role]]
        available = [member for member in chat_members if member.status not in IGNORE_STATUS]
        if not available:
            continue
        message.append(f"@{role}: ")
        for member in available:
            message.append(f"├─{member.user.full_name}")
        message[-1] = "└" + message[-1][1:]
    update.message.reply_markdown("\n".join(message))


@only_registered_group
def check_mention(update, context):
    cur = DB_CONN.cursor()
    chat_id = update.message.chat_id
    if update.message.text is not None:
        text = update.message.text
    elif update.message.caption is not None:
        text = update.message.caption
    else:
        return
    users = set()
    roles = [find_role(word) for word in text.split() if find_role(word)]
    for role in roles:
        cur.execute("SELECT * FROM roletable WHERE group_id=%s AND role=%s", (chat_id, role))
        result = cur.fetchall()
        users.update(record.user_id for record in result)

    users = list(users)
    chat_members = [context.bot.get_chat_member(chat_id, user_id) for user_id in users]
    available = [member for member in chat_members if member.status not in IGNORE_STATUS]
    if not available:
        return
    for i in range(0, len(available), BATCH):
        current = available[i:i + BATCH]
        message = []
        for member in current:
            message.append(f"[{member.user.first_name}](tg://user?id={member.user.id})")
        update.message.reply_markdown(", ".join(message))


def main():
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("about", about_command))

    for obj in CommandList:
        dispatcher.add_handler(PrefixHandler(PREFIX, obj.command, obj.function))
        print(f"Command {obj.command} added {obj.function}")

    dispatcher.add_handler(MessageHandler(Filters.all, check_mention))
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
