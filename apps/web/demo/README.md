# Backup demonstration and recording

**Video status: NOT RECORDED.** ffmpeg is installed, but browser validation/recording was interrupted by the user's physical Escape key. No screenshot sequence, synthetic animation, unit test or HTTP response is being presented as a real end-to-end recording.

## Preparation

1. Use `NODETRAIL_DATA_MODE=mock`, run `pnpm build` and `pnpm start` from apps/web. Keep the sample-data badge visible throughout. This is a Python fixture demonstration, not research on an unseen topic.
2. Open `http://localhost:3000`. Close unrelated browser tabs, notifications and windows before recording. Use a dedicated browser window. Do not display environment files or credentials.
3. Open `demo/sample-syllabus.html` manually and print/save it as `sample-syllabus.pdf`. The HTML is a source fixture, **not** a delivered PDF. The form accepts PDF/DOCX, not HTML. Alternatively use a non-sensitive PDF/DOCX under the local mock cap of 10 MiB. Mock upload simulates receipt and does not parse it.
4. Complete the manual acceptance checklist in `docs/verification.md` on desktop and 390px mobile before recording. If a check fails, fix/retest before presenting the recording as the backup.

## Suggested two-minute script

| Time     | On-screen action                                                             | Narration in Vietnamese                                                                        |
| -------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| 0–12s    | Overview; point to sample-data badge                                         | “Đây là bản demo frontend, dùng dữ liệu Python có sẵn.”                                        |
| 12–30s   | New topic, enter a goal, attach sample PDF, show local simulated receipt     | “Người học nêu mục tiêu hoặc gửi đề cương. Ở bản mock, tệp chưa được đọc.”                     |
| 30–44s   | Quick mode; submit; show research trail and sample source                    | “Các bước này đang mô phỏng; khi nối API, trạng thái sẽ đến từ máy chủ.”                       |
| 44–60s   | Open map; zoom/pan/fit; select Boolean expressions                           | “Bản đồ thể hiện quan hệ tiên quyết và mức nắm vững.”                                          |
| 60–75s   | Open Why panel; show supplied trace; open citation                           | “Bảng Vì sao trình bày lý do, bằng chứng và các lựa chọn. Nguồn có thể mở để kiểm tra.”        |
| 75–100s  | Open lesson; wrong answer; show remediation; request a hint; retry correctly | “Sena gợi mở cách suy nghĩ. Phản hồi và mức nắm vững ở đây là dữ liệu minh họa.”               |
| 100–110s | Review screen; return to lesson to show preserved context                    | “Ngữ cảnh được giữ khi chuyển màn hình. Lịch này là minh họa trong phiên.”                     |
| 110–120s | Free → Pro dialog; show demo/no-payment notice; deep mode option             | “Free dùng Nhanh. Pro có Nghiên cứu sâu. Bản demo không thu phí và không xác nhận quyền thật.” |

## Window-only recorder

From a terminal separate from the demo window, run the existing ffmpeg wrapper with the exact observed Chrome window title:

```powershell
.\demo\record-window.ps1 -WindowTitle '<exact demo browser window title>' -Seconds 120
```

The wrapper records only that window, no audio, into `demo/NodeTrail-demo.mp4`. It refuses to overwrite an existing recording. Capture narration separately if needed. It has been prepared but **not run**. If gdigrab/window capture is unavailable on the machine, use the user's recording tool and the same script.

After capture, play the entire file, check legibility, badge visibility, transitions and absence of unrelated content. Check duration/video stream with `ffprobe demo/NodeTrail-demo.mp4`. A successful command exit alone does not establish demo acceptance.
