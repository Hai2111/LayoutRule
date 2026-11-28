# Owner working rules for layout agents (read before any layout session)

This file holds what the owner has taught the agent through direct corrections. On the original machine these rules lived in the agent's local memory. They are copied here so that any agent, on any device, starts with them.

Each rule records what the owner said, why, and how to apply it. Rules are **cumulative**: add to them, never delete. Lesson numbers refer to [learn/lessons.jsonl](learn/lessons.jsonl).

## 1. Decide yourself, report once

- **What the owner said:** "quyết định này nên do bạn mới phải" (this decision should be yours); "đừng đưa các quyết định nhỏ lẻ để tôi review, tôi chỉ review kết quả cuối thôi" (don't bring me small piecemeal decisions, I only review the final result); "quyết định nhỏ thì không hỏi nhé" (don't ask about small decisions).
- **Decide alone:** all engineering trade-offs.
  - Equivalent pin and part swaps, such as USBLC6 pass-through pairs and identical pull-ups.
  - MCU GPIO permutations that respect strapping, PSRAM and USB constraints. Record the firmware impact.
  - Via count, layer choice, and moving parts.
- **Still ask:** mechanical anchors and external interfaces (connector position, header pin order), fab capability limits, money, publishing, downloads, and anything irreversible outside the repo.
- **Fix before reporting.** If you know something is suboptimal and can fix it, fix it. Do not list it as a known issue ("tại sao biết chưa tối ưu nhưng không sửa?", why leave it unfixed if you know it's suboptimal?).
- **Final review:** the owner gives one final review, PASS or FAIL (see LayoutRule START_HERE / REVIEW_LEARNING_LOOP).

## 2. Review by relative position, with images

- **What the owner said:** "đừng chỉ tập trung vào số liệu, tập trung vào vị trí tương đối, xử lý hình ảnh đi" (don't focus only on numbers; focus on relative position and work from images).
- **Judge relations, not metrics.** Look at what sits where relative to what, the order along a power or signal path, and what passes between which pads. Numbers matter only for hard limits: fab clearance and width for current.
- **Compare with references.** Render the block under review in the same frame as the same block on reference boards (`tools/ref_block_view.py`, `review2d.py`). References feed **logic** (roles, order, topology) into the process, not numbers.
- **Review independently after every edit round.** Look at close-ups of every region with concrete questions:
  - Does a track run along another part's pin row?
  - Is the trunk straight with short stubs?
  - Is every via forced by fixed pinouts?
- **Fix what you find before reporting.** A passing check means "not yet disproved", not "done".
- **When the owner names a defect,** encode it as a check and as a router cost, then rerun the check on every board.

## 3. Work by blocks, not single spots

- **Start from the references.** Open the reference block images first and compare roles and relative positions.
- **Judge the whole board by blocks** (power, USB, loads).
- **Re-place whole blocks.** If a defect comes from placement, re-place the whole block using real courtyards, re-route the nets of that block, and judge the whole board again. Fixing one spot at a time is rejected as "phiến diện" (one-sided).
- **Reference patterns are starting points, not locks.** For example, CC resistors can move. Small 2-pin parts go through a pose search (`placesmall`, `pack_small.py`).

## 4. Owner routing style

Taken from the owner's own hand edits of the training boards:

- **Differential pairs** (USB D+/D−): run as a coupled pair, parallel and evenly spaced, with symmetric fan-in and fan-out.
- **Same-function groups** (UART, LED, PWM, SPI, I2C): run as evenly spaced buses with aligned 45° bends. Keep the bus in pin order from end to end. Fix crossings with placement or pin permutation, not vias.
- **GND:** solid zone on both layers, never routed (L59). Place dense, purposeful stitching vias near every decap and IC GND pin, in every copper island, between groups, and along edges.
- **Power branches:**
  - Push them out toward the board edge to free space around IC pins, using the project's edge clearance (0.3 mm), not a self-imposed margin.
  - Draw the trunk first, then put the TVS and caps on the trunk (L60).
  - Width must not grow downstream of the source pad (W1).
- **USB-C VBUS:** join the VBUS pins with copper (a zone or a wide bridge), not a thin track.
- **Angles:** only 0, 45 and 90 degrees in drawing, no 90-degree corners in the final board (C90, `chamfer`), and no off-45° segments (A45).
- **Bends:** more bends are fine when they buy symmetry or a clean bus. Low bend count is not a goal.
- **Owner edits are authoritative.** Never overwrite them, but report objective DRC problems they contain.

## 5. Knowledge is cumulative

- **What the owner said:** "mọi thứ phải luôn được bổ sung" (everything must always be added to).
- **How it works:**
  - New sources add lessons and cross-link them to old rule IDs.
  - A lesson's status is upgraded with evidence; it is never rewritten or deleted.
  - Claimed numbers are verified by search (datasheets, standards, vendor guides).
  - New rules are tested on the training boards.

## 6. Existing solutions first

- **What the owner said:** "maybe it is better to find existed solution than solve them again".
- **Search before building.** Read the vendor design guide, reference designs, and the fab's calculator or stackup before writing a solver. A self-written solver is only a cross-check (L77, L78).
- **Example:** Ethernet MDI rules come from the WIZnet HW Design Guide, and the 100 Ω width/gap comes from the JLCPCB impedance calculator for the real stackup.

## 7. Review is a question bank; silkscreen comes last

- **Use the question bank.** Review means running `tools/review_run.py` over `learn/review_questions.json`. The more standard questions, the better the review. Add new questions; never delete any.
- **Silkscreen comes last.** "sau khi pass hết tất cả rule cho route và place thì mới quan tâm tới lớp silkscreen" (only care about silkscreen after every place and route rule passes).

## 8. Process hygiene

- **Junk files.** "sai thì sửa không dừng sẽ tạo ra file rác" (if it's wrong, fix it without stopping; otherwise you create junk files). Undo deletes its step files (`prune`). Saves go through `ksave` (atomic, no stray `.kicad_pro`/`.kicad_prl` files).
- **Interruptions.** "nếu 1 công đoạn nhỏ bị ngắt hãy kiểm tra lỗi và sửa để quy trình trơn chu" (if a small step is interrupted, check what broke and fix it so the process runs smoothly).
  - Run chains through `kpipe.py`.
  - After an interrupt, check for orphan processes, verify the outputs, then rerun (L76).
- **No net-less copper.** In Git Bash, export `MSYS_NO_PATHCONV=1` before passing net names that start with `/` (L80).
