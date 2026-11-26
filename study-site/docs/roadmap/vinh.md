---
title: "Lộ trình — Vinh"
member: vinh
course: "OS + CN"
---
# Lộ trình của Vinh

Phần bạn trình bày là STM32 FreeRTOS supervisor của OS và hàng đợi AI/AoI của CN.

## Bước 1 — Học chung

Đọc lượt đầu để biết toàn hệ thống; số phút là **ước lượng**, chưa tính luyện sâu hoặc chạy demo. 1C chỉ đọc hướng dẫn; thực hành sau lý thuyết.

- **CN 1:** [1A](../sessions/01-A-cn-product.md) (10′) → [1B](../sessions/01-B-cn-mechanisms.md) (15′) → [1C](../sessions/01-C-cn-demo.md) (5′).
- **CN 2:** [2A](../sessions/02-A-simevents-theory.md) (10′) → [2B](../sessions/02-B-simevents-model.md) (35′) → [2C](../sessions/02-C-cn-evidence.md) (25′) → [2D](../sessions/02-D-cn-defence.md) (10′).
- **OS 3:** [3A](../sessions/03-A-linux-theory.md) (15′) → [3B](../sessions/03-B-linux-pipeline.md) (20′) → [3C](../sessions/03-C-linux-evidence.md) (20′).
- **OS 4:** [4A](../sessions/04-A-rtos-theory.md) (15′) → [4B](../sessions/04-B-stm32-implementation.md) (25′) → [4C](../sessions/04-C-supervisor-evidence.md) (15′).

## Bước 2 — Phần của bạn

- **OS:** [4A A1–A6](../sessions/04-A-rtos-theory.md), [4B B1–B10](../sessions/04-B-stm32-implementation.md), [4C C1–C7](../sessions/04-C-supervisor-evidence.md). Đọc `stateflow_chart.png`, `stale_result_failsafe_rearm_timeline.png`, `10_f5_measured.png`. Hiếu tạo HB/INF; bạn giải thích accept và quyết định state.
- **CN:** [2B B4, B9](../sessions/02-B-simevents-model.md), [2C C6, C8](../sessions/02-C-cn-evidence.md). Đọc `CN_simevents_v2__Inference.png`, `07_fifo_latest.png`.

## Bước 3 — Luyện trình bày

Trang luyện: [Trình bày CN](../defence/cn.md) · [Demo CN](../demo/cn.md) · [Trình bày OS](../defence/os.md) · [Demo OS](../demo/os.md)

- OS: 3 task, tick 1 kHz và timer µs; nhận UART bằng DMA, kiểm tra CRC và accept trước khi đánh giá (SOURCE).
- OS: HB timeout 100 ms, source age HOLD 200 ms, FAILSAFE 500 ms (SOURCE). F2 local FAILSAFE P50 100.577 ms từ HB cuối; F5 HOLD/FAILSAFE P50 175.596/475.596 ms từ INF cuối (MEASURED).
- OS: phân biệt re-arm logic và reset; capture logic analyser chưa xác minh vật lý.
- CN: T7 mean AoI 623→204 ms, queue wait P50 440.20→16.48 ms, throughput 17.63→17.52/s (MEASURED synthetic workload).

**Chuyển lời:** OS: “MCU chỉ kiểm tra dữ liệu đã đến; Hiếu sẽ giải thích cách Linux tạo, xếp hàng và gửi những dữ liệu đó.” CN (kết thúc): “Latest-value giữ kết quả mới hơn mà gần như không đổi throughput; đó là cải tiến freshness đã đo của nhóm.”

## Checklist

- [ ] Tôi giải thích được hai đồng hồ và vai trò DMA.
- [ ] Tôi giải thích được frame v3 và các accept check.
- [ ] Tôi giải thích được bốn state và các ngưỡng.
- [ ] Tôi giải thích được F2 khác F5 và mốc thời gian đo.
- [ ] Tôi giải thích được re-arm khác reset.
- [ ] Tôi giải thích được AoI khác latency.
- [ ] Tôi giải thích được T7 và giới hạn synthetic workload.
