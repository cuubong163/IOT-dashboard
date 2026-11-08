# CareLink — Dashboard quản lý 3 node IoT y tế

Giao diện tiếng Việt, tông xanh ngọc, chạy trên máy tính và điện thoại.

## Đã có

- Tổng quan 3 node, nhịp tim, SpO₂, nhiệt độ và độ ẩm.
- Biểu đồ ECG cuộn trực tiếp và biểu đồ môi trường (1, 5, 15 phút).
- Node 1: đổi tần số 125/250/500 Hz, tạm dừng hoặc tiếp tục đo.
- Node 2: bật/tắt relay quạt; tùy chọn tự bật khi vượt ngưỡng nhiệt độ.
- Node 3: xem gia tốc X/Y/Z, pin, RSSI, trạng thái vận động; xác nhận té ngã, bật/tắt còi, xóa sự cố sau kiểm tra.
- Cảnh báo theo ngưỡng, mất liên lạc, xác nhận đã tiếp nhận.
- Nhật ký hoạt động, lọc theo node, tìm kiếm, xuất CSV có dấu tiếng Việt.
- Chế độ mô phỏng chạy ngay; chế độ thiết bị thực qua WebSocket.
- Gateway Python mẫu: MQTT, Modbus RTU qua USB–RS485, LoRa qua ESP32 nhận và USB Serial.

**Phạm vi:** đây là dashboard và Gateway mẫu cho bài tập. Chưa kèm chương trình nạp cho ESP32. Các node cần thực hiện đúng quy ước bên dưới hoặc bạn cần sửa adapter tương ứng theo chương trình đang có. Chưa có kiểm thử với phần cứng thật. Không coi việc MQTT gửi thành công là thiết bị đã thực hiện lệnh.

## 1. Chạy nhanh giao diện, chưa cần phần cứng

Cài Python 3.10 trở lên. Giải nén, mở Terminal tại thư mục chứa README này:

```bash
python -m http.server 8000 --directory dist
```

Trên Linux nếu lệnh `python` không có, dùng `python3`.
Mở **http://localhost:8000**. Dashboard khởi động ở chế độ mô phỏng.

Thử nhanh:
1. Vào **Sinh hiệu**, chọn 500 Hz và bấm **Áp dụng tần số**; thử công tắc đo liên tục.
2. Vào **Môi trường**, bật/tắt quạt mô phỏng.
3. Vào **Vận động & té ngã**, bấm **Mô phỏng té ngã**, sau đó **Xác nhận & bật còi**.
4. Vào **Cảnh báo**, xác nhận sự kiện. Có thể thử nhiệt độ cao trong 20 giây.
5. Bấm **Xuất dữ liệu** để tải CSV của phiên đang mở.

Phông chữ trực tuyến có phông hệ thống dự phòng; giao diện vẫn dùng được khi không tải được phông.

## 2. Chạy cùng Gateway tại máy tính

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r gateway\requirements.txt
.venv\Scripts\python.exe gateway\gateway.py
```

### Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r gateway/requirements.txt
.venv/bin/python gateway/gateway.py
```

Mở **http://localhost:8080** → **Kết nối & cài đặt** → nhập `ws://localhost:8080/ws` → **Kết nối Gateway**.

Nếu chưa khai báo adapter/phần cứng, Gateway vẫn mở được nhưng không tự tạo dữ liệu. Các node hiện “Chưa có dữ liệu”; lệnh bị từ chối khi chưa có thiết bị. Có thể quay về **Mô phỏng** bất kỳ lúc nào.

### Bật các adapter

Dừng Gateway bằng Ctrl+C, đặt các biến môi trường rồi chạy lại. Ví dụ Windows PowerShell:

```powershell
$env:MQTT_HOST="192.168.1.10"
$env:MQTT_PORT="1883"
$env:RS485_PORT="COM5"
$env:LORA_PORT="COM6"
.venv\Scripts\python.exe gateway\gateway.py
```

Linux:

