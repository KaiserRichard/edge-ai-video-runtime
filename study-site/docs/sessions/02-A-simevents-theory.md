---
title: "Session 2 — A. Nền tảng SimEvents"
course: CN
session: 2
part: A
---
# Session 2 — A. Nền tảng SimEvents

Sau phần này, bạn phân biệt được sản phẩm thật với mô hình toán học, đọc được entity, event và signal trong SimEvents, và biết vì sao nhóm chuyển sang phiên bản v2.

**Quy ước bằng chứng:** SOURCE = cấu hình hoặc mã đã đọc; MEASURED = kết quả đo được báo cáo; SIMULATED = kết quả mô phỏng đã lưu; CALCULATED = tính từ dữ liệu đã nêu. Ví dụ minh họa không phải lần chạy mới. FLAGGED/UNKNOWN = chưa đủ điều kiện xác nhận. P50 là trung vị; P95 là phân vị 95%.

## A1. Vì sao cần SimEvents khi đã có sản phẩm thật?

Sản phẩm thật: camera tạo JPEG, Pi packetize và gửi UDP, laptop nhận, ghép, phát theo lịch rồi xử lý AI. Báo cáo RTCP quay lại Pi. Các phép đo trên thiết bị cho biết hệ thống hoạt động trong điều kiện thử, nhưng khó tách riêng ảnh hưởng của từng cơ chế.

Mô phỏng: generator tạo entity chứa kích thước và thời điểm sinh; channel đặt luật mất gói và delay; consumer có service time; AIMD điều khiển kích thước. Ta có thể thay một thông số, giữ các điều kiện khác và lặp với seed xác định.

| Sản phẩm thật | SimEvents |
|---|---|
| JPEG có pixel thực | Kích thước, ID và thời gian |
| UDP socket thực | Dây entity |
| Ethernet hoặc Wi-Fi | Channel có luật delay/loss |
| ONNX hoặc workload giả lập | Service time cấu hình |
| Tải OS biến thiên | Tham số và random seed |

![Native SimEvents v2: mô hình toàn hệ thống](../assets/fig/simevents/CN_simevents_v2.png)

Đọc vùng xanh của đường RTP, vùng vàng của đường RTCP, vùng tím của điều khiển/quan sát. Đây là mô hình của các cơ chế liên quan đến CN, không chứa ảnh thật. Nó không đo chất lượng JPEG, độ chính xác phân loại hay thời gian thực thi thực của một mạng neural.

!!! tip "Nói đơn giản"
    Để nghiên cứu tắc đường, ta cần thời điểm xe vào đường, kích thước và tốc độ xe, không nhất thiết cần biết từng người ngồi trên xe. Tương tự, nghiên cứu truyền ảnh có thể dùng số byte, ID và timestamp thay vì pixel.

## A2. Simulink và Discrete-Event Simulation

Simulink thường diễn tả tín hiệu thay đổi theo thời gian, ví dụ góc pitch \(\theta(t)\). SimEvents mô tả sự kiện rời rạc (discrete events): packet được tạo, đến receiver, server hoàn thành việc xử lý. Thời gian mô phỏng vẫn liên tục; các sự kiện xảy ra ở những thời điểm cụ thể, không bắt buộc cùng khoảng cách.

- **Entity (thực thể):** đối tượng riêng biệt như frame, packet hay RR.
- **Event (sự kiện):** thay đổi xảy ra tại một thời điểm, như packet đến queue.
- **Attribute (thuộc tính):** thông tin gắn với entity, như `seq`, `capture`, `size`.

Ví dụ một packet trong frame 1 có sequence 0, fragment 1, count 6, size 1200 B và RTP timestamp 0 (ví dụ minh họa theo quy ước của mô hình). Packet đi qua serializer, channel rồi receiver. Các khối có thể đổi attribute, giữ lại hoặc loại bỏ entity.

## A3. Bảy building blocks (khối cơ bản)

![Generator/replicator/server trong kiến trúc packetizer](../assets/fig/simevents/CN_simevents_v2__RTP_Packetizer.png)

