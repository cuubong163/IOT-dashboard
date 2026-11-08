import asyncio
import json
import unittest
from aiohttp import ClientSession, WSServerHandshakeError
from aiohttp.test_utils import TestServer
from gateway import Hub, crc16, validate_command, create_app, HUB_KEY

class ContractTests(unittest.TestCase):
    def test_crc_known_modbus_request(self):
        self.assertEqual(crc16(bytes.fromhex('01 03 00 00 00 0A')), bytes.fromhex('C5 CD'))

    def test_reject_wrong_node_action_and_rate(self):
        for msg in [
            {'type':'command','id':'x','node':1,'action':'set_buzzer','value':True},
            {'type':'command','id':'x','node':1,'action':'set_rate','value':1000},
            {'type':'command','id':'x','node':2,'action':'set_fan','value':'true'},
        ]:
            with self.assertRaises(ValueError): validate_command(msg)

class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_device_ack_required(self):
        hub=Hub()
        class FakeMQTT:
            def is_connected(self): return True
            def publish(self, topic, payload, **kwargs):
                msg=json.loads(payload)
                asyncio.create_task(hub.ingest({'type':'ack','id':msg['id'],'ok':True},1))
                return type('Result',(),{'rc':0})()
        hub.mqtt=FakeMQTT()
        response=await hub.command({'type':'command','id':'ack-test','node':1,'action':'set_rate','value':250})
        self.assertTrue(response['ok'])
        self.assertFalse(hub.pending)
        hub.mqtt=None
        with self.assertRaises(ValueError):
            await hub.command({'type':'command','id':'no-mqtt','node':1,'action':'set_measuring','value':False})
        self.assertFalse(hub.pending)

    async def test_end_to_end_websocket_and_origin(self):
        server=TestServer(create_app())
        await server.start_server()
        origin=str(server.make_url('/')).rstrip('/')
        try:
            async with ClientSession() as session:
                async with session.get(server.make_url('/')) as response:
                    self.assertEqual(response.status,200)
                    self.assertIn('CareLink',await response.text())
                with self.assertRaises(WSServerHandshakeError):
                    await session.ws_connect(server.make_url('/ws'),headers={'Origin':'https://unrelated.example'})
                async with session.ws_connect(server.make_url('/ws'),headers={'Origin':origin}) as ws:
                    hub=server.app[HUB_KEY]
                    telemetry={'type':'telemetry','node':2,'seq':1,'boot_id':'a','data':{'temp':26.1,'humidity':60,'fan':False}}
                    await hub.ingest(telemetry,2)
                    received=await ws.receive_json(timeout=2)
                    self.assertEqual(received['data']['temp'],26.1)
                    # QoS duplicate never reaches subscribers.
                    await hub.ingest(telemetry,2)
                    await ws.send_json({'type':'command','id':'offline-relay','node':2,'action':'set_fan','value':True})
                    reply=await ws.receive_json(timeout=2)
                    self.assertEqual(reply['id'],'offline-relay')
                    self.assertFalse(reply['ok'])
        finally:
            await server.close()

if __name__=='__main__': unittest.main()