```bash
export MQTT_HOST=192.168.1.10
export MQTT_PORT=1883
export RS485_PORT=/dev/ttyUSB0
export LORA_PORT=/dev/ttyUSB1
.venv/bin/python gateway/gateway.py
```

Thay IP/cổng COM bằng thông tin thực tế; không sao chép nguyên ví dụ. Chỉ bật biến của phần cứng đã cắm. `MQTT_HOST` là broker MQTT (ví dụ Mosquitto), không phải dashboard. Phần mềm không cài broker hộ bạn.
Có thể đặt thêm `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TLS=1` và cổng TLS phù hợp. Không ghi mật khẩu vào mã nguồn.

Gateway mặc định chỉ lắng nghe `127.0.0.1:8080`. Web đã xuất bản dùng HTTPS, nên không thể kết nối trực tiếp đến Gateway `ws://` tại nhà bạn. Cách đơn giản nhất khi thực hành là chạy cả web và Gateway trên máy tính bằng cách trên. Nếu cần truy cập từ xa, phải cấu hình WSS qua reverse proxy có xác thực, chứng chỉ hợp lệ và khai báo `ALLOWED_ORIGINS` đúng địa chỉ web. Bản mẫu không cung cấp xác thực cho việc phơi Gateway ra Internet.

## 3. Cách ghép phần cứng

| Node | Đường đến Gateway | Thiết bị bổ sung ở đầu Gateway |
|---|---|---|
| 1: ESP32 + MAX30100 + AD8232 | Wi-Fi → broker MQTT → Gateway | Máy tính chạy broker hoặc broker trong mạng |
| 2: ESP32 + DHT22 + MAX485 | RS485 → USB | USB–RS485 có tự điều khiển chiều truyền |
| 3: ESP32 + MPU6050 + Ra-02 | LoRa → ESP32 nhận → USB Serial | Thêm ESP32 và **thêm một Ra-02 433 MHz** |

- Không cần Raspberry Pi; máy tính Windows/Linux làm Gateway được.
- Một Ra-02 tại Node 3 là chưa đủ: LoRa cần thiết bị thu ở đầu Gateway.
- Node 2 cần thêm relay + quạt nếu muốn điều khiển thông gió.
- Buzzer 5V cần nguồn phù hợp và mạch kích transistor/MOSFET; không cấp trực tiếp từ GPIO ESP32.
- ESP32 dùng logic 3,3V. Kiểm tra MAX485 và từng module trước khi đấu nối.
- RS485 cần đấu A/B đúng, tham chiếu chung phù hợp, và điện trở kết thúc ở hai đầu tuyến khi cần.
- LoRa không phù hợp gửi gia tốc 6 trục tốc độ cao liên tục. Xử lý phát hiện té ngã tại Node 3, gửi trạng thái/gói gia tốc gọn theo chu kỳ, ưu tiên gói sự kiện và phản hồi lệnh. Tần suất và thời lượng phát phải phù hợp điều kiện sử dụng thực tế.
- Không sử dụng thử trên người khi mạch đo điện cực chưa bảo đảm cách ly và an toàn điện. Đây là bản phục vụ học tập.

## 4. Quy ước Node 1 — MQTT

Các topic:

| Chiều | Topic | Nội dung |
|---|---|---|
| Node → Gateway | `carelink/node1/telemetry` | Dữ liệu cảm biến |
| Gateway → Node | `carelink/node1/command` | Lệnh điều khiển |
| Node → Gateway | `carelink/node1/ack` | Xác nhận đã thực hiện lệnh |

Dùng JSON UTF-8, QoS 1, **retain=false** cho cả dữ liệu tức thời và lệnh.
Gửi ECG theo từng khối (ví dụ 25 mẫu/100 ms khi lấy mẫu 250 Hz), không gửi một bản tin cho mỗi mẫu. Bản tin mẫu dưới đây rút ngắn mảng ECG để dễ đọc:

