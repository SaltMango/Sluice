# 🚀 Sluice - Smart Torrent Client

A high-performance, adaptive BitTorrent client built for modern high-bandwidth environments.

---

## 🧠 Overview

Sluice is a next-generation torrent engine designed to:

- Maximize bandwidth utilization
- Adapt dynamically to swarm conditions
- Improve download efficiency using intelligent scheduling

Built with:

- Python + libtorrent (core engine)
- React + Tauri (desktop UI)

---

## ✨ Features

### ⚡ Smart Scheduler

- Hybrid piece prioritization
- Rarest-first + edge boosting
- Dynamic adaptation based on peer behavior

### 👥 Peer Intelligence

- Real-time peer scoring
- Fast peer prioritization
- Stability-aware selection

### 📊 Performance Optimization

- Adaptive bandwidth utilization
- Aggressive mode (with safeguards)
- Smart request distribution

### 🖥️ Modern UI

- Built with React + Tauri
- Lightweight and responsive
- Real-time stats and monitoring

---

## 🏗️ Architecture

```text
React UI → Tauri → Controller → Engine (Scheduler + Peer Manager) → libtorrent
```

- Single desktop application
- Engine-first design
- UI is replaceable

---

## 📦 Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- Rust (for Tauri)
- libtorrent

---

### Setup

```bash
# Clone repo
git clone https://github.com/SaltMango/Sluice.git
cd Sluice

# Setup Python engine
cd engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run engine
uvicorn main:app

# Setup frontend
cd ../frontend
npm install

# Run app
npm run tauri dev
```

---

## 🚀 Usage

1. Launch the application
2. Add a `.torrent` file or magnet link
3. Monitor:
   - Download speed
   - Peer connections
   - Progress

---

## ⚠️ Legal Disclaimer

This software is a **general-purpose BitTorrent client**.

- It does **not provide or host any content**
- It does **not promote piracy**

Users are solely responsible for how they use this software.

---

## ⚖️ Terms of Use

By using this software, you agree that:

1. You will comply with all applicable local laws
2. You will not use this software to download or distribute copyrighted content without permission
3. The developers are **not responsible** for misuse

---

## 📜 Copyright Notice

Downloading or distributing copyrighted material without authorization may be illegal in your jurisdiction.

Examples of legal use:

- Linux ISOs
- Open-source software
- Public datasets

---

## 🛡️ Liability Limitation

This software is provided:

> “AS IS”, WITHOUT WARRANTY OF ANY KIND

The authors are not liable for:

- Data loss
- Legal issues arising from misuse
- Network or system damage

---

## 🔐 Security & Privacy

- No data is collected or transmitted externally
- All operations are local
- No tracking or analytics

---

## 📂 Project Structure

```text
project/
├── frontend/     # React + Tauri UI
├── engine/       # Python torrent engine
├── docs/
└── README.md
```

---

## 🧪 Development

### Run backend

```bash
cd engine
uvicorn main:app --reload
```

### Run frontend

```bash
cd frontend
npm run tauri dev
```

---

## 🤝 Contributing

Contributions are welcome!

Steps:

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

---

## 📄 License

MIT License

---

## ⚠️ Important Note

This project is intended for:

- Research
- Learning
- Performance optimization

It is **not designed or marketed for piracy**.

---

## 🌍 Vision

To build a next-generation adaptive download engine that:

- Maximizes efficiency
- Respects legal boundaries
- Pushes torrent technology forward

---

## ⭐ Acknowledgements

- libtorrent
- BitTorrent protocol contributors

---

## 📬 Contact

For questions or contributions:

- GitHub Issues
- Discussions

---

## 🚀 Future Plans

- Multi-torrent optimization
- AI-based scheduling
- Distributed downloading

---

## 🔥 Final Thought

> Torrent is a technology.
> How it is used defines its legality.

Use responsibly.
