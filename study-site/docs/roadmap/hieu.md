---
title: "Lộ trình — Hiếu"
member: hieu
course: "OS + CN"
---
# Lộ trình của Hiếu

Phần bạn trình bày là Linux pipeline của OS và vòng điều khiển AIMD/dashboard của CN.

## Bước 1 — Học chung

Đọc lượt đầu để biết toàn hệ thống; số phút là **ước lượng**, chưa tính luyện sâu hoặc chạy demo. 1C chỉ đọc hướng dẫn; thực hành sau lý thuyết.

- **CN 1:** [1A](../sessions/01-A-cn-product.md) (10′) → [1B](../sessions/01-B-cn-mechanisms.md) (15′) → [1C](../sessions/01-C-cn-demo.md) (5′).
- **CN 2:** [2A](../sessions/02-A-simevents-theory.md) (10′) → [2B](../sessions/02-B-simevents-model.md) (35′) → [2C](../sessions/02-C-cn-evidence.md) (25′) → [2D](../sessions/02-D-cn-defence.md) (10′).
- **OS 3:** [3A](../sessions/03-A-linux-theory.md) (15′) → [3B](../sessions/03-B-linux-pipeline.md) (20′) → [3C](../sessions/03-C-linux-evidence.md) (20′).
- **OS 4:** [4A](../sessions/04-A-rtos-theory.md) (15′) → [4B](../sessions/04-B-stm32-implementation.md) (25′) → [4C](../sessions/04-C-supervisor-evidence.md) (15′).

## Bước 2 — Phần của bạn

- **OS:** [3A A2–A6](../sessions/03-A-linux-theory.md), [3B B1–B8](../sessions/03-B-linux-pipeline.md), [3C C2–C9](../sessions/03-C-linux-evidence.md). Đọc `08_contention_summary.png`, `08_service_histogram.png`, `09_input_policy_aoi.png`, `os_t3_p0_p1.png` và `os_t4_fifo_latest.png`. Nắm E1–E4, bridge/input queue và quy tắc loại run.
- **CN:** [2B B3, B10–B11](../sessions/02-B-simevents-model.md), [2C C1–C2, C5.1](../sessions/02-C-cn-evidence.md). Đọc `CN_simevents_v2__AIMD.png`, `Stage_B_Dashboard.png`, `04_rtcp_loss.png`, `06_quality_bitrate.png`. Mạnh tạo RR; bạn nhận và điều khiển.

## Bước 3 — Luyện trình bày

- OS: camera → inference → bridge; heartbeat và age-at-send do Linux tạo, MCU kiểm tra độc lập.
- OS: E3 memrate chỉ đổi bridge không giải quyết backlog; 6660→6958 ms mean AoI (MEASURED PTY theo v1, FLAGGED theo v2). OS-T4 đổi input 192→92.8 ms idle; 334.7→223.5 ms memrate (MEASURED PTY, 3 repeat).
- CN: Stateflow loss >2% giảm scale ×0.8; Python dùng ngưỡng >5%, quality/resolution (SOURCE).
- CN: Stage B on-time 73.16→87.07%, AoI 147.70→111.87 ms (SIMULATED). T8 hardware chưa xác nhận.

**Chuyển lời:** OS (sau Vinh, kết thúc): “Tóm lại, Linux quyết định dữ liệu nào được gửi; MCU quyết định dữ liệu còn đủ mới hay không.” CN: “Khi frame đã đến đúng hạn, Vinh sẽ giải thích cách chọn frame mới nhất cho AI.”

## Checklist

- [ ] Tôi giải thích được ba tiến trình và hai hàng đợi.
- [ ] Tôi giải thích được age-at-send khác heartbeat.
- [ ] Tôi giải thích được vì sao E3 không cải thiện và run nào bị loại.
- [ ] Tôi giải thích được sự khác nhau giữa luật AIMD Python và Stateflow.
- [ ] Tôi giải thích được trace rate và dashboard Stage B.
- [ ] Tôi giải thích được ranh giới giữa simulation và đo thật.
