import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

import native_app
from lan import LanService


class CollaborationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.patch=patch.object(native_app,'datadir',return_value=self.root)
        self.patch.start()
        self.bridge=native_app.Bridge()
        self.bridge.saveState(native_app.initial_state())
    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_solo_comment_persists_and_activity_is_readable(self):
        event={'type':'comment.add','eventId':'event-1','cardId':'example-1',
               'text':'توضیح اولیه'}
        first=self.bridge.collabCommand(event)
        second=self.bridge.collabCommand(event)
        self.assertEqual(first,second)
        comments=self.bridge.collabRead('comments','example-1')
        self.assertEqual(len(comments),1)
        self.assertEqual(comments[0]['text'],'توضیح اولیه')
        self.assertTrue(self.bridge.collabRead('activity'))
        self.assertTrue((self.root/'collab.json').exists())

    def test_lan_comment_mentions_and_permissions(self):
        service=LanService(self.bridge,self.root/'accounts.json',bind='127.0.0.1',port=0)
        service.setup_owner('admin','a-strong-password')
        port=service.start()
        def req(path,payload=None,token=None):
            request=Request(f'http://127.0.0.1:{port}'+path,
                            data=json.dumps(payload).encode('utf8') if payload is not None else None,
                            headers={'Content-Type':'application/json',
                                     **({'Authorization':'Bearer '+token} if token else {})},
                            method='POST' if payload is not None else 'GET')
            with urlopen(request,timeout=6) as r:return json.loads(r.read())
        try:
            owner=req('/api/login',{'username':'admin','password':'a-strong-password'})['token']
            req('/api/user',{'username':'writer','password':'writer-pass-012',
                             'role':'editor','projects':['p-sample']},owner)
            req('/api/user',{'username':'viewer','password':'viewer-pass-012',
                             'role':'viewer','projects':['p-personal']},owner)
            writer=req('/api/login',{'username':'writer','password':'writer-pass-012'})['token']
            viewer=req('/api/login',{'username':'viewer','password':'viewer-pass-012'})['token']
            req('/api/collab',{'type':'comment.add','eventId':'comment-1','cardId':'example-1',
                               'text':'توضیح برای @admin'},writer)
            self.assertEqual(len(req('/api/comments?cardId=example-1',token=owner)['items']),1)
            self.assertEqual(len(req('/api/notifications',token=owner)['items']),1)
            with self.assertRaises(HTTPError) as caught:
                req('/api/comments?cardId=example-1',token=viewer)
            self.assertEqual(caught.exception.code,403)
            with self.assertRaises(HTTPError) as caught:
                req('/api/collab',{'type':'comment.add','eventId':'unauthorized-1',
                                   'cardId':'example-1','text':'unauthorized'},viewer)
            self.assertEqual(caught.exception.code,403)
        finally:
            service.stop()


if __name__=='__main__':
    unittest.main()