```json
{"type":"telemetry","node":1,"boot_id":"boot-001","seq":1,"data":{"hr":76,"spo2":98,"rate":250,"measuring":true,"ecg":[0.01,0.03,0.12,0.95,-0.2,0.02]}}
```

`ecg` là mảng mẫu theo thứ tự thời gian. Có thể gửi giá trị ADC; biểu đồ tự điều chỉnh trục trong chế độ thiết bị thật, chưa quy đổi ra mV. Các mẫu được đặt theo tần số và thời điểm nhận, nên chưa phải hệ đo đồng bộ thời gian chính xác. Cần bổ sung dấu thời gian mẫu và xử lý mất gói cho nghiên cứu chuyên sâu.
`hr` đơn vị bpm; `spo2` đơn vị %; `rate` là tần số lấy mẫu **thực tế**. Chỉ gửi phép đo cảm biến hợp lệ; không thay lỗi cảm biến bằng số giả.
`boot_id` thay đổi sau mỗi lần khởi động; `seq` tăng theo bản tin. Gateway loại bản tin trùng trong cửa sổ 512 gói nếu có cả hai trường.

Lệnh:

```json
{"type":"command","id":"unique-command-id","node":1,"action":"set_rate","value":500}
```

Hoặc `action="set_measuring"`, `value=true/false`.
Thiết bị chỉ gửi ACK sau khi đã thực hiện; cần ghi nhớ ID lệnh gần đây để không thực hiện lặp khi MQTT gửi trùng:

```json
{"type":"ack","id":"unique-command-id","ok":true}
```

Nếu thất bại: `{"type":"ack","id":"unique-command-id","ok":false,"error":"Lý do"}`.
Gateway chờ ACK tối đa 6 giây; giao diện chờ tối đa 8 giây. Sau timeout, không tự đổi trạng thái thành thành công.

## 5. Quy ước Node 2 — Modbus RTU

Đây là **bản đồ thanh ghi đề xuất**, không phải thanh ghi mặc định của DHT22. Chương trình ESP32 phải triển khai Modbus slave tương ứng:

- Slave ID: 1; 9600 baud; 8 bit dữ liệu; không parity; 1 stop bit.
- Gateway đọc FC03, start=0, quantity=3, mỗi 3 giây.
- Địa chỉ bên dưới là địa chỉ PDU bắt đầu từ 0.

| Holding register | Kiểu | Giá trị |
|---|---|---|
| 0 | int16 có dấu | Nhiệt độ × 10 (256 = 25,6°C) |
| 1 | uint16 | Độ ẩm × 10 (620 = 62,0%) |
| 2 | uint16 | Relay quạt: 0 tắt, 1 bật |

Ghi quạt bằng FC06 vào register 2. Node phản hồi đúng khung ghi sau khi cập nhật thanh ghi/relay. Gateway kiểm tra độ dài, CRC, địa chỉ, hàm và dữ liệu echo. Phản hồi này xác nhận thao tác điều khiển, không đo được quạt có quay thật hay không.

Nếu firmware hiện tại khác bản đồ thanh ghi, sửa `ModbusNode2.read()` và `ModbusNode2.set_fan()` trong `gateway/gateway.py`.

## 6. Quy ước Node 3 — LoRa và ESP32 nhận

Ra-02 là module SPI; **không thể cắm trực tiếp vào USB máy tính**. ESP32 ở đầu Gateway nhận gói LoRa và chuyển JSON xuống USB Serial 115200 baud. Mỗi JSON kết thúc bằng một ký tự xuống dòng `\n`.

Ví dụ dữ liệu:

```json
{"type":"telemetry","node":3,"boot_id":"wearable-001","seq":10,"data":{"accel":[0.02,-0.03,1.01],"activity":"Đang nghỉ ngơi","fall":false,"battery":86,"rssi":-78,"buzzer":false}}
```

Gia tốc đơn vị g. Pin tính theo %, RSSI theo dBm. Chỉ gửi pin nếu có mạch đo pin và thuật toán quy đổi thực tế.
ESP32 nhận có thể giải mã gói nhị phân ngắn trên LoRa rồi chuẩn hóa thành JSON qua USB. Không bắt buộc truyền nguyên JSON dài trên sóng LoRa.

