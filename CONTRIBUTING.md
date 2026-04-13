# 🤝 Contributing to Smart Torrent Client

Thank you for your interest in contributing!

We welcome contributions of all kinds:

- Bug fixes
- Feature improvements
- Documentation updates
- Performance optimizations

---

## 🧠 Before You Start

Please:

- Read the README.md
- Check existing issues
- Open a discussion for large changes

---

## 🚀 Development Setup

### 1. Clone repo

```bash
git clone https://github.com/yourusername/smart-torrent-client.git
cd smart-torrent-client
```

### 2. Setup Python engine

```bash
cd engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run backend

```bash
uvicorn main:app --reload
```

### 4. Run frontend

```bash
cd frontend
npm install
npm run tauri dev
```

---

## 🛠️ Code Structure

```
engine/
 ├── torrent.py
 ├── scheduler.py
 ├── peers.py
 └── controller.py

frontend/
 ├── React UI
 └── Tauri app
```

---

## 📌 Coding Guidelines

### Python

- Use type hints
- Follow PEP8
- Keep modules small and focused
- Avoid global state

### React

- Use functional components
- Keep UI logic separate from API calls
- Maintain clean state management

---

## 🧪 Testing

- Test your feature locally before PR
- Avoid breaking existing functionality
- Add logs where needed

---

## 🔄 Pull Request Process

1. Fork the repository
2. Create a branch:

```bash
git checkout -b feature/your-feature-name
```

3. Commit changes:

```bash
git commit -m "feat: add new scheduler logic"
```

4. Push:

```bash
git push origin feature/your-feature-name
```

5. Open Pull Request

---

## 📝 Commit Message Format

Use standard format:

```
feat: new feature
fix: bug fix
refactor: code improvement
docs: documentation change
```

---

## ⚠️ Legal Notice

By contributing, you agree that:

- Your code will be licensed under the MIT License
- You do not include copyrighted or illegal content
- You do not add piracy-related features or data

---

## 🚫 What NOT to contribute

- Piracy-related content
- Torrent links to copyrighted material
- Malicious code

---

## 💡 Contribution Ideas

- Improve scheduler performance
- Better peer scoring algorithms
- UI enhancements
- Logging and monitoring improvements

---

## 🙌 Code of Conduct

Be respectful and constructive.

We aim to build:

- Clean code
- Useful tools
- Positive community

---

## 📬 Questions?

Open an issue or discussion.

Thanks for contributing 🚀
