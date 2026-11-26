---
title: "Lộ trình — Khánh (trưởng nhóm)"
member: khanh
course: "OS + CN"
---
# Tổng quan của Khánh

Phần bạn trình bày là **không có**. Đây là trang tổng quan để điều phối nhóm tự học và tự bảo vệ, không phân một phần thuyết trình cho trưởng nhóm.

## Bước 1 — Học chung

| Nhóm | Thứ tự đọc lượt đầu |
|---|---|
| Mạnh, Trường | [1A](../sessions/01-A-cn-product.md) (10′) → [1B](../sessions/01-B-cn-mechanisms.md) (15′) → [1C](../sessions/01-C-cn-demo.md) (5′) → [2A](../sessions/02-A-simevents-theory.md) (10′) → [2B](../sessions/02-B-simevents-model.md) (35′) → [2C](../sessions/02-C-cn-evidence.md) (25′) → [2D](../sessions/02-D-cn-defence.md) (10′) |
| Hiếu, Vinh | CN 1–2 như trên → [3A](../sessions/03-A-linux-theory.md) (15′) → [3B](../sessions/03-B-linux-pipeline.md) (20′) → [3C](../sessions/03-C-linux-evidence.md) (20′) → [4A](../sessions/04-A-rtos-theory.md) (15′) → [4B](../sessions/04-B-stm32-implementation.md) (25′) → [4C](../sessions/04-C-supervisor-evidence.md) (15′) |

Thời lượng là ước lượng lượt đầu; 1C chỉ đọc, demo phần cứng cuối cùng.

## Bước 2 — Phân công

| Người | OS | CN |
|---|---|---|
| [Vinh](vinh.md) | MCU, FreeRTOS, F2/F5 | Inference, AoI, T7 |
| [Hiếu](hieu.md) | Linux, IPC, E1–E4 | RR consumption, AIMD, dashboard |
| [Mạnh](manh.md) | — | Receiver, RR generation, T4 |
| [Trường](truong.md) | — | Sender/channel, T3/T5 |

## Bước 3 — Luyện trình bày

Trang luyện: [Trình bày CN](../defence/cn.md) · [Demo CN](../demo/cn.md) · [Trình bày OS](../defence/os.md) · [Demo OS](../demo/os.md)

**OS:** Vinh → Hiếu. **CN:** Trường → Mạnh → Hiếu → Vinh. Chuyển lời theo roadmap cá nhân; không cần Khánh chen vào. Nắm các mốc chung: F2 ~100 ms sau HB cuối; F5 ~175/475 ms sau INF cuối; T3 5.2%→24%; T7 623→204 ms (MEASURED); Stage B 73.16→87.07% (SIMULATED). Đọc [tổng kết CN](../sessions/02-D-cn-defence.md) và [bằng chứng supervisor](../sessions/04-C-supervisor-evidence.md).

## Checklist tổng quan (không phải phần trình bày)

- [ ] Tôi giải thích được phân công và ranh giới từng người.
- [ ] Tôi giải thích được thứ tự học chung và học sâu.
- [ ] Tôi giải thích được vì sao Mạnh tạo RR, Hiếu tiêu thụ RR.
- [ ] Tôi giải thích được bằng chứng vật lý khác kết quả mô phỏng.
- [ ] Tôi giải thích được thứ tự chuyển lời và fallback replay.
