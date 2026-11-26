---
hide:
  - footer
---

# Demo phần cứng — CN

Sau trang này bạn giải thích được demo CN chứng minh gì, và cách chuyển sang replay nếu phần cứng lỗi.

!!! tip "Nói đơn giản"
    Demo giống chuyến chạy thử. Nếu chuyến hiện tại lỗi, dùng bản ghi cũ nhưng phải nói rõ đó là bản ghi.

!!! warning "Chỉ làm trên bàn thử đã được phép"
    Demo đi sau phần học lý thuyết. Kiểm tra nguồn, mạng và cổng thật trước khi chạy.

## Demo chứng minh gì?

JPEG truyền qua RTP, được ghép đúng hạn, receiver gửi RR, dashboard hiển thị quan sát. Demo ngắn chỉ chứng minh chức năng hiện tại, không thay chiến dịch đo đủ lượt.

## 1. Chuẩn bị chung

- Pi 5, nguồn 5 V/5 A và tản nhiệt; `vcgencmd get_throttled` phải là `0x0` trước demo sạch.
- Ghi commit đang dùng và thời gian chạy.
- Laptop và Pi trên mạng bàn thử riêng; xác định IP và interface thực tế, không sửa mạng đang dùng chung.
- Mỗi lượt có thư mục mới. Kiểm tra log và cổng UDP, không xóa log cũ.
- Chuẩn bị trước bản replay CN; kiểm tra file thực sự có ở máy demo.

## 2. Kiểm thử chức năng nội bộ laptop

Trong môi trường Linux tương thích đã cài Python và deps, từ `R/cn`, chạy `bash rtp/scripts/loopback_demo.sh` với Python venv đúng (script có biến `PYTHON`). Script kiểm tra 150 frame và RR có RTT; không chứng minh mạng vật lý. Windows dùng hướng dẫn 3 terminal PowerShell trong [`dashboard/README.md`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/dashboard/README.md) nếu đã cài venv phù hợp.

## 3. Demo camera Pi → laptop (nếu bench đã sẵn sàng)

- Tắt nguồn trước khi nối camera. Kiểm tra camera v2 và thư viện libcamera trong checkout đầy đủ; source ZIP học không có C++ camera.
- Camera chạy phía Pi và ghi ảnh vào vùng shared memory để sender đọc (giao diện nguồn ảnh). Từ `R/os`, theo [`linux/camera/README.md`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/os/linux/camera/README.md), build và chạy `hea_cam` với `--backend libcamera --width 640 --height 480 --fps 15 --shm hea_camera --output /tmp/hea_cam.sock --csv /tmp/hea_cam.csv`. Dùng socket/ring tên riêng, không xóa ring đang dùng. Xác nhận có `/dev/shm/hea_camera`.
- Laptop: chạy dashboard live (từ `R/dashboard`, `python -m dashboard --mode live`), mở http://127.0.0.1:8080/. Cho phép UDP RTP/RTCP và telemetry cần thiết trên mạng bench.
- Laptop: receiver trước, sender sau. Lệnh POSIX minh họa dựa trên CLI đã đọc; thay `RX_DIR`, `TX_DIR` và `LAPTOP_IP` bằng đường dẫn/IP thật, chưa tồn tại. Không gõ placeholder nguyên văn. Python env phải có dependencies.

Laptop (`R/cn/rtp`):

```bash
PYTHONPATH=rtp python3 -m rtp receiver --bind 0.0.0.0 --port 5004 --duration 85 --playout-ms 50 --rtcp-interval 1 --ai off --out-dir RX_DIR --rtcp-csv receiver_rtcp.csv --telemetry 127.0.0.1 --telemetry-session demo
```

Pi (`R/cn/rtp`):

