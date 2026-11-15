# TECHNICAL SOURCE REGISTER — standards, application notes, articles & CAD workflow

**Reviewed:** 2026-11-15. This register records **publisher-specific statements**, a proposed PCB decision, and evidence class. It is *not* a replacement for paid standards or product-specific guidelines. No full copyrighted standards text is mirrored.

## Evidence / source hierarchy
1. **Mandatory project constraints and safety regulations**, fabrication/assembly limits, validated device requirements, current project schematic. Safety standards require exact edition, working voltage, pollution degree, materials and environment.
2. **Device-specific official datasheet/layout guide** for *exact* MPN/package/revision (vendor may revise guidance).
3. **Official application notes and measured reference evaluations** with matching topology/stackup conditions.
4. **General scholarly/technical articles** and engineering conference papers.
5. **Reviewed source CAD** with pinned commit, net-to-pad map and manufacturability evidence.
6. **Video review** with time-stamped specific observed design examples.
7. **Unverified heuristics**: warnings only. A source's authority does not make every inference applicable to other topologies.

## Source index (13 primary documents)

| ID | Type | Source and verified scope | Evidence status | Rules / applicable claims |
|---|---|---|---|---|
| TS01 | Official CAD docs | [KiCad 9.0 PCB Editor — design rules, zones, DRC](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) | **HTML_READ** | DRC checks implemented constraints/netlist parity; re-fill zones before DRC; custom `.kicad_dru` rules support `condition` / `constraint` clauses and priority ordering. **Not** an electrical SI/EMI test. A02, R01, G02, G05, G07. |
| TS02 | Vendor app note | [TI AN-1229 SNVA054C — SIMPLE SWITCHER buck layout](https://www.ti.com/lit/an/snva054c/snva054c.pdf) | **PDF_SCREENSHOT_INSPECTED** (p.3, Figure 1; text §2/§3) | Identify rapidly changing current paths; input bypass and catch diode placement, feedback isolation; enlarging SW copper indiscriminately can increase EMI. Valid for its described buck families/topology; modern synchronous bucks use different switch geometry. P03, R03, G02. |
| TS03 | Vendor app note | [TI SLLA414A — High-Speed Layout Guidelines for Signal Conditioners and USB Hubs](https://www.ti.com/lit/an/slla414a/slla414a.pdf) (Jan 2026 revision) | **PDF_SCREENSHOT_INSPECTED** (p.7/figure 3-4/3-5; text sections 2–4) | Prioritize critical pairs early; high-frequency return path is disrupted by reference-plane splits; near transitions provide appropriate return transfer. USB2 device-specific example: 90Ω±15% differential in this document; **do not transfer this tolerance blindly** to a different PHY, stackup or interface. R02,R05,R07. |
| TS04 | Vendor technical article | [ADI AN-1142 — Techniques for High Speed ADC PCB Layout](https://www.analog.com/en/resources/app-notes/an-1142.html) | **HTML_READ** (EPAD, decoupling sections) | EPAD ground/thermal connection and solder-paste segmentation are assembly-sensitive; select PDN components and place bypass by low impedance path, not “more capacitors always better”. P04,P09,G04. |
| TS05 | Vendor technical article | [ADI Short Course in PCB Layout for High-Speed ADCs](https://www.analog.com/en/resources/technical-articles/a-short-course-in-pcb-layout-for-high-speed-adcs.html) | **HTML_READ** | Keep high-speed analog reference planes continuous; symmetric analog diff input loading; avoid arbitrary shared vias when aggressor currents couple; ground return at layer transitions. Primarily **high-speed ADC** context: 50-mil ground-via guideline in original is **not a universal stitching-via pitch**. R05,R07,R10,G03. |
| TS06 | Vendor technical article | [ADI Practical Guide to High-Speed PCB Layout](https://www.analog.com/en/resources/analog-dialogue/articles/high-speed-printed-circuit-board-layout.html) | **HTML_READ** | Provide layout person with functional signal flow, placement constraints, stackup, critical net descriptions, clearances and review checkpoints **before** route. Broken GND under fast signals increases stray inductance. A03,P02,G07. |
| TS07 | Vendor technical article | [ADI Mixed-Signal PCB Layout Basics](https://www.analog.com/en/resources/analog-dialogue/articles/what-are-the-basic-guidelines-for-layout-design-of-mixed-signal-pcbs.html) | **HTML_READ** (placement, analog/digital, supply, decoupling) | Floorplan by schematic signal path, isolate noisy and sensitive regions, manage return current, do not presume every analog/digital IC requires a split GND plane. P02,P08,G01. |
| TS08 | Vendor technical article | [ADI Designing Power Supplies for High-Speed ADC](https://www.analog.com/en/resources/technical-articles/power-supplies-high-speed-adc.html) | **HTML_READ** | Consider switching-supply noise transfer, ferrite entry filtering where designed, adequate GND reference and data/clock return segmentation for ADC. P08,R05. |
| TS09 | Vendor USB app note | [Microchip AN26.2 — USB 2.0/3.x Hub Implementation](https://ww1.microchip.com/downloads/en/Appnotes/AN26.2-Application-Note-DS00001876C.pdf) | **PDF_METADATA_AND_SEARCH_TEXT_ONLY** | A source for exact USB-hub routing/stackup design constraints; **not yet visually reviewed**; do not use it to certify an arbitrary native-FS USB MCU. R07,A03. |
| TS10 | Vendor USB app note | [Microchip AN22.3 — USB334x Transceiver Layout](https://www.microchip.com/en-us/application-notes/an223) | **OFFICIAL_PRODUCT_PAGE_READ** | USB 2.0 HS PHY needs SI-aware placement/routing; QFN pin escape/device bypass is package-dependent. R07,P09. |
| TS11 | Manufacturer standard | [IPC-2152 — Current Carrying Capacity in Printed Board Design, contents/sample](https://www.ipc.org/TOC/IPC-2152.pdf) | **PDF_SCREENSHOT_INSPECTED** (cover and contents, no full standard validation) | Proper trace sizing uses current **and allowed conductor temperature rise** plus copper/layer/enclosure conditions; never derive all currents from one fixed width. R04,G04. Avoid claiming a particular width/amp value from an unread copy. |
| TS12 | Manufacturer standard | [IPC-7351 — SMT Land Pattern, contents/sample](https://www.ipc.org/TOC/IPC-7351.pdf) | **PDF_SCREENSHOT_INSPECTED** (cover and contents, no full standard validation) | Land pattern/pad tolerancing, component courtyard/spacing, SMT assembly and rework matter beyond DRC clearance. P09,P11,G05; exact footprint geometry needs current standard/datasheet/fab. |
| TS13 | Vendor USB product note | [TI TS3USB30 datasheet (Rev. F), layout section](https://www.ti.com/lit/ds/scds237f/scds237f.pdf) | **PDF_METADATA_AND_SEARCH_TEXT_ONLY** | Example of vendor-specified matched D+/D− pair, minimize corners/vias, bypass placement offset from D pairs; cannot generalize numeric length threshold without reading actual current datasheet and interface. R07,P04. |

## Source-derived conclusions (not universal CAD geometry constraints)

**SC01: Edge speed changes priority.** Critical route planning is conditioned on interface bandwidth/risetime and EMI margin, not only bit-rate or clock frequency. TS03/TS05/TS06.

**SC02: Switching regulator is topology-based, not nearest-centroid-based.** Source → CIN → switch → return topology is evaluated by current transient loop; power FET/diode/inductor placement varies across buck/boost/synchronous. TS02.

**SC03: Return-reference continuity is a *spatial* condition.** Full-route GND-reference overlap matters; two route candidates of equal length can have radically different return current detours. TS03 Fig 3-4 / TS05 / TS06.

**SC04: Geometry + manufacturability are dual constraints.** Via-in-pad fill, soldermask slivers, exposed-pad paste, assembly clearances and drill sizes depend on vendor fab and assembly. TS04/TS12/TS01.

**SC05: DRC is necessary, not sufficient.** DRC validates net/rules *that have been encoded*; do not infer high-speed eye diagram, EMC, ADC ENOB, signal-to-noise or thermal pass without engineering tests. TS01/TS03/TS04.

**SC06: Source-specific overrides.** TI TS03's USB2 90Ω±15% table, IPC-2152's thermal sizing methods, ADI TS05's high-speed ADC GND via density and the RD03 ESP32-S3 crystal gap are scoped recommendations; choose constraints from device-level specifications first.

## Conflict log — deliberately kept explicit
- **AGND/DGND split:** TS07 discusses separation of functional analog/digital regions; TS04 recommends simple common GND in many mixed-signal converter systems. Both can be true under distinct return-current/isolated-system assumptions. **Action:** inspect exact ADC layout guide and topology, no automatic plane split.
- **Placement “closest”:** TS04 advocates pin bypass proximity, while plane/via inductance and assembly constraints mean minimal centroid distance is not sufficient. **Action:** measure pad route + return inductance proxy, not only xy distance.
- **USB impedance:** TI TS03's numbers describe context of signal conditioners/hubs, not universal USB-C (which is a connector) or Full Speed only designs. **Action:** tag rule by PHY/interface and fab stackup.
- **Rules vs measured proof:** Device EVM and technical articles can provide useful patterns but are not proof that a copied layout passes EMI/thermal. Record actual test evidence separately.

## Next research tasks
- Open full Microchip PDF, inspect layout figures/tolerances and pin-specific exceptions; promote TS09 to PDF_SCREENSHOT_INSPECTED only after doing so.
- Cross-check IPC standards edition currently licensed by the user's organization before applying numeric acceptance criteria.
- Obtain actual published CAD PCB, pin revision/sha, derive trace/net/zone topology and compare to reviewed reference figures.

**No standard text or third-party source CAD is copied into this repository.**
