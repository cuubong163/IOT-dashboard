"""CareLink lab gateway. Python 3.10+. Run from the project root.
No hardware data are fabricated. Adapters require the firmware contract in README.md.
"""
import asyncio
import contextlib
import json
import logging
import os
import struct
import time
from collections import OrderedDict
from pathlib import Path
from aiohttp import web, WSMsgType

LOG = logging.getLogger('carelink')
ROOT = Path(__file__).resolve().parent.parent

def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack('<H', crc)

def validate_command(msg):
    if not isinstance(msg, dict) or msg.get('type') != 'command':
        raise ValueError('Bản tin phải có type=command')
    node, action, value = msg.get('node'), msg.get('action'), msg.get('value')
    if not isinstance(msg.get('id'), str) or not 1 <= len(msg['id']) <= 100:
        raise ValueError('Mã lệnh không hợp lệ')
    if type(node) is not int or node not in (1, 2, 3):
        raise ValueError('Node không hợp lệ')
    allowed = {1: {'set_rate', 'set_measuring'}, 2: {'set_fan'}, 3: {'set_buzzer', 'clear_fall'}}
    if action not in allowed[node]:
        raise ValueError('Lệnh không được hỗ trợ cho node')
    if action == 'set_rate':
        if type(value) is not int or value not in (125, 250, 500):
            raise ValueError('Tần số lấy mẫu không hợp lệ')
    elif type(value) is not bool:
        raise ValueError('Giá trị điều khiển phải là true hoặc false')
    return node, action, value

class Hub:
    def __init__(self):
        self.clients = set()
        self.pending = {}
        self.mqtt = None
        self.serial_lora = None
        self.modbus = None
        self.loop = None
        self.sequences = OrderedDict()
        self.command_lock = asyncio.Lock()

    async def broadcast(self, msg):
        for client in list(self.clients):
            try:
                await asyncio.wait_for(client.send_json(msg), 1)
            except (ConnectionError, asyncio.TimeoutError, RuntimeError):
                self.clients.discard(client)

    async def ingest(self, msg, source_node):
        if not isinstance(msg, dict):
            return
        if msg.get('type') == 'ack':
            pending = self.pending.get(msg.get('id'))
            if pending and pending[0] == source_node and type(msg.get('ok')) is bool:
                if not pending[1].done():
                    pending[1].set_result(msg)
            return
        if msg.get('type') != 'telemetry' or msg.get('node') != source_node or not isinstance(msg.get('data'), dict):
            return
        # Optional monotonically increasing sequence + unique boot_id for QoS-1 duplicate detection.
        seq = msg.get('seq')
        boot = msg.get('boot_id')
        if type(seq) is int and isinstance(boot, str):
            key = (source_node, boot[:100], seq)
            if key in self.sequences:
                return
            self.sequences[key] = True
            while len(self.sequences) > 512:
                self.sequences.popitem(last=False)
        msg['received_at'] = time.time()
        await self.broadcast(msg)

    async def command(self, msg):
        node, action, value = validate_command(msg)
        cmd_id = msg['id']
        if cmd_id in self.pending:
            raise ValueError('Mã lệnh đang được xử lý')
        if node == 2:
            if self.modbus is None:
                raise ValueError('Chưa cấu hình RS485_PORT')
            async with self.command_lock:
                if self.modbus is None:
                    raise ValueError('Node 2 chưa kết nối')
                await asyncio.to_thread(self.modbus.set_fan, value)
            return {'type': 'ack', 'id': cmd_id, 'ok': True}
        future = asyncio.get_running_loop().create_future()
        self.pending[cmd_id] = (node, future)
        try:
            payload = json.dumps(msg, ensure_ascii=False, allow_nan=False)
            if node == 1:
                if self.mqtt is None or not self.mqtt.is_connected():
                    raise ValueError('MQTT broker chưa kết nối')
                result = self.mqtt.publish('carelink/node1/command', payload, qos=1, retain=False)
                if result.rc != 0:
                    raise ValueError('MQTT từ chối gửi lệnh')
            elif node == 3:
                if self.serial_lora is None:
                    raise ValueError('Chưa cấu hình LORA_PORT')
                await asyncio.to_thread(self.serial_lora.write, (payload + '\n').encode())
            # A successful transport write is NOT a successful device command.
            return await asyncio.wait_for(future, timeout=6)
        finally:
            self.pending.pop(cmd_id, None)

