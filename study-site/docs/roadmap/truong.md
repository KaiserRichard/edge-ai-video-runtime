---
title: "Lộ trình — Trường"
member: truong
course: "CN"
---
# Lộ trình của Trường

Phần bạn trình bày là nguồn ảnh, RTP sender, serialization, channel và netem.

## Bước 1 — Học chung

Đọc lượt đầu để biết toàn hệ thống; số phút là **ước lượng**, chưa tính luyện sâu hoặc chạy demo. 1C chỉ đọc hướng dẫn; thực hành sau lý thuyết.

- **CN 1:** [1A](../sessions/01-A-cn-product.md) (10′) → [1B](../sessions/01-B-cn-mechanisms.md) (15′) → [1C](../sessions/01-C-cn-demo.md) (5′).
- **CN 2:** [2A](../sessions/02-A-simevents-theory.md) (10′) → [2B](../sessions/02-B-simevents-model.md) (35′) → [2C](../sessions/02-C-cn-evidence.md) (25′) → [2D](../sessions/02-D-cn-defence.md) (10′).

## Bước 2 — Phần của bạn

[1A A1–A3](../sessions/01-A-cn-product.md) → [1B B1–B2](../sessions/01-B-cn-mechanisms.md) → [2B B3–B7](../sessions/02-B-simevents-model.md) → [2C C3, C5](../sessions/02-C-cn-evidence.md). Đọc `CN_simevents_v2__Frames.png`, `CN_simevents_v2__RTP_Packetizer.png`, `__Serialization.png`, `__Channel.png`, `01_rtp_metadata.png`, `05_netem_frame_loss.png`, `06_quality_bitrate.png`.

## Bước 3 — Luyện trình bày

- Nguồn synthetic/JPEG/camera dùng chung giao diện; 15 FPS → 66.67 ms (SOURCE/CALCULATED).
- Sequence modulo 65536, media clock 90 kHz; payload custom PT 96. Phân biệt 1200 B trong Python và SimEvents (SOURCE).
- T3 loss 5.2% → frame loss 24%; GE 5.3% → 8.8% (MEASURED).
- T5 payload 500/1200/1400/3000 B cho frame loss 21.2/9.8/9.7/10.7% (MEASURED); giải thích MTU.

**Chuyển lời:** “Các packet đã qua kênh có loss và delay. Mạnh sẽ giải thích cách receiver ghép ảnh và quyết định ảnh có đúng hạn hay không.”

## Checklist

- [ ] Tôi giải thích được nguồn thật và giả lập.
- [ ] Tôi giải thích được header RTP và marker.
- [ ] Tôi giải thích được kích thước payload Python khác mô hình.
- [ ] Tôi giải thích được serialization khác propagation.
- [ ] Tôi giải thích được loss độc lập khác GE burst.
- [ ] Tôi giải thích được T3 và T5.
