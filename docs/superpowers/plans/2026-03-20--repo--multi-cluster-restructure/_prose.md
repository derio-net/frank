# Multi-Cluster Monorepo Restructure — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-03-20--repo--multi-cluster-restructure-design.md`
**Status:** Not Started

## Phase 0: File Restructure

### Task 1: Move directories and update all file-level path references

- P0.T1.S1: Move directories

- P0.T1.S2: Update all Application CR template paths

- P0.T1.S3: Update Omni config patch paths

- P0.T1.S4: Commit the restructure as a single atomic commit

## Phase 1: ArgoCD Sync

### Task 1: Disable auto-sync, update ArgoCD root app, push, sync, verify, re-enable

- P1.T1.S1: Disable Frank ArgoCD auto-sync

- P1.T1.S2: Update Frank root app in ArgoCD

- P1.T1.S3: Push and verify Frank ArgoCD sync

- P1.T1.S4: Re-enable auto-sync

- P1.T1.S5: Commit any fixups

## Phase 2: Update References

### Task 1: Update documentation and CI

- P2.T1.S1: Update CLAUDE.md

- P2.T1.S2: Update blog posts with repo structure references

- P2.T1.S3: Update CI workflows

- P2.T1.S4: Update runbooks

- P2.T1.S5: Commit reference updates
