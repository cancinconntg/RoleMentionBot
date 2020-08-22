import os
import psycopg2
import psycopg2.extras
import telegram
from telegram.ext import Updater, CommandHandler, PrefixHandler, MessageHandler, Filters
from collections import namedtuple

PREFIX = ";"
BATCH = 5

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise Exception("TOKEN not found")

DB_URL = os.environ['DATABASE_URL']
DB_CONN = psycopg2.connect(DB_URL, sslmode='require', cursor_factory=psycopg2.extras.NamedTupleCursor)

Command = namedtuple("Command", "command function help")
CommandList = []


def init_db():
    cur = DB_CONN.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS record ("
                "id SERIAL PRIMARY KEY,"
                "user_id BIGINT NOT NULL,"
                "group_id BIGINT NOT NULL,"
                "role TEXT NOT NULL"
                ");")
    DB_CONN.commit()


def start(update, context):
    update.message.reply_text(f"Hi!")


def send_help(update, context):
    message = ["These are my commands:"]
    for obj in CommandList:
        message.append(f"`{PREFIX}{obj.command}`\t{obj.help}")
    update.message.reply_markdown("\n".join(message))


def prefix_command(command, help=""):
    def my_function(func):
        global CommandList

        def wrapper(update, context):
            chat = update.effective_chat
            if chat is not None and chat.type in ("group", "supergroup"):
                return func(update, context)
            update.message.reply_text("You can use this only on groups!")

        CommandList.append(Command(command, wrapper, help))
        return wrapper
    return my_function


@prefix_command(command="add")
def add_role(update, context):
    cur = DB_CONN.cursor()
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    roles = update.message.text.split()[1:]
    for role in roles:
        if role[0] == "@":
            role = role[1:]
        cur.execute("SELECT * FROM record WHERE user_id=%s AND group_id=%s AND role=%s", (user_id, chat_id, role))
        result = cur.fetchall()
        if result:
            update.message.reply_text(f"Role @{role} exists for you")
            continue
        cur.execute("INSERT INTO record(user_id, group_id, role) "
                    "VALUES (%s, %s, %s)", (user_id, chat_id, role))
        update.message.reply_text(f"Add role @{role}")
    DB_CONN.commit()


@prefix_command(command="del")
def delete_role(update, context):
    cur = DB_CONN.cursor()
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    roles = update.message.text.split()[1:]
    for role in roles:
        if role[0] == "@":
            role = role[1:]
        cur.execute("DELETE FROM record WHERE user_id=%s AND group_id=%s AND role=%s", (user_id, chat_id, role))
        update.message.reply_text(f"Delete role @{role}")
    DB_CONN.commit()


@prefix_command(command="get")
def get_role(update, context):
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    cur = DB_CONN.cursor()
    cur.execute("SELECT (role) FROM record WHERE group_id=%s AND user_id=%s", (chat_id, user_id))
    result = cur.fetchall()
    roles = [f"@{item[0]}" for item in result]
    update.message.reply_text("Your roles: \n" + " ".join(roles))


@prefix_command(command="getall")
def get_all_roles(update, context):
    chat_id = update.message.chat_id
    cur = DB_CONN.cursor()
    cur.execute("SELECT * FROM record WHERE group_id=%s", (chat_id,))
    result = cur.fetchall()
    roles = {}
    for record in result:
        roles.setdefault(record.role,  []).append(record.user_id)
    message = ["All roles: "]
    for role in roles.keys():
        message.append(f"\n@{role}: ")
        for user_id in roles[role]:
            member = context.bot.get_chat_member(chat_id, user_id)
            message.append(f"=> [{member.user.full_name}](tg://user?id={user_id})")
    update.message.reply_markdown("\n".join(message))


def check_mention(update, context):
    cur = DB_CONN.cursor()
    chat_id = update.message.chat_id

    if update.message.text is not None:
        text = update.message.text
    elif update.message.caption is not None:
        text = update.message.caption
    else:
        return
    text = text.split()

    users = set()
    for word in text:
        if word[0] == "@":
            cur.execute("SELECT (user_id) FROM record WHERE group_id=%s AND role=%s", (chat_id, word[1:]))
            result = cur.fetchall()
            users.update(item[0] for item in result)

    users = list(users)
    for i in range(0, len(users), BATCH):
        current = users[i:i + BATCH]
        message = []
        for user_id in current:
            member = context.bot.get_chat_member(chat_id, user_id)
            message.append(f"[{member.user.first_name}](tg://user?id={user_id})")
        update.message.reply_markdown(" ".join(message))


def main():
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", send_help))

    for obj in CommandList:
        dispatcher.add_handler(PrefixHandler(PREFIX, obj.command, obj.function))
        print(f"Command {obj.command} added {obj.function}")

    dispatcher.add_handler(MessageHandler(Filters.all, check_mention))
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
