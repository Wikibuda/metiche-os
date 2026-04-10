from __future__ import annotations

import unittest

from sqlmodel import Session, SQLModel, create_engine, select

from app.domain.channel_memory.models import ChannelMemory
from app.services.channel_memory_service import ChannelMemoryService


class ChannelMemoryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.service = ChannelMemoryService(self.session)

    def tearDown(self) -> None:
        self.session.close()

    def test_save_and_get_context_for_multiple_channels(self) -> None:
        whatsapp_context = {"last_message": "hola", "intent": "saludo"}
        telegram_context = {"last_message": "seguimos", "intent": "continuacion"}

        saved_whatsapp = self.service.save_context("test_user", "whatsapp", whatsapp_context)
        self.assertEqual(saved_whatsapp.client_key, "test_user")
        self.assertEqual(saved_whatsapp.channel, "whatsapp")

        saved_telegram = self.service.save_context("test_user", "telegram", telegram_context)
        self.assertEqual(saved_telegram.client_key, "test_user")
        self.assertEqual(saved_telegram.channel, "telegram")

        loaded_whatsapp = self.service.get_context("test_user", "whatsapp")
        loaded_telegram = self.service.get_context("test_user", "telegram")

        self.assertEqual(loaded_whatsapp, whatsapp_context)
        self.assertEqual(loaded_telegram, telegram_context)

    def test_save_context_updates_existing_row(self) -> None:
        self.service.save_context("test_user", "whatsapp", {"step": 1})
        self.service.save_context("test_user", "whatsapp", {"step": 2, "status": "ok"})

        rows = self.session.exec(select(ChannelMemory)).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].context, {"step": 2, "status": "ok"})

    def test_delete_context_removes_row(self) -> None:
        self.service.save_context("test_user", "whatsapp", {"step": 1})
        deleted = self.service.delete_context("test_user", "whatsapp")
        self.assertTrue(deleted)
        self.assertIsNone(self.service.get_context("test_user", "whatsapp"))


if __name__ == "__main__":
    unittest.main()
