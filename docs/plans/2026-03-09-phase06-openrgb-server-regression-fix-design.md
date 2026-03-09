# Design: OpenRGB Server Regression Fix

## Background

The Phase 6 OpenRGB DaemonSet uses a two-container pod:
- **Init container** (`apply-leds`): runs `openrgb $OPENRGB_ARGS` to set LED colors on startup
- **Main container** (`openrgb-server`): runs `openrgb --server` as a keepalive

During the PCIe link speed fix session (2026-03-09), the LEDs were observed showing incorrect
colors (green, then lila) instead of off (`000000`) across cold boots. Debugging revealed that
the `--server` container takes ownership of the IT5701-GIGABYTE USB HID device after the init
container exits, reinitializes it, and resets the LEDs to the device's last saved hardware
state — overwriting the config applied by the init container.

Running `openrgb --noautoconnect -d 0 -m Static -c 000000` standalone (bypassing the server)
successfully turned the LEDs off, confirming the server is the cause of the regression.

The server was included in the original Phase 6 design solely as a keepalive mechanism. It was
never used as a remote control interface. This is a YAGNI violation that caused a real bug.

## Root Cause

The IT5701-GIGABYTE controller saves color state to non-volatile memory. When the server
container starts and takes device ownership, it reinitializes the device — which restores the
last saved hardware state rather than the color applied by the init container.

## Fix

Replace the two-container pod with a single container:

```yaml
containers:
  - name: openrgb
    image: swensorm/openrgb:release_0.9
    command: ["/bin/sh", "-c"]
    args:
      - |
        /usr/app/openrgb --noautoconnect $OPENRGB_ARGS
        sleep infinity
    env:
      - name: OPENRGB_ARGS
        valueFrom:
          configMapKeyRef:
            name: openrgb-config
            key: OPENRGB_ARGS
    securityContext:
      privileged: true
    volumeMounts:
      - name: dev
        mountPath: /dev
```

- `--noautoconnect` prevents any attempt to connect to a local server (standalone mode)
- Config is applied once at container startup
- `sleep infinity` keeps the pod alive as a simple keepalive
- No server takes device ownership afterward — the applied color persists

The ConfigMap is unchanged. Updating LED config remains a one-line git edit + ArgoCD sync.

## Implementation Order

1. Apply fix to `apps/openrgb/manifests/daemonset.yaml`
2. **Verify live** — confirm LEDs turn off on pod restart before updating any docs
3. Update `docs/plans/2026-03-03-phase06-openrgb-led-control-design.md`
4. Update `docs/plans/2026-03-03-phase06-openrgb-led-control.md`
5. Update Phase 6 blog post with corrected architecture and regression note
