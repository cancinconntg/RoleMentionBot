import os
import sqlite3
import telegram
from telegram.ext import Updater, CommandHandler, PrefixHandler, MessageHandler, Filters

PREFIX = "r!"
BATCH = 5

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise Exception("TOKEN not found")
DB_FILE = "local.db"
DB_CONN = sqlite3.connect(DB_FILE, check_same_thread=False)


def init_db():
    cur = DB_CONN.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS record ("
                "id INTEGER PRIMARY KEY,"
                "user_id INTEGER NOT NULL,"
                "group_id INTEGER NOT NULL,"
                "role TEXT NOT NULL"
                ");")
    DB_CONN.commit()


def start(update, context):
    update.message.reply_text(f"Hi!")


def send_help(update, context):
    update.message.reply_markdown("Hi! These are my commands.\n"
                                  "Works only in groups or supergroups!\n"
                                  "`r!add [roles...]`\n"
                                  "`r!del [roles...]`\n"
                                  "`r!get`")


def only_group(func):
    def wrapper(update, context):
        chat = update.effective_chat
        if chat is not None and chat.type in ("group", "supergroup"):
            return func(update, context)
        update.message.reply_text("You can use this only on groups!")
    return wrapper


@only_group
def add_role(update, context):
    cur = DB_CONN.cursor()
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    roles = update.message.text.split()[1:]
    for role in roles:
        if role[0] == "@":
            role = role[1:]
        cur.execute("SELECT * FROM record WHERE user_id=? AND group_id=? AND role=?", (user_id, chat_id, role))
        result = cur.fetchall()
        if result:
            update.message.reply_text(f"Role @{role} exists for you")
            continue
        cur.execute("INSERT INTO record(user_id, group_id, role) "
                    "VALUES (?, ?, ?)", (user_id, chat_id, role))
        update.message.reply_text(f"Add role @{role}")
    DB_CONN.commit()


@only_group
def delete_role(update, context):
    cur = DB_CONN.cursor()
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    roles = update.message.text.split()[1:]
    for role in roles:
        if role[0] == "@":
            role = role[1:]
        cur.execute("DELETE FROM record WHERE user_id=? AND group_id=? AND role=?", (user_id, chat_id, role))
        update.message.reply_text(f"Delete role @{role}")
    DB_CONN.commit()


@only_group
def get_role(update, context):
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    cur = DB_CONN.cursor()
    cur.execute("SELECT (role) FROM record WHERE group_id=? AND user_id=?", (chat_id, user_id))
    result = cur.fetchall()
    roles = [f"@{item[0]}" for item in result]
    update.message.reply_text("Your roles: \n" + " ".join(roles))


@only_group
def check_mention(update, context):
    cur = DB_CONN.cursor()
    chat_id = update.message.chat_id
    bot = context.bot

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
            cur.execute("SELECT (user_id) FROM record WHERE group_id=? AND role=?", (chat_id, word[1:]))
            result = cur.fetchall()
            users.update(item[0] for item in result)

    users = list(users)
    for i in range(0, len(users), BATCH):
        current = users[i:i + BATCH]
        message = []
        for idx in current:
            member = bot.get_chat_member(chat_id, idx)
            message.append(f"[{member.user.first_name}](tg://user?id={idx})")
        update.message.reply_markdown(" ".join(message))


def main():
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", send_help))
    dispatcher.add_handler(PrefixHandler(PREFIX, "add", add_role))
    dispatcher.add_handler(PrefixHandler(PREFIX, "del", delete_role))
    dispatcher.add_handler(PrefixHandler(PREFIX, "get", get_role))
    dispatcher.add_handler(MessageHandler(Filters.all, check_mention))
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