Gateway gửi ngược xuống USB Serial:

```json
{"type":"command","id":"unique-command-id","node":3,"action":"set_buzzer","value":true}
```

ESP32 nhận chuyển lệnh qua LoRa đến thiết bị đeo. Thiết bị đeo thực hiện, gửi ACK qua LoRa; ESP32 nhận chuyển ACK thành JSON xuống USB. **Không phát ACK thành công ngay sau khi chỉ gửi xong gói LoRa.**
Lệnh `clear_fall` với `value=true` phải xóa cờ té ngã và tắt còi trên thiết bị trước khi ACK. Cấu hình hai bộ LoRa phải tương thích (tần số, băng thông, SF, coding rate, sync word).

## 7. Dữ liệu, cảnh báo và giới hạn

- Cài đặt được lưu trong trình duyệt bằng localStorage.
- Dữ liệu: tối đa 3.600 bản ghi; cảnh báo và nhật ký: tối đa 200 mục mỗi loại trong bộ nhớ. Không có cơ sở dữ liệu bệnh án.
- CSV chứa các bản ghi tổng hợp theo giây, **không bao gồm toàn bộ mẫu ECG**. Muốn lưu ECG thô cần bổ sung bộ lưu ở Gateway.
- Đổi giữa mô phỏng và thiết bị thật giữ các bản ghi đã có trong phiên, có cột nguồn; đồng thời bắt đầu lại danh sách cảnh báo/nhật ký và biểu đồ để tránh trộn trạng thái hiện tại.
- Mất liên lạc được tính từ lần cuối nhận bản tin node, mặc định 15 giây. Node chưa từng gửi dữ liệu hiện “Chưa có dữ liệu”.
- Xác nhận cảnh báo chỉ đánh dấu đã tiếp nhận. Điều kiện bất thường vẫn tồn tại cho đến khi phép đo trở lại ngưỡng hoặc sự cố được xóa sau kiểm tra.
- Tự bật quạt chỉ chạy khi dashboard đang mở và nhận dữ liệu. Chức năng không tự tắt quạt. Khi cần vận hành độc lập, chuyển logic tự động xuống Gateway/ESP32.
- Chưa có thông báo khi đóng trình duyệt, phân quyền nhiều người, lưu trữ lâu dài, vị trí bệnh nhân hay xác định phòng bằng LoRa.
- Ngưỡng ban đầu là ví dụ cho bài tập, chưa được cá thể hóa. Không phải hệ thống chẩn đoán/cảnh báo y tế đã chứng nhận.
- MQTT QoS không bảo đảm dữ liệu luôn liên tục; RS485/LoRa cũng cần đo thử khoảng cách, mất gói và độ trễ tại nơi lắp đặt.

## 8. Kiểm tra phần mềm

Sau khi cài dependencies:

```bash
python -m unittest discover -s gateway -v
```

Kiểm tra CRC Modbus theo vector chuẩn, chặn lệnh sai, đòi hỏi ACK từ thiết bị, truyền dữ liệu WebSocket, loại gói trùng, chặn origin không được phép và báo lỗi khi thiếu adapter. Đây là kiểm tra phần mềm; chưa kiểm tra cảm biến, đường dây, sóng LoRa hay relay thực tế.

## Cấu trúc

- `dist/index.html`, `dist/styles.css`, `dist/app.js`: toàn bộ giao diện, không cần Node.js/npm.
- `gateway/gateway.py`: Gateway Python và các adapter.
- `gateway/requirements.txt`: thư viện Python.
- `gateway/test_gateway.py`: kiểm tra phần mềm.
- `README.md`: hướng dẫn này.

Tài liệu thư viện: https://docs.aiohttp.org/en/stable/web_quickstart.html · https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html · https://pyserial.readthedocs.io/en/latest/pyserial_api.html
