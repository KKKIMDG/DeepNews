"""Account deletion, with the DB session stubbed so no connection is made."""
import importlib
from pathlib import Path
import sys
import types
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import DeclarativeBase


class AccountDeletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = dict(sys.modules)
        root = Path(__file__).resolve().parents[1] / 'backend'
        for name, path in [('backend', root), ('backend.domains', root / 'domains'),
                           ('backend.domains.auth', root / 'domains/auth')]:
            module = types.ModuleType(name)
            module.__path__ = [str(path)]
            sys.modules[name] = module
        database = types.ModuleType('backend.database')

        class Base(DeclarativeBase):
            pass

        database.Base = Base
        database.get_session = MagicMock()
        sys.modules['backend.database'] = database
        cls.service = importlib.import_module('backend.domains.auth.service')
        cls.router = importlib.import_module('backend.domains.auth.router')
        cls.dependencies = importlib.import_module('backend.domains.auth.dependencies')
        cls.security = importlib.import_module('backend.domains.auth.security')

    @classmethod
    def tearDownClass(cls):
        for name in list(sys.modules):
            if name.startswith('backend'):
                sys.modules.pop(name, None)
        sys.modules.update({k: v for k, v in cls.saved.items() if k.startswith('backend')})

    def session_with_user(self, password='correct-password'):
        session = MagicMock()
        session.get.return_value = types.SimpleNamespace(id=7, password_hash=self.security.hash_password(password))
        return session

    def test_right_password_deletes_user_row(self):
        session = self.session_with_user()
        self.service.delete_account(session, 7, 'correct-password')
        statement = session.execute.call_args.args[0]
        self.assertEqual(statement.table.name, 'app_user')
        self.assertEqual(statement.compile().params, {'id_1': 7})

    def test_wrong_password_is_403_and_deletes_nothing(self):
        session = self.session_with_user()
        with self.assertRaises(HTTPException) as caught:
            self.service.delete_account(session, 7, 'wrong-password')
        self.assertEqual(caught.exception.status_code, 403)  # 401 would make the extension sign out
        session.execute.assert_not_called()

    def test_endpoint_requires_login_and_password(self):
        try:
            from fastapi.testclient import TestClient
        except RuntimeError as missing:  # the server venv has no httpx client
            self.skipTest(str(missing))
        app = FastAPI()
        app.include_router(self.router.router)
        client = TestClient(app)
        with patch.object(self.router, 'get_session', return_value=nullcontext(MagicMock())), \
             patch.object(self.router.service, 'delete_account') as delete_account:
            self.assertEqual(client.request('DELETE', '/api/v1/auth/me', json={'password': 'x'}).status_code, 401)
            app.dependency_overrides[self.dependencies.get_current_user] = \
                lambda: self.dependencies.CurrentUser(id=7, email='a@b.co', ad_filter_threshold=0.8)
            self.assertEqual(client.request('DELETE', '/api/v1/auth/me').status_code, 422)
            response = client.request('DELETE', '/api/v1/auth/me', json={'password': 'pw'})
            self.assertEqual(response.status_code, 204)
            self.assertEqual(delete_account.call_args.args[1:], (7, 'pw'))

    def test_login_locks_after_repeated_failures(self):
        service = self.service
        service.LOGIN_FAILURES.reset('lock@b.co')
        session = MagicMock()
        session.scalar.return_value = types.SimpleNamespace(id=7, password_hash=self.security.hash_password('right-password'))
        for _ in range(5):
            with self.assertRaises(HTTPException) as caught:
                service.login(session, 'lock@b.co', 'wrong')
            self.assertEqual(caught.exception.status_code, 401)
        with self.assertRaises(HTTPException) as caught:
            service.login(session, 'lock@b.co', 'right-password')  # even the right password waits out the window
        self.assertEqual(caught.exception.status_code, 429)
        service.LOGIN_FAILURES.reset('lock@b.co')
        self.assertEqual(service.login(session, 'lock@b.co', 'right-password')[0].id, 7)

    def test_change_password_keeps_only_current_session(self):
        session = self.session_with_user()
        with self.assertRaises(HTTPException) as caught:
            self.service.change_password(session, 7, 'token', 'wrong-password', 'new-password-1')
        self.assertEqual(caught.exception.status_code, 403)
        self.service.change_password(session, 7, 'token', 'correct-password', 'new-password-1')
        user = session.get.return_value
        self.assertTrue(self.security.verify_password('new-password-1', user.password_hash))
        where = str(session.execute.call_args.args[0].compile(compile_kwargs={'literal_binds': True}))
        self.assertIn('user_session.token_hash !=', where)
        self.assertIn(self.security.hash_session_token('token'), where)

    def test_signup_requires_invite_code_when_configured(self):
        service = self.service
        session = MagicMock()
        session.scalar.return_value = None
        with patch.object(service, 'settings', types.SimpleNamespace(signup_invite_code='team-2026')):
            with self.assertRaises(HTTPException) as caught:
                service.signup(session, 'new@b.co', 'password-123', 'wrong')
            self.assertEqual(caught.exception.status_code, 403)
            session.add.assert_not_called()
            service.signup(session, 'new@b.co', 'password-123', ' team-2026 ')
        session.add.assert_called()
        service.SIGNUPS.reset('all')


    def test_signup_interests_are_validated_and_deduplicated(self):
        from pydantic import ValidationError
        schemas = importlib.import_module('backend.domains.auth.schemas')
        req = schemas.SignupRequest(email='a@b.co', password='password-123',
                                    topics=['경제', 'IT_과학', '경제'], keywords=['반도체'])
        self.assertEqual(req.topics, ['경제', 'IT_과학'])
        self.assertEqual(schemas.SignupRequest(email='a@b.co', password='password-123').topics, [])
        with self.assertRaises(ValidationError):
            schemas.SignupRequest(email='a@b.co', password='password-123', topics=['연예인'])
        with self.assertRaises(ValidationError):
            schemas.SignupRequest(email='a@b.co', password='password-123', keywords=['k'] * 11)

    def test_initial_keywords_are_normalized_and_noise_dropped(self):
        personalization = importlib.import_module('backend.domains.personalization.service')
        session = MagicMock()
        with patch.object(personalization.repository, 'replace_topics') as topics,                 patch.object(personalization.repository, 'upsert_preference') as upsert:
            personalization.set_initial_interests(session, 7, ['스포츠'], ['야구를', '있다', '야구', 'AI'])
        topics.assert_called_once_with(session, 7, ['스포츠'])
        self.assertEqual([call.args[2] for call in upsert.call_args_list], ['야구', 'AI'])
        self.assertTrue(all(call.args[3] == 'include' for call in upsert.call_args_list))

if __name__ == '__main__':
    unittest.main()