HUB_KEY = web.AppKey('hub', Hub)
TASKS_KEY = web.AppKey('tasks', list)

class ModbusNode2:
    """Proposed firmware map: FC03 registers 0=temp*10 signed,1=humidity*10,2=fan.
    Fan writes FC06 register 2. Address 1, 9600 8N1, USB-RS485 auto direction.
    """
    def __init__(self, port):
        import serial
        self.serial = serial.Serial(port, 9600, timeout=0.5, write_timeout=0.5)

    def exchange(self, request, expected):
        self.serial.reset_input_buffer()
        self.serial.write(request + crc16(request))
        self.serial.flush()
        response = self.serial.read(expected)
        if len(response) < 5 or crc16(response[:-2]) != response[-2:]:
            raise ValueError('Modbus timeout hoặc CRC sai')
        if response[0] != 1 or response[1] != request[1]:
            raise ValueError('Modbus sai địa chỉ/hàm hoặc trả exception')
        if len(response) != expected:
            raise ValueError('Modbus sai độ dài')
        return response

    def read(self):
        response = self.exchange(bytes.fromhex('01 03 00 00 00 03'), 11)
        if response[2] != 6:
            raise ValueError('Modbus sai số byte dữ liệu')
        temp, humidity, fan = struct.unpack('>hHH', response[3:9])
        if not -400 <= temp <= 1000 or not 0 <= humidity <= 1000 or fan not in (0, 1):
            raise ValueError('Modbus dữ liệu ngoài phạm vi')
        return {'type': 'telemetry', 'node': 2, 'data': {'temp': temp / 10, 'humidity': humidity / 10, 'fan': bool(fan)}}

    def set_fan(self, value):
        request = struct.pack('>BBHH', 1, 6, 2, int(value))
        response = self.exchange(request, 8)
        if response[:-2] != request:
            raise ValueError('Thiết bị chưa xác nhận ghi relay')

async def poll_modbus(hub):
    while True:
        try:
            if hub.modbus is None:
                hub.modbus = await asyncio.to_thread(ModbusNode2, os.environ['RS485_PORT'])
            async with hub.command_lock:
                msg = await asyncio.to_thread(hub.modbus.read)
            await hub.ingest(msg, 2)
        except (OSError, ValueError, ImportError) as exc:
            LOG.warning('Node 2: %s', exc)
            if hub.modbus:
                hub.modbus.serial.close()
            hub.modbus = None
        await asyncio.sleep(3)

async def read_lora(hub):
    while True:
        try:
            if hub.serial_lora is None:
                import serial
                hub.serial_lora = await asyncio.to_thread(serial.Serial, os.environ['LORA_PORT'], 115200, timeout=0.3, write_timeout=0.5)
            raw = await asyncio.to_thread(hub.serial_lora.read_until, b'\n', 8192)
            if not raw:
                continue
            if not raw.endswith(b'\n'):
                LOG.warning('LoRa: bỏ dòng Serial không hoàn chỉnh')
                continue
            await hub.ingest(json.loads(raw), 3)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            LOG.warning('LoRa: bỏ bản tin không hợp lệ')
        except (OSError, ImportError) as exc:
            LOG.warning('LoRa Serial: %s', exc)
            if hub.serial_lora:
                hub.serial_lora.close()
            hub.serial_lora = None
            await asyncio.sleep(3)

