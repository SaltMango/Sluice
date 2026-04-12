# Custom Torrent Client – Architecture (v5 – Tauri + React)

## 1. Overview

A high-performance **desktop torrent application** built on top of libtorrent, featuring:

- Adaptive scheduling engine
- Peer intelligence system
- Modern UI using React
- Lightweight desktop runtime using Tauri

---

## 2. Core Design Decision

### Protocol Layer

- libtorrent (Python bindings)

### Application Type

- Desktop app (single system, NOT web app)

### UI Stack

- React (Vite)

### Desktop Runtime

- Tauri (Rust-based)

---

## 3. Final Architecture

```text
                 ┌────────────────────────────┐
                 │       React UI (Vite)      │
                 │ (Tables, Charts, Controls)│
                 └────────────┬───────────────┘
                              │
                 ┌────────────▼───────────────┐
                 │        Tauri Core          │
                 │ (Rust IPC + OS bridge)    │
                 └────────────┬───────────────┘
                              │
                 ┌────────────▼───────────────┐
                 │        Controller          │
                 │   (UI ↔ Engine bridge)     │
                 └────────────┬───────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐  ┌────────▼────────┐  ┌─────────▼────────┐
│ Scheduler Core │  │ Peer Manager    │  │ Torrent Engine   │
│ (adaptive)     │  │ (peer scoring)  │  │ (libtorrent)     │
└───────┬────────┘  └────────┬────────┘  └─────────┬────────┘
        │                    │                     │
        └────────────┬───────┴────────────┬────────┘
                     │                    │
              ┌──────▼────────────────────▼──────┐
              │        libtorrent Core           │
              │ (networking + disk + peers)     │
              └─────────────────────────────────┘
```

---

## 4. Key Change (IMPORTANT)

### Before (v4)

- PyQt GUI directly connected to controller

### Now (v5)

- React UI runs inside Tauri
- Tauri acts as **bridge layer**
- Controller remains the same core logic

---

## 5. UI Layer (React)

### Technology

- React + Vite

### Responsibilities

- Display:
  - Torrent list
  - Progress %
  - Speed (MB/s)
  - Peer count

- User actions:
  - Add torrent
  - Pause/resume
  - Remove torrent

- Show logs and stats

---

## 6. Tauri Layer (NEW)

Acts as:

👉 Secure bridge between UI and system

### Responsibilities

- Launch Python engine
- Handle communication (IPC)
- Provide OS features:
  - File picker
  - Notifications

- Expose commands to React

---

## 7. Controller Layer

Same as v4, but now sits **after Tauri**

### Responsibilities

- Bridge UI ↔ Engine
- Manage:
  - Torrent lifecycle
  - Scheduler execution
  - Timers

- Send updates back to UI

---

## 8. Communication Flow

### UI → Engine

```text
React → Tauri → Controller → Engine
```

### Engine → UI

```text
Engine → Controller → Tauri → React
```

---

## 9. Scheduler Core

Runs inside Python engine.

### Piece Score

```text
score(piece) =
    W_rarity   * norm_rarity
  + W_position * norm_position
  + W_peer     * norm_peer_availability
  + W_speed    * norm_peer_speed
```

---

## 10. Peer Manager

- Computes normalized peer score
- Feeds scheduler
- Runs every 1 second

---

## 11. Controller Loop

Timers:

- Peer update → 1s
- Scheduler update → 2s
- UI update → 1s

---

## 12. Bandwidth Logic

Uses:

- User config OR observed peak

Adaptive mode:

- Increase peers if underutilized
- Backoff if unstable

---

## 13. State Persistence

- Resume data (libtorrent)
- Config (JSON/YAML)
- Logs

---

## 14. Logging

- Console (dev)
- File (runtime)
- Structured logs

---

## 15. Concurrency Model

- Python engine runs as separate process
- Tauri manages lifecycle
- Async communication via IPC

---

## 16. Optional API Layer (Future)

Used for:

- Remote control
- Web UI
- Multi-device

Not required for MVP

---

## 17. Final Design Principles

- Engine-first architecture
- UI is replaceable (React / PyQt / Web)
- Lightweight desktop runtime (Tauri)
- Scheduler is core innovation
- Single-user local system (initially)

---