| Khối native | Vai trò |
|---|---|
| Entity Generator | Sinh entity theo lịch |
| Entity Queue | Giữ entity đang chờ |
| Entity Server | Giữ/xử lý entity trong service time |
| Entity Replicator | Nhân entity thành các bản sao |
| Entity Output Switch | Chọn đường đi theo thuộc tính |
| Entity Terminator | Kết thúc vòng đời entity |
| Entity Transport Delay | Mô phỏng thời gian di chuyển |

Đọc Packetizer: `Count fragments` tính số bản sao, `Make N copies` tạo các bản sao, `Stamp RTP header` gán thuộc tính từng mảnh. Server không nhất thiết là máy chủ mạng. Nó có thể đại diện link truyền, bộ xử lý AI hoặc thời gian giữ trong playout buffer.

Entity wire mang từng đối tượng. Signal wire mang giá trị số như scale AIMD. Hai loại dây phối hợp tạo mô hình lai (hybrid simulation) giữa event và điều khiển lấy mẫu.

## A4. Tại sao chuyển từ v1 sang v2?

SOURCE: [`sim/study_simevents_v2/SIMEVENTS_V2_REPORT.md`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/sim/study_simevents_v2/SIMEVENTS_V2_REPORT.md), [`build_cn_simevents_v2.m`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/sim/study_simevents_v2/build_cn_simevents_v2.m). v1 sử dụng MATLAB Discrete-Event System `CNSEStage`; nhiều cơ chế nằm trong code. v2 thay các khối đó bằng khối native. Packetizer tách count/replicate/stamp; channel tách loss/delay; receiver tách jitter, deadline, counter. v2 vẫn cần event action và helper cho RNG, RR, trace. Nó không phải mô hình không có code.

## A5. Cầu nối Data Communications — Gilbert–Elliott và RL

Mất độc lập giống kênh có lỗi không nhớ quá khứ. Gilbert–Elliott là chuỗi Markov hai trạng thái. Trong cấu hình T3 thực tế, trạng thái Good không mất packet, Bad mất tất cả; xác suất chuyển G→B là 1.316%, B→G là 25% (SOURCE từ qdisc báo cáo).

```mermaid
stateDiagram-v2
 G: Good - packet sống
 B: Bad - packet mất
 G --> B: p
 B --> G: r
 G --> G: 1-p
 B --> B: 1-r
```

\[
P_B=\frac{p}{p+r}\approx 0.05,\qquad E[L_B]=1/r=4\text{ packet}.
\]

CALCULATED: loss trung bình khoảng 5%, burst trung bình 4 packet. Vì thế `ge5_b4`. Đây mới là Markov chain mô tả môi trường; chưa có agent, action hay reward nên không phải bài toán RL. Sender chỉ quan sát một phần qua RR. AIMD là luật điều khiển xác định, không phải RL.

Config YAML cũ khác actual qdisc trong [`hw_tables.md`](https://github.com/KaiserRichard/edge-ai-video-runtime/blob/main/cn/rtp/report/hw_tables.md); khi giải thích số đo, dùng cấu hình thực đã báo cáo.

## A. Trắc nghiệm cuối phần

<div class="quiz" markdown>
<p class="quiz-q">Tại sao entity không cần pixel ảnh?</p>

- [ ] Vì mô hình đánh giá chất lượng JPEG trực tiếp
- [x] Vì nghiên cứu loss/timing chỉ cần ID, byte và timestamp
- [ ] Vì RTP không truyền ảnh
- [ ] Vì packet có cùng kích thước

<div class="quiz-why" markdown>
Các thuộc tính đủ cho cơ chế mạng đã mô hình hóa, không đủ cho đánh giá chất lượng hình ảnh.
</div>
</div>

<div class="quiz" markdown>
<p class="quiz-q">Khối nào tạo nhiều packet entity từ một frame?</p>

- [x] Entity Replicator
- [ ] Entity Terminator
- [ ] Unit Delay
- [ ] Scope

<div class="quiz-why" markdown>
Replicator tạo số bản sao theo count đã tính.
</div>
</div>

<div class="quiz" markdown>
<p class="quiz-q">Tại sao v2 vẫn có code?</p>

- [ ] Không còn block native
- [x] Mã hỗ trợ attribute, RNG, RR và trace
- [ ] Vì nó là ONNX
- [ ] Vì mất khả năng mô phỏng event

<div class="quiz-why" markdown>
Native blocks làm rõ cơ chế; helper vẫn cần cho một số thao tác.
</div>
</div>
