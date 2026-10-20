"""Dependency-free staging D1 schema verification using SQLite.

D1 is SQLite-based. This smoke test checks the committed migration SQL can
be applied on an empty DB and that tenant/immutability constraints remain.
A Cloudflare staging migration and phone E2E are still required separately.
"""
from pathlib import Path
import sqlite3
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


class D1SchemaSmoke(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        for name in ("0001_intake.sql", "0002_static_previews.sql",
                     "0003_ai_attempts.sql"):
            self.db.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))

    def tearDown(self):
        self.db.close()

    def test_fails_closed_until_owner_resumes(self):
        self.assertEqual(
            self.db.execute("SELECT paused FROM ivy_control WHERE id=1").fetchone(),
            (1,),
        )

    def test_requests_have_owner_and_idempotency_uniqueness(self):
        row_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO ivy_requests(id,owner_email,idempotency_key,mode,prompt,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (row_id,"owner@example.com","x"*16,"web","hello","awaiting_hosted_worker",1)
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO ivy_requests(id,owner_email,idempotency_key,mode,prompt,status,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (str(uuid.uuid4()),"owner@example.com","x"*16,"web","other","awaiting_hosted_worker",2)
            )
        # Same idempotency key is a separate namespace for another OWNER.
        self.db.execute(
            "INSERT INTO ivy_requests(id,owner_email,idempotency_key,mode,prompt,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()),"another@example.com","x"*16,
             "app","independent","awaiting_hosted_worker",2)
        )

    def test_template_checks_reject_invalid_generator_and_oversize(self):
        row_id=str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO ivy_requests(id,owner_email,idempotency_key,mode,prompt,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (row_id,"owner@example.com","a"*16,"web","test","template_ready",1)
        )
        base=(row_id,"owner@example.com","static_template_v1","<html></html>","[]",1)
        self.db.execute(
            "INSERT INTO ivy_static_previews(request_id,owner_email,generator,html,checks_json,created_at) "
            "VALUES(?,?,?,?,?,?)",base
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO ivy_static_previews(request_id,owner_email,generator,html,checks_json,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()),"owner@example.com","untrusted_generator","x","[]",1)
            )
        other_id=str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO ivy_requests(id,owner_email,idempotency_key,mode,prompt,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (other_id,"owner@example.com","b"*16,"web","test","template_ready",2)
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO ivy_static_previews(request_id,owner_email,generator,html,checks_json,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (other_id,"owner@example.com","static_template_v1","X"*20001,"[]",2)
            )

    def test_ai_attempts_allow_one_row_per_request(self):
        row_id=str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO ivy_requests(id,owner_email,idempotency_key,mode,prompt,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (row_id,"owner@example.com","c"*16,"web","test","awaiting_hosted_worker",1)
        )
        self.db.execute(
            "INSERT INTO ivy_ai_attempts(request_id,owner_email,status,created_at) "
            "VALUES(?,?,?,?)",(row_id,"owner@example.com","reserved",1)
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO ivy_ai_attempts(request_id,owner_email,status,created_at) "
                "VALUES(?,?,?,?)",(row_id,"owner@example.com","reserved",1)
            )


if __name__ == "__main__":
    unittest.main()
