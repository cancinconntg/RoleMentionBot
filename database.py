import sqlite3
from typing import NamedTuple


class Record(NamedTuple):
    id: int
    user_id: int
    group_id: int
    role: str

    @classmethod
    def factory(cls, cursor, row):
        return cls(*row)


class Database:
    def __init__(self, dbfile):
        self.db = sqlite3.connect(dbfile, check_same_thread=False)
        self.db.row_factory = Record.factory
        self.init_tables()

    def __del__(self):
        self.db.close()

    def init_tables(self):
        cur = self.db.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS roletable ("
                    "id INTEGER PRIMARY KEY,"
                    "user_id INTEGER NOT NULL,"
                    "group_id INTEGER NOT NULL,"
                    "role TEXT NOT NULL"
                    ");")
        self.db.commit()

    def select(self, **kwargs):
        req = "SELECT * FROM roletable WHERE " + " AND ".join(f"{key}=?" for key in kwargs.keys())
        if not kwargs:
            req = "SELECT * FROM roletable"
        cur = self.db.cursor()
        cur.execute(req, list(kwargs.values()))
        result = cur.fetchall()
        return list(result)

    def insert(self, user_id, group_id, role):
        cur = self.db.cursor()
        cur.execute("INSERT INTO roletable(user_id, group_id, role) "
                    "VALUES (?, ?, ?)", (user_id, group_id, role))
        self.db.commit()
        return cur.rowcount

    def delete(self, **kwargs):
        req = "DELETE FROM roletable WHERE " + " AND ".join(f"{key}=?" for key in kwargs.keys())
        if not kwargs:
            req = "DELETE FROM roletable"
        cur = self.db.cursor()
        cur.execute(req, list(kwargs.values()))
        self.db.commit()
        return cur.rowcount

    def exist(self, group_id, role):
        cur = self.db.cursor()
        cur.execute("SELECT * FROM roletable WHERE group_id=? AND role=?", (group_id, role))
        return bool(cur.fetchall())
