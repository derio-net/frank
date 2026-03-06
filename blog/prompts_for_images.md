# Prompts for Generating Images

Here are prompts for Gemini, tailored to each image you need. They all share a consistent style based on your reference — cartoon Frankenstein monster made of computer parts.

**Base style to prepend to each prompt:**
> `Cartoon illustration, vibrant colors, thick outlines, chibi proportions. Dark background with electric blue lightning accents. Tech-horror aesthetic, playful not scary.`

---

## Site Banner (wide, 1200x630)

> A wide banner illustration of a Frankenstein-like monster made entirely of server hardware. His torso is a rack-mount server chassis with blinking LEDs, shoulders are CPU heatsinks with spinning fans, arms are bundles of ethernet cables and PCIe risers, legs are stacked NVMe SSDs. Bolts on his neck are RJ45 connectors crackling with blue electricity. He stands triumphantly on a pile of Raspberry Pis and NUC mini-PCs, arms raised. Behind him, a glowing Kubernetes wheel logo floats like a full moon. Text space on the right side. Wide cinematic aspect ratio.

## Favicon (square, simple)

> A simple square icon of a green Frankenstein monster head made of computer parts. Flat-top head is a CPU die with circuit traces, neck bolts are USB-C connectors sparking with blue electricity, eyes are blue LED status lights, stitches across forehead are solder traces. Minimal detail, icon-friendly, works at 32x32px. Solid dark background.

## Post Covers

**Post 0 — Overview & Roadmap:**
> A Frankenstein monster made of server hardware standing at a workbench, assembling himself. One arm is already attached (ethernet cables), the other is being bolted on (GPU card arm). On the workbench: scattered Raspberry Pis, NUC computers, SSDs, RAM sticks, and a blueprint/schematic showing the full monster design. Electric sparks where parts connect.

**Post 1 — Introduction (Why Build a Homelab):**
> A Frankenstein monster made of computer parts sitting at a desk, sketching blueprints of himself on paper. The desk has scattered components — a Raspberry Pi, a NUC mini-PC, a GPU card, ethernet cables. A thought bubble above his head shows a cloud with a red X through it (rejecting cloud). Cozy workshop/lab setting with server rack shelves in background.

**Post 2 — Foundation (Talos, Nodes, Cilium):**
> A Frankenstein monster made of server hardware laying the foundation of a building. He's placing server nodes like bricks — three identical NUC-shaped bricks for the base layer, connected by glowing green eBPF/cilium network threads that weave between them like mortar. A hexagonal bee (Cilium logo reference) flies nearby. Construction site setting.

**Post 3 — Storage (Longhorn):**
> A Frankenstein monster made of computer parts riding a longhorn bull made of stacked hard drives and SSDs. The bull's horns are SATA cables, its body is a RAID array of glowing drives. The monster holds reins made of iSCSI cables. Three glowing copies of a data block float behind them (representing 3 replicas). Western/ranch setting with server racks as fence posts.

**Post 4 — GPU Compute:**
> A Frankenstein monster made of server hardware with one massive arm that's an NVIDIA RTX GPU card (green, glowing, oversized) and one regular arm with a smaller Intel Arc GPU (blue glow). The GPU arm crackles with energy but has a red warning sign on it (broken). The Intel arm works perfectly, with a small blue spark. Lightning bolts between the two arms. The monster looks frustrated at the big arm and pleased with the small one.

**Post 5 — GitOps (ArgoCD):**
> A Frankenstein monster made of computer parts conducting an orchestra. Each orchestra member is a different Kubernetes pod/container (small box-shaped robots). The monster holds a conductor's baton that's a git branch, and sheet music on the stand shows YAML code. An octopus (ArgoCD reference) sits on his shoulder, its tentacles reaching out to touch each orchestra member. Musical notes are replaced with sync arrows and checkmarks.

**Post 6 — Fun Stuff (RGB LEDs):**
> A Frankenstein monster made of server hardware standing in front of a mirror, admiring himself. His chest fans glow with rainbow RGB lighting. He holds a tiny git commit message that says "color: red" and his fans are changing from rainbow to red. A small ArgoCD octopus on his shoulder holds a paintbrush. The monster looks proud and slightly vain. Disco ball made of a CPU die hangs from ceiling.

---

For PaperMod, once you have the images, drop them as `cover.png` inside each post's page bundle directory and add this to each post's front matter:

```yaml
cover:
  image: cover.png
  alt: "Frank the cluster monster — [topic]"
  relative: true
```
