---
title: "Khi thầy hỏi ngoài phần mình"
course: "OS + CN"
member: "Tất cả thành viên"
prerequisites: []
---

# Khi thầy hỏi ngoài phần mình

Sau bài này bạn giải thích được trả lời ngắn và chuyển đúng người mà không né câu hỏi.

![Minh họa Khi thầy hỏi ngoài phần mình](../assets/img/defence_questions.webp){ .figure-right loading=lazy }

## Ý tưởng

Mọi người có thể giải thích đường đi cơ bản. Nếu hỏi sâu, nêu giới hạn phần mình và chuyển đúng chủ giao diện.

!!! tip "Nói đơn giản"
    Tiếp sức: biết ai đưa gậy cho mình và đưa tiếp cho ai. Không cần chạy thay mọi người.

## Lý thuyết

Cách trả lời: (a) nhắc vị trí khối, (b) nêu đầu vào/đầu ra, (c) giải thích một cơ chế, (d) phân biệt SOURCE/SIMULATED/MEASURED/CALCULATED, (e) chuyển người phụ trách nếu cần.

Ví dụ CN: RTP đi từ sender tới receiver; RR đi ngược, không chứa ảnh. Trường tạo RTP; Mạnh tạo RR; Hiếu dùng RR; Vinh xử lý ảnh ok. OS: Hiếu tạo HB và age-at-send; Vinh kiểm tra MCU. **MEASURED:** F5 cho thấy HB còn mới nhưng tuổi nguồn gây HOLD. Không nói mọi đội cần học OS; Mạnh/Trường chỉ cần phần CN.

## Mô phỏng và đo đạc

![CN_simevents_v2](../assets/fig/simevents/CN_simevents_v2.png){ loading=lazy }

!!! note "Cách đọc hình — SOURCE — sơ đồ mô hình"
    Hàng trên đi từ Frames đến Inference. Hàng giữa trả RR về sender. Dây dưới nối AIMD với Frames. Không có trục thời gian trong sơ đồ.

![Hinh_3_1_System_architecture](../assets/fig/os_report/Hinh_3_1_System_architecture.png){ loading=lazy }

!!! note "Cách đọc hình — SOURCE — sơ đồ báo cáo"
    Đọc từ Pi workload/bridge qua UART INFERENCE và HEARTBEAT đến RX, supervisor, output/LED. Đường đứt đỏ là biên quyền điều khiển.

![10_f5_measured](../assets/fig/plots/10_f5_measured.png){ loading=lazy }

!!! note "Cách đọc hình — MEASURED"
    Trái: từng lượt F5, y thời gian từ inference cuối đến HOLD/FAILSAFE (ms). Phải: tuổi HB lúc HOLD, thấp hơn vạch ngưỡng HB.

## Bằng chứng trong mã

**SOURCE:** sơ đồ kiến trúc và các track thành viên.

## Trắc nghiệm

<div class="quiz" markdown>
<p class="quiz-q">Dây từ AIMD quay lại khối nào?</p>

![Dây từ AIMD quay lại khối nào?](../assets/fig/simevents/CN_simevents_v2.png)

- [x] Frames
- [ ] Inference
- [ ] Channel
- [ ] Receiver

<div class="quiz-why" markdown>
Frames nhận hệ số kích thước. AIMD không thay trực tiếp dữ liệu đã đến receiver.
</div>
</div>

<div class="quiz" markdown>
<p class="quiz-q">Ai có quyền quyết định trạng thái output?</p>

![Ai có quyền quyết định trạng thái output?](../assets/fig/os_report/Hinh_3_1_System_architecture.png)

- [ ] Bridge Linux
- [x] Supervisor bên STM32
- [ ] ONNX Runtime
- [ ] Camera

<div class="quiz-why" markdown>
Pi tạo thông tin; MCU đánh giá độc lập. Sơ đồ không chứng minh chứng nhận an toàn.
</div>
</div>

<div class="quiz" markdown>
<p class="quiz-q">Không nhớ số chính xác trong báo cáo: nói gì?</p>

- [ ] Nói mọi số giống model
- [ ] Đổi chủ đề
- [x] Nêu cơ chế, xin đối chiếu đúng bảng nguồn
- [ ] Bịa số gần đúng

<div class="quiz-why" markdown>
Không cần đoán. Câu trả lời có căn cứ tốt hơn một số sai.
</div>
</div>

## Câu thầy có thể hỏi

??? question "RR tạo ở đâu?"
    Receiver; sender dùng RR.

??? question "Ai nói về E3 real?"
    Hiếu nói gate và Linux; Vinh nói state MCU.