```bash
PYTHONPATH=rtp python3 -m rtp sender --host LAPTOP_IP --port 5004 --source shm:hea_camera --shm-library ../../os/linux/camera/build/libhea_camera.so --width 640 --height 480 --fps 15 --quality 75 --duration 80 --rtcp-interval 1 --abr fixed --out-dir TX_DIR --rtcp-csv sender_rtcp.csv --telemetry LAPTOP_IP --telemetry-session demo
```

- Xem READY, sender/receiver CSV, frame status, RR và preview (default ≤5 FPS, độc lập FPS truyền). AI off cho smoke. Vinh trình bày T7 từ số liệu lịch sử; nếu bật AI synthetic/ONNX cần lượt riêng đã thử trước.
- Chỉ nếu mạng bench riêng và người quản lý cho phép: kiểm tra qdisc gốc, tạo loss 5% trên interface đã xác nhận theo runbook. Ghi trước/sau, phục hồi cấu hình gốc ngay cả khi lỗi. Không chạy lệnh xóa root qdisc tùy tiện trên mạng chung.
- Dừng sender/receiver, dashboard và camera đúng tiến trình; kiểm tra qdisc và log. Không gọi smoke test là T8 đủ gate. Runner snapshot mới có metadata và scp nhưng template CLI cần xác nhận.

## 4. Khi phần cứng lỗi — nói thật, chuyển nhanh

| Tình huống | Fallback | Câu nói với thầy |
|---|---|---|
| Camera không mở | Synthetic source loopback | “Đường truyền phần mềm vẫn kiểm thử được; đây không phải camera thật.” |
| Mạng LAN không hoạt động | Replay CN recorded sample nếu tồn tại | “Đây là dữ liệu đã ghi trước, không phải live.” |
| Dashboard không mở | CSV, hình Stage B và bảng T7/T4 | “Đây là số liệu nguồn; UI hiện tại chưa chạy.” |

Từ `R/dashboard`, kiểm tra mẫu tồn tại rồi chạy:

```bash
python -m dashboard --mode replay --replay samples/cn-loss5 --loop
```


Mở http://127.0.0.1:8080/, Ctrl+C để dừng. Nếu không có mẫu, dùng hình và bảng đã đóng gói. Không tạo dữ liệu giả để gọi là live.

## Nguồn

[`cn/rtp/scripts/loopback_demo.sh`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/cn/rtp/scripts/loopback_demo.sh), `cn/rtp/rtp/{sender,receiver}.py`, [`dashboard/README.md`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/dashboard/README.md), [`os/linux/camera/README.md`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/os/linux/camera/README.md) (chỉ phần chạy camera). Các lệnh đã đọc từ mã nguồn, chưa thực thi trên bench trong lần soạn này.

## Trắc nghiệm

<div class="quiz" markdown>
<p class="quiz-q">Dây từ AIMD quay lại khối nào?</p>

![Dây từ AIMD quay lại khối nào?](../assets/fig/simevents/CN_simevents_v2.png)

- [ ] Receiver
- [x] Frames
- [ ] Inference
- [ ] Channel

<div class="quiz-why" markdown>
Frames nhận hệ số kích thước. AIMD không thay trực tiếp dữ liệu đã đến receiver.
</div>
</div>

<div class="quiz" markdown>
<p class="quiz-q">Camera lỗi, replay chạy được. Nói gì?</p>

- [ ] Replay là phép đo mới
- [ ] T8 hardware đã pass
- [x] Đây là dữ liệu ghi trước, không phải live
- [ ] Camera chắc chắn đã chạy

<div class="quiz-why" markdown>
Replay minh họa chức năng và dữ liệu đã ghi. Không thay cho test phần cứng.
</div>
</div>

## Câu thầy có thể hỏi

??? question "Nếu không có đủ thiết bị thì demo có giá trị gì?"
    Loopback chứng minh đường phần mềm, replay minh họa dữ liệu đã ghi; không chứng minh bench thật.

??? question "Demo ngắn có thay chiến dịch đo không?"
    Không. Campaign cần cấu hình, lượt lặp và gate.
