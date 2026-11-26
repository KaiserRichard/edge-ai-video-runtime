---
title: "Lộ trình — Mạnh"
member: manh
course: "CN"
---
# Lộ trình của Mạnh

Phần bạn trình bày là receiver, jitter, playout, ghép ảnh và tạo RTCP RR.

## Bước 1 — Học chung

Đọc lượt đầu để biết toàn hệ thống; số phút là **ước lượng**, chưa tính luyện sâu hoặc chạy demo. 1C chỉ đọc hướng dẫn; thực hành sau lý thuyết.

- **CN 1:** [1A](../sessions/01-A-cn-product.md) (10′) → [1B](../sessions/01-B-cn-mechanisms.md) (15′) → [1C](../sessions/01-C-cn-demo.md) (5′).
- **CN 2:** [2A](../sessions/02-A-simevents-theory.md) (10′) → [2B](../sessions/02-B-simevents-model.md) (35′) → [2C](../sessions/02-C-cn-evidence.md) (25′) → [2D](../sessions/02-D-cn-defence.md) (10′).

## Bước 2 — Phần của bạn

[1B B2–B4](../sessions/01-B-cn-mechanisms.md) → [2B B8, B10](../sessions/02-B-simevents-model.md) → [2C C4](../sessions/02-C-cn-evidence.md). Đọc `CN_simevents_v2__Receiver.png`, `__Receiver__RFC_3550_jitter.png`, `__Receiver__Playout_deadline.png`, `__Receiver__Fragment_counter.png`, `02_jitter_time.png`, `03_playout_tradeoff.png`, `04_rtcp_loss.png`. Bạn tạo RR; Hiếu tiêu thụ RR.

## Bước 3 — Luyện trình bày

- Receiver nhận các mảnh, sequence nhận diện packet, timestamp đặt lịch media; marker không bảo đảm đủ mảnh.
- Jitter RFC 3550 là bộ lọc 1/16 (SOURCE); deadline dựa vào anchor + hiệu timestamp/90000 + depth.
- T4 depth 20→50→100 ms: late 93.5→14.3→0%, P50 37.91→75.32→117.68 ms (MEASURED).
- RR báo loss trong kỳ và jitter; phân biệt frame lost với late.

**Chuyển lời:** “Receiver vừa tạo RTCP RR từ những gì đã nhận; Hiếu sẽ giải thích sender dùng báo cáo đó để thích nghi như thế nào.”

## Checklist

- [ ] Tôi giải thích được sequence khác timestamp.
- [ ] Tôi giải thích được jitter khác delay.
- [ ] Tôi giải thích được deadline không bám từng arrival.
- [ ] Tôi giải thích được complete khác on-time.
- [ ] Tôi giải thích được T4 trade-off.
- [ ] Tôi giải thích được RR được tạo từ thống kê tiếp nhận.
