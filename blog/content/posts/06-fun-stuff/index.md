---
title: "Fun Stuff — Controlling Case LEDs from Kubernetes"
date: 2026-03-06
draft: true
tags: ["openrgb", "hardware"]
summary: "The most over-engineered RGB setup — controlling ARGB case fans from a Kubernetes DaemonSet via USB HID."
weight: 7
---

Every serious infrastructure project needs a completely unnecessary feature. This is ours: controlling the ARGB LED fans on gpu-1 from a Kubernetes DaemonSet.

## The Hardware

*Content to be written — FOIFKIN F1 case, 6 PWM ARGB fans, internal hub, Gigabyte Z790 Eagle AX motherboard, ITE IT5701 USB RGB controller.*

## USB HID vs I2C

*Content to be written — originally tried I2C path, Talos kernel lacks CONFIG_I2C_CHARDEV, pivoted to USB HID (simpler, safer, already available via /dev/hidraw0).*

## The OpenRGB DaemonSet

<!-- Reference: apps/openrgb/manifests/daemonset.yaml -->

*Content to be written — privileged pod, /dev mount for USB HID access, nodeSelector for gpu-1 only, one-shot LED config on startup.*

## ConfigMap-Driven LED Config

<!-- Reference: apps/openrgb/manifests/configmap.yaml -->

*Content to be written — change OPENRGB_ARGS in the ConfigMap, push to git, ArgoCD syncs, LEDs change. GitOps for RGB.*

## Was It Worth It?

Absolutely not. But the fans look great.