async def startup(app):
    hub = app[HUB_KEY]
    hub.loop = asyncio.get_running_loop()
    tasks = app[TASKS_KEY]
    if os.getenv('MQTT_HOST'):
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='carelink-gateway')
        if os.getenv('MQTT_USERNAME'):
            client.username_pw_set(os.environ['MQTT_USERNAME'], os.getenv('MQTT_PASSWORD'))
        if os.getenv('MQTT_TLS') == '1':
            client.tls_set()
        def on_connect(c, userdata, flags, reason, properties):
            if reason == 0:
                c.subscribe([('carelink/node1/telemetry', 1), ('carelink/node1/ack', 1)])
                LOG.info('MQTT đã kết nối')
            else:
                LOG.warning('MQTT chưa kết nối: %s', reason)
        def on_message(c, userdata, message):
            if message.retain:
                return  # retained historical data are not current measurements
            try:
                msg = json.loads(message.payload)
                if isinstance(msg, dict):
                    asyncio.run_coroutine_threadsafe(hub.ingest(msg, 1), hub.loop)
            except (ValueError, UnicodeError):
                LOG.warning('MQTT: bỏ bản tin không hợp lệ')
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect_async(os.environ['MQTT_HOST'], int(os.getenv('MQTT_PORT', '1883')), 30)
        client.loop_start()
        hub.mqtt = client
    if os.getenv('RS485_PORT'):
        tasks.append(asyncio.create_task(poll_modbus(hub)))
    if os.getenv('LORA_PORT'):
        tasks.append(asyncio.create_task(read_lora(hub)))
    LOG.info('Gateway sẵn sàng. Adapter đã bật: MQTT=%s RS485=%s LoRa=%s', bool(hub.mqtt), bool(os.getenv('RS485_PORT')), bool(os.getenv('LORA_PORT')))

async def cleanup(app):
    for task in app[TASKS_KEY]:
        task.cancel()
    for task in app[TASKS_KEY]:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    hub = app[HUB_KEY]
    for client in list(hub.clients):
        await client.close()
    if hub.mqtt:
        hub.mqtt.disconnect()
        hub.mqtt.loop_stop()
    if hub.serial_lora:
        hub.serial_lora.close()
    if hub.modbus:
        hub.modbus.serial.close()

async def ws_handler(request):
    # Default local-only gateway. Reject web pages from unrelated origins.
    allowed = {f'http://localhost:{request.url.port or 80}', f'http://127.0.0.1:{request.url.port or 80}'}
    allowed.update(x.strip() for x in os.getenv('ALLOWED_ORIGINS', '').split(',') if x.strip())
    if request.headers.get('Origin') not in allowed:
        raise web.HTTPForbidden(text='Origin không được phép')
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=16384)
    await ws.prepare(request)
    hub = request.app[HUB_KEY]
    hub.clients.add(ws)
    try:
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                continue
            cmd_id = None
            try:
                msg = json.loads(message.data)
                if isinstance(msg, dict):
                    cmd_id = msg.get('id')
                result = await hub.command(msg)
                await ws.send_json(result)
            except (ValueError, OSError, asyncio.TimeoutError) as exc:
                await ws.send_json({'type': 'ack', 'id': cmd_id, 'ok': False, 'error': str(exc) or 'Thiết bị chưa phản hồi'})
    finally:
        hub.clients.discard(ws)
    return ws

async def index_handler(request):
    return web.FileResponse(ROOT / 'dist' / 'index.html')

def create_app():
    app = web.Application()
    app[HUB_KEY] = Hub()
    app[TASKS_KEY] = []
    app.router.add_get('/ws', ws_handler)
    app.router.add_get('/', index_handler)
    app.router.add_static('/', ROOT / 'dist', show_index=False)
    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    web.run_app(create_app(), host=os.getenv('GATEWAY_HOST', '127.0.0.1'), port=int(os.getenv('GATEWAY_PORT', '8080')))
